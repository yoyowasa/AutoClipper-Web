import json
import re
import shutil
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.orm import Session

from app.audio.extract import extract_mono_wav
from app.audio.silence_detect import SilenceSegment, detect_silence, silence_output_path, write_silence_segments
from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine,
    TranscriptSegment,
    transcript_output_path,
    write_transcript_segments,
)
from app.audio.volume_features import AudioFeatures, audio_features_output_path, compute_audio_features, write_audio_features
from app.candidates.generate_normal_candidates import generate_normal_candidates
from app.candidates.generate_short_candidates import generate_short_candidates
from app.candidates.merge_boundaries import Candidate, write_candidates
from app.candidates.select_candidates import CandidateSelection, select_candidates, write_selected_clips
from app.db import SessionLocal
from app.ids import make_id
from app.jobs.summaries import write_generation_summaries
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP, SUCCESS_STATUSES
from app.models import ExportItem, Job, Video
from app.render.render_normal import NormalRenderBatchResult, render_normal_clip, render_selected_normal_candidates
from app.render.render_short import ShortRenderBatchResult, render_selected_short_candidates, render_short_clip
from app.scoring.openai_score import OpenAICandidateScorer, score_candidate_batch
from app.scoring.rule_score import score_candidates
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.black_screen import (
    BlackScreenSegment,
    VisualQuality,
    build_visual_quality,
    detect_black_screen,
    visual_quality_output_path,
    write_visual_quality,
)
from app.video.probe import VideoMetadata, probe_metadata
from app.video.scene_detect import SceneSegment, scene_output_path, scene_segments_from_boundaries, write_scene_segments
from app.video.scene_detect import detect_scenes as default_detect_scenes


SessionFactory = Callable[[], Session]
ProbeMetadata = Callable[[str | Path], VideoMetadata]
ExtractAudio = Callable[[str | Path, str | Path], Path]
TranscribeAudio = Callable[[str | Path], list[TranscriptSegment]]
DetectScenes = Callable[[str | Path], list[SceneSegment]]
DetectSilence = Callable[[str | Path, float | None], list[SilenceSegment]]
ComputeAudioFeatures = Callable[[str | Path, float, Sequence[SilenceSegment]], AudioFeatures]
DetectBlackScreen = Callable[[str | Path], list[BlackScreenSegment]]

MIN_AUDIO_VOLUME_PEAK = 0.005
MAX_AUDIO_SILENCE_RATIO = 0.98
MIN_AUDIO_SPEECH_SECONDS = 1.0
MIN_AUDIO_SPEECH_DENSITY = 0.02

MIN_TRANSCRIPT_TEXT_LENGTH = 20
MIN_TRANSCRIPT_SPEECH_SECONDS = 3.0
MIN_AVERAGE_TRANSCRIPT_CONFIDENCE = 0.25
LOW_INFORMATION_WORDS = {
    "ah",
    "hmm",
    "mm",
    "music",
    "thank",
    "thanks",
    "uh",
    "um",
    "you",
    "yeah",
}


@dataclass(frozen=True)
class AutoClipperPipelineDependencies:
    probe_metadata: ProbeMetadata = probe_metadata
    extract_audio: ExtractAudio = extract_mono_wav
    transcribe_audio: TranscribeAudio | None = None
    detect_scenes: DetectScenes = default_detect_scenes
    detect_silence: DetectSilence | None = None
    compute_audio_features: ComputeAudioFeatures = compute_audio_features
    detect_black_screen: DetectBlackScreen = detect_black_screen
    normal_renderer: Callable[..., Path] = render_normal_clip
    short_renderer: Callable[..., Any] = render_short_clip
    openai_scorer: OpenAICandidateScorer | None = None


class PipelineExpectedError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _default_transcribe_audio(wav_path: str | Path) -> list[TranscriptSegment]:
    return FasterWhisperTranscriptionEngine().transcribe(wav_path)


def _truthy_setting(settings: dict[str, Any], key: str) -> bool:
    value = settings.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _e2e_fixture_transcript_enabled(settings: dict[str, Any]) -> bool:
    return _truthy_setting(settings, "e2eFixtureTranscript")


def _e2e_fixture_transcript(duration: float) -> list[TranscriptSegment]:
    end = round(max(duration, 0.001), 3)
    return [
        TranscriptSegment(
            start=0.0,
            end=end,
            text=(
                "Why automation mistakes matter before launch. "
                "How teams can fix the process with a clear checklist. "
                "The final lesson is to measure progress every week."
            ),
            confidence=1.0,
        )
    ]


def _default_detect_silence(wav_path: str | Path, duration: float | None) -> list[SilenceSegment]:
    return detect_silence(wav_path, audio_duration=duration)


def _format_diagnostic_message(message: str, details: dict[str, Any]) -> str:
    if not details:
        return message
    return f"{message} Diagnostics: {json.dumps(details, sort_keys=True)}"


def _set_status(db: Session, job: Job, status: str) -> None:
    job.status = status
    job.progress = PROGRESS_MAP[status]
    job.current_step = CURRENT_STEP_MAP[status]
    if status != "failed":
        job.error_code = None
        job.error_message = None
    db.commit()
    db.refresh(job)


def _fail_job(db: Session, job_id: str, code: str, message: str, details: dict[str, Any] | None = None) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.status = "failed"
    job.progress = PROGRESS_MAP["failed"]
    job.current_step = CURRENT_STEP_MAP["failed"]
    job.error_code = code
    job.error_message = _format_diagnostic_message(message, details or {})
    db.commit()


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _metadata_to_jsonable(metadata: VideoMetadata) -> dict[str, Any]:
    return {
        "duration": metadata.duration,
        "width": metadata.width,
        "height": metadata.height,
        "fps": metadata.fps,
        "has_audio": metadata.has_audio,
    }


def _update_video_metadata(db: Session, video: Video, metadata: VideoMetadata) -> None:
    video.duration = metadata.duration
    video.width = metadata.width
    video.height = metadata.height
    video.fps = metadata.fps
    video.has_audio = metadata.has_audio
    db.commit()


def _safe_scene_detection(
    input_path: Path,
    duration: float | None,
    detector: DetectScenes,
) -> list[SceneSegment]:
    try:
        scenes = detector(input_path)
    except Exception:
        scenes = []
    if scenes:
        return scenes
    return scene_segments_from_boundaries([], duration=duration)


def _safe_silence_detection(
    wav_path: Path,
    duration: float | None,
    detector: DetectSilence,
) -> list[SilenceSegment]:
    try:
        return detector(wav_path, duration)
    except Exception:
        return []


def _safe_audio_features(
    wav_path: Path,
    duration: float,
    silence_segments: Sequence[SilenceSegment],
    builder: ComputeAudioFeatures,
) -> AudioFeatures:
    try:
        return builder(wav_path, duration, silence_segments)
    except Exception:
        return AudioFeatures(
            duration=max(duration, 0.0),
            silence_ratio=0.0,
            speech_density=1.0 if duration > 0 else 0.0,
            volume_peak=0.5,
            silent_seconds=0.0,
            speech_seconds=max(duration, 0.0),
        )


def _audio_diagnostics(audio_features: AudioFeatures) -> dict[str, float]:
    return {
        "duration": round(audio_features.duration, 6),
        "silence_ratio": round(audio_features.silence_ratio, 6),
        "speech_seconds": round(audio_features.speech_seconds, 6),
        "speech_density": round(audio_features.speech_density, 6),
        "volume_peak": round(audio_features.volume_peak, 6),
    }


def _audio_is_silent_or_unusable(audio_features: AudioFeatures) -> bool:
    if audio_features.duration <= 0:
        return True
    if audio_features.volume_peak <= MIN_AUDIO_VOLUME_PEAK:
        return True
    if (
        audio_features.silence_ratio >= MAX_AUDIO_SILENCE_RATIO
        and audio_features.speech_seconds <= MIN_AUDIO_SPEECH_SECONDS
    ):
        return True
    return (
        audio_features.speech_density <= MIN_AUDIO_SPEECH_DENSITY
        and audio_features.speech_seconds <= MIN_AUDIO_SPEECH_SECONDS
    )


def _raise_if_audio_unusable(audio_features: AudioFeatures) -> None:
    if not _audio_is_silent_or_unusable(audio_features):
        return
    details = _audio_diagnostics(audio_features)
    raise PipelineExpectedError(
        "audio_silent_or_unusable",
        "Audio is silent or too weak for reliable transcription.",
        details=details,
    )


def _transcript_text(segments: Sequence[TranscriptSegment]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def _transcript_speech_duration(segments: Sequence[TranscriptSegment]) -> float:
    return sum(max(0.0, segment.end - segment.start) for segment in segments if segment.text.strip())


def _average_transcript_confidence(segments: Sequence[TranscriptSegment]) -> float | None:
    values = [segment.confidence for segment in segments if segment.confidence is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _transcript_has_repeated_low_information_text(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    if len(words) < 5:
        return False
    counts = Counter(words)
    word, count = counts.most_common(1)[0]
    return word in LOW_INFORMATION_WORDS and count / len(words) >= 0.8


def _transcript_diagnostics(segments: Sequence[TranscriptSegment]) -> dict[str, Any]:
    text = _transcript_text(segments)
    average_confidence = _average_transcript_confidence(segments)
    details: dict[str, Any] = {
        "segment_count": len(segments),
        "total_text_length": len(text),
        "total_speech_duration": round(_transcript_speech_duration(segments), 6),
    }
    if average_confidence is not None:
        details["average_confidence"] = round(average_confidence, 6)
    return details


def _raise_if_transcript_unusable(segments: Sequence[TranscriptSegment]) -> None:
    details = _transcript_diagnostics(segments)
    text = _transcript_text(segments)
    average_confidence = _average_transcript_confidence(segments)
    reasons: list[str] = []

    if not segments:
        reasons.append("segment_count_zero")
    if len(text) < MIN_TRANSCRIPT_TEXT_LENGTH:
        reasons.append("total_text_length_too_low")
    if _transcript_speech_duration(segments) < MIN_TRANSCRIPT_SPEECH_SECONDS:
        reasons.append("total_speech_duration_too_low")
    if average_confidence is not None and average_confidence < MIN_AVERAGE_TRANSCRIPT_CONFIDENCE:
        reasons.append("average_confidence_too_low")
    if _transcript_has_repeated_low_information_text(text):
        reasons.append("repeated_low_information_text")

    if not reasons:
        return

    details["reasons"] = reasons
    raise PipelineExpectedError(
        "transcript_unusable",
        "Transcription did not produce usable speech text.",
        details=details,
    )


def _safe_visual_quality(
    input_path: Path,
    duration: float,
    detector: DetectBlackScreen,
) -> VisualQuality:
    try:
        black_segments = detector(input_path)
    except Exception:
        black_segments = []
    return build_visual_quality(duration, black_segments)


def _score_candidate_list(
    candidates: Sequence[Candidate],
    settings: dict[str, Any],
    audio_features: AudioFeatures,
    silence_segments: Sequence[SilenceSegment],
    visual_quality: VisualQuality,
    scorer: OpenAICandidateScorer | None,
) -> list[Candidate]:
    rule_scored = score_candidates(
        candidates,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    use_openai = bool(
        settings.get("useOpenAIScoring")
        or settings.get("openaiScoring")
        or settings.get("enableOpenAIScoring")
    )
    if not use_openai:
        return [candidate.model_copy(update={"final_score": candidate.rule_score}) for candidate in rule_scored]
    active_scorer = scorer or OpenAICandidateScorer()
    try:
        openai_scored = score_candidate_batch(
            rule_scored,
            scorer=active_scorer,
            audio_features=audio_features,
            visual_features=visual_quality,
        )
    except Exception:
        return [
            candidate.model_copy(
                update={
                    "final_score": candidate.rule_score,
                    "should_use": None,
                    "reject_reason": None,
                    "risk_flags": [*candidate.risk_flags, "openai_fallback_rule_score"],
                }
            )
            for candidate in rule_scored
        ]

    fallback_candidates: list[Candidate] = []
    for candidate in openai_scored:
        if "openai_scoring_failed" not in candidate.risk_flags:
            fallback_candidates.append(candidate)
            continue
        fallback_candidates.append(
            candidate.model_copy(
                update={
                    "ai_score": None,
                    "final_score": candidate.rule_score,
                    "should_use": None,
                    "reject_reason": None,
                    "reason": "OpenAI scoring failed; used rule score fallback.",
                    "risk_flags": [
                        flag
                        for flag in candidate.risk_flags
                        if flag != "openai_scoring_failed"
                    ]
                    + ["openai_fallback_rule_score"],
                }
            )
        )
    return fallback_candidates


def _render_failures_to_jsonable(
    normal_result: NormalRenderBatchResult | None,
    short_result: ShortRenderBatchResult | None,
) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    if normal_result is not None:
        payload.extend(
            {"type": "normal", "candidate_id": failure.candidate_id, "error": failure.error}
            for failure in normal_result.failures
        )
    if short_result is not None:
        payload.extend(
            {"type": "short", "candidate_id": failure.candidate_id, "error": failure.error}
            for failure in short_result.failures
        )
    return payload


def _create_zip(zip_path: Path, exports: Sequence[ExportItem], metadata_files: Sequence[Path] | None = None) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for export in exports:
            for value in (export.video_path, export.subtitle_path, export.metadata_path):
                if not value:
                    continue
                path = Path(value)
                if path.is_file():
                    archive.write(path, arcname=path.name)
        for metadata_file in metadata_files or []:
            if metadata_file.is_file():
                archive.write(metadata_file, arcname=metadata_file.name)


def _write_placeholder_mp4(path: Path, label: str) -> None:
    path.write_bytes(f"AutoClipper dummy MP4: {label}\n".encode("utf-8"))


def _create_export(
    db: Session,
    job: Job,
    output_dir: Path,
    export_type: str,
    index: int,
    duration: float,
    score: float,
) -> ExportItem:
    title_prefix = "Normal clip" if export_type == "normal" else "Short"
    export_id = make_id("exp")
    video_path = output_dir / f"{export_type}_{index:02d}.mp4"
    metadata_path = output_dir / f"{export_type}_{index:02d}.json"
    _write_placeholder_mp4(video_path, f"{title_prefix} {index}")
    _write_json(
        metadata_path,
        {
            "id": export_id,
            "type": export_type,
            "title": f"{title_prefix} {index}",
        },
    )

    export = ExportItem(
        id=export_id,
        job_id=job.id,
        video_id=job.video_id,
        candidate_id=None,
        type=export_type,
        title=f"{title_prefix} {index}",
        duration=duration,
        score=score,
        video_path=str(video_path),
        subtitle_path=None,
        metadata_path=str(metadata_path),
    )
    db.add(export)
    return export


def _create_dummy_exports(db: Session, job: Job, output_dir: Path) -> list[ExportItem]:
    exports = [
        _create_export(db, job, output_dir, "normal", 1, 180.0, 84.0),
        _create_export(db, job, output_dir, "normal", 2, 240.0, 81.0),
        _create_export(db, job, output_dir, "short", 1, 42.0, 88.0),
        _create_export(db, job, output_dir, "short", 2, 36.0, 86.0),
        _create_export(db, job, output_dir, "short", 3, 58.0, 83.0),
    ]
    db.commit()
    return exports


def run_dummy_autoclipper_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    output_dir = storage_paths.job_outputs(job_id)
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")

        try:
            for next_status in SUCCESS_STATUSES[:-1]:
                _set_status(db, job, next_status)
                visited_statuses.append(next_status)

            exports = _create_dummy_exports(db, job, output_dir)
            summary_files = write_generation_summaries(output_dir, exports=exports)
            _create_zip(storage_paths.zip_path(job.id), exports, metadata_files=summary_files)

            _set_status(db, job, "completed")
            visited_statuses.append("completed")
        except Exception as exc:
            _fail_job(db, job_id, "dummy_job_failed", str(exc))
            raise

    return visited_statuses


def score_candidate_batch_for_worker(
    candidates: Sequence[Candidate],
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
    scorer: OpenAICandidateScorer | None = None,
) -> list[Candidate]:
    active_scorer = scorer or OpenAICandidateScorer()
    return score_candidate_batch(
        candidates,
        scorer=active_scorer,
        audio_features=audio_features,
        visual_features=visual_features,
    )


def run_autoclipper_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    transcribe_audio = deps.transcribe_audio or _default_transcribe_audio
    detect_silence_for_audio = deps.detect_silence or _default_detect_silence
    visited_statuses: list[str] = []
    metadata_files: list[Path] = []
    normal_result: NormalRenderBatchResult | None = None
    short_result: ShortRenderBatchResult | None = None
    transcript_segments: list[TranscriptSegment] = []
    silence_segments: list[SilenceSegment] = []
    audio_features: AudioFeatures | None = None
    normal_candidates: list[Candidate] = []
    short_candidates: list[Candidate] = []
    scored_candidates: list[Candidate] = []
    selection: CandidateSelection | None = None
    exports: list[ExportItem] = []
    transcription_engine = "not_run"
    used_fixture_transcript = False
    summary_files: list[Path] = []
    temp_dir: Path | None = None

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        settings = dict(job.settings_json or {})
        used_fixture_transcript = _e2e_fixture_transcript_enabled(settings)
        job_dir = storage_paths.job_outputs(job.id)
        temp_dir = storage_paths.temp / job.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        input_path = storage_paths.resolve_stored_file(video.stored_path)
        audio_path = temp_dir / "audio.wav"

        def write_summaries() -> list[Path]:
            return write_generation_summaries(
                job_dir,
                transcript_segments=transcript_segments,
                audio_features=audio_features,
                normal_candidates=normal_candidates,
                short_candidates=short_candidates,
                scored_candidates=scored_candidates,
                selection=selection,
                normal_result=normal_result,
                short_result=short_result,
                exports=exports,
                transcription_engine=transcription_engine,
                used_fixture_transcript=used_fixture_transcript,
            )

        try:
            _set_status(db, job, "probing")
            visited_statuses.append("probing")
            try:
                metadata = deps.probe_metadata(input_path)
            except Exception as exc:
                raise PipelineExpectedError(
                    "probe_failed",
                    f"Could not read video metadata: {exc}",
                ) from exc
            _update_video_metadata(db, video, metadata)
            metadata_files.append(_write_json(job_dir / "video_metadata.json", _metadata_to_jsonable(metadata)))
            duration = float(metadata.duration or 0.0)
            if not metadata.has_audio:
                raise PipelineExpectedError(
                    "missing_audio",
                    "Video has no audio track. AutoClipper needs audio for transcription.",
                )

            _set_status(db, job, "extracting_audio")
            visited_statuses.append("extracting_audio")
            try:
                deps.extract_audio(input_path, audio_path)
            except Exception as exc:
                raise PipelineExpectedError(
                    "audio_extraction_failed",
                    f"Could not extract audio: {exc}",
                ) from exc

            silence_segments = _safe_silence_detection(audio_path, duration, detect_silence_for_audio)
            silence_path = write_silence_segments(silence_segments, silence_output_path(job_dir))
            metadata_files.append(silence_path)
            audio_features = _safe_audio_features(
                audio_path,
                duration,
                silence_segments,
                deps.compute_audio_features,
            )
            audio_features_path = write_audio_features(audio_features, audio_features_output_path(job_dir))
            metadata_files.append(audio_features_path)
            _raise_if_audio_unusable(audio_features)

            _set_status(db, job, "transcribing")
            visited_statuses.append("transcribing")
            if used_fixture_transcript:
                transcription_engine = "e2e_fixture"
                transcript_segments = _e2e_fixture_transcript(duration)
            else:
                transcription_engine = "faster_whisper"
                try:
                    transcript_segments = transcribe_audio(audio_path)
                except Exception as exc:
                    raise PipelineExpectedError(
                        "transcription_failed",
                        f"Could not transcribe audio: {exc}",
                    ) from exc
            transcript_path = write_transcript_segments(transcript_segments, transcript_output_path(job_dir))
            metadata_files.append(transcript_path)
            _raise_if_transcript_unusable(transcript_segments)

            _set_status(db, job, "detecting_scenes")
            visited_statuses.append("detecting_scenes")
            scene_segments = _safe_scene_detection(input_path, duration, deps.detect_scenes)
            scene_path = write_scene_segments(scene_segments, scene_output_path(job_dir))
            metadata_files.append(scene_path)
            visual_quality = _safe_visual_quality(input_path, duration, deps.detect_black_screen)
            visual_quality_path = write_visual_quality(visual_quality, visual_quality_output_path(job_dir))
            metadata_files.append(visual_quality_path)

            _set_status(db, job, "generating_candidates")
            visited_statuses.append("generating_candidates")
            try:
                normal_candidates = generate_normal_candidates(
                    transcript_segments,
                    scene_segments,
                    silence_segments,
                    settings=settings,
                )
                short_candidates = generate_short_candidates(
                    transcript_segments,
                    scene_segments,
                    silence_segments,
                    settings=settings,
                )
            except Exception as exc:
                raise PipelineExpectedError(
                    "candidate_generation_failed",
                    f"Could not generate clip candidates: {exc}",
                ) from exc
            all_candidates = [*normal_candidates, *short_candidates]
            metadata_files.extend(
                [
                    write_candidates(normal_candidates, job_dir / "normal_candidates.json"),
                    write_candidates(short_candidates, job_dir / "short_candidates.json"),
                    write_candidates(all_candidates, job_dir / "candidates.json"),
                ]
            )
            if not all_candidates:
                raise PipelineExpectedError(
                    "no_candidates_found",
                    "No clip candidates were found for the selected settings.",
                )

            _set_status(db, job, "scoring_candidates")
            visited_statuses.append("scoring_candidates")
            scored_candidates = _score_candidate_list(
                all_candidates,
                settings=settings,
                audio_features=audio_features,
                silence_segments=silence_segments,
                visual_quality=visual_quality,
                scorer=deps.openai_scorer,
            )
            metadata_files.append(write_candidates(scored_candidates, job_dir / "scored_candidates.json"))

            _set_status(db, job, "selecting_clips")
            visited_statuses.append("selecting_clips")
            selection = select_candidates(
                scored_candidates,
                settings=settings,
                audio_features=audio_features,
                silence_segments=silence_segments,
            )
            selected_path = write_selected_clips(selection, job_dir / "selected_clips.json")
            metadata_files.append(selected_path)

            _set_status(db, job, "rendering_normal_clips")
            visited_statuses.append("rendering_normal_clips")
            normal_result = render_selected_normal_candidates(
                db=db,
                job=job,
                input_path=input_path,
                selected_candidates=selection.normal_clips,
                transcript_segments=transcript_segments,
                burn_subtitles=bool(settings.get("burnSubtitles", True)),
                normalize_audio=bool(settings.get("normalizeAudio", False)),
                paths=storage_paths,
                renderer=deps.normal_renderer,
                normal_width=metadata.width or 1920,
                normal_height=metadata.height or 1080,
            )

            _set_status(db, job, "rendering_shorts")
            visited_statuses.append("rendering_shorts")
            short_result = render_selected_short_candidates(
                db=db,
                job=job,
                input_path=input_path,
                selected_candidates=selection.shorts,
                transcript_segments=transcript_segments,
                burn_subtitles=bool(settings.get("burnSubtitles", True)),
                normalize_audio=bool(settings.get("normalizeAudio", False)),
                layout=settings.get("shortLayout", settings.get("layout", "auto")),
                paths=storage_paths,
                renderer=deps.short_renderer,
                source_width=metadata.width,
                source_height=metadata.height,
            )

            render_failures_path = _write_json(
                job_dir / "render_failures.json",
                _render_failures_to_jsonable(normal_result, short_result),
            )
            metadata_files.append(render_failures_path)
            exports = [*normal_result.exports, *short_result.exports]
            summary_files = write_summaries()
            metadata_files.extend(path for path in summary_files if path not in metadata_files)
            if not exports:
                raise PipelineExpectedError(
                    "no_usable_output",
                    "Pipeline completed analysis but produced no usable clips.",
                )

            _set_status(db, job, "packaging_zip")
            visited_statuses.append("packaging_zip")
            _create_zip(storage_paths.zip_path(job.id), exports, metadata_files=metadata_files)

            _set_status(db, job, "completed")
            visited_statuses.append("completed")
        except PipelineExpectedError as exc:
            _fail_job(db, job_id, exc.code, exc.message, details=exc.details)
        except Exception as exc:
            _fail_job(db, job_id, "pipeline_failed", str(exc))
            raise
        finally:
            if not summary_files:
                try:
                    write_summaries()
                except Exception:
                    pass
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

    return visited_statuses
