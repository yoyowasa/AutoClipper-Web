import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio.extract import extract_mono_wav
from app.audio.openai_transcript_correction import (
    OpenAITranscriptCorrector,
    TranscriptCorrectionResult,
    correction_diff_output_path,
    correction_progress_output_path,
    correction_summary_output_path,
    deterministic_transcript_output_path,
    disabled_correction_result,
    fallback_correction_result,
    filter_failed_correction_result,
    write_corrected_transcript,
    write_correction_diff,
    write_correction_summary,
)
from app.audio.silence_detect import SilenceSegment, detect_silence, silence_output_path, write_silence_segments
from app.audio.transcript_postprocess import (
    DEFAULT_TRANSCRIPT_REPLACEMENTS,
    postprocess_transcript_segments,
    raw_transcript_output_path,
    transcript_postprocess_summary_path,
    write_transcript_postprocess_summary,
)
from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine,
    TranscriptSegment,
    transcript_output_path,
    write_transcript_segments,
)
from app.audio.transcription_runtime import (
    TRANSCRIPTION_COMPUTE_TYPES,
    TRANSCRIPTION_DEVICES,
    TranscriptionRuntimeError,
)
from app.audio.transcript_suspicion import (
    TranscriptSuspicionResult,
    analyze_transcript_suspicion,
    write_suspicion_artifacts,
    write_suspicion_failure_summary,
)
from app.audio.volume_features import AudioFeatures, audio_features_output_path, compute_audio_features, write_audio_features
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.boundary_refinement import refine_selected_candidates
from app.candidates.generate_normal_candidates import generate_normal_candidates_with_summary
from app.candidates.generate_short_candidates import generate_short_candidates_with_summary
from app.candidates.manual_ranges import (
    MANUAL_SELECTION_REASON,
    automatic_selection_settings,
    build_manual_candidates,
    manual_ranges_for_type,
    merge_manual_candidates_into_selection,
    validate_manual_ranges_for_duration,
)
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationMemoryLimitError,
    CandidateType,
    OpenAIScoreSource,
    merge_candidate_generation_summaries,
    write_candidates,
)
from app.candidates.select_candidates import (
    CandidateSelection,
    parse_selection_settings,
    select_candidates,
    write_selected_clips,
)
from app.candidates.title_fallback import titled_candidates
from app.db import SessionLocal
from app.ids import make_id
from app.jobs.clip_plan import (
    build_clip_plan,
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_awaiting_review,
    update_clip_plan_boundary,
    update_clip_plan_hook_scene,
    write_clip_plan,
)
from app.jobs.summaries import write_generation_summaries
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP, SUCCESS_STATUSES
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    apply_reviewed_text,
    build_subtitle_review,
    load_subtitle_review,
    mark_review_completed,
    mark_review_rendering,
    reviewed_transcript_output_path,
    restore_review_after_render_failure,
    subtitle_review_output_path,
    subtitle_review_preview_path,
    subtitle_review_preview_url,
    subtitle_review_summary_path,
    update_review_hook_scene,
    write_subtitle_review,
    write_subtitle_review_summary,
)
from app.models import ExportItem, Job, Video, utc_now
from app.render.render_normal import NormalRenderBatchResult, render_normal_clip, render_selected_normal_candidates
from app.render.render_review_preview import render_review_preview
from app.render.render_short import ShortRenderBatchResult, render_selected_short_candidates, render_short_clip
from app.scoring.openai_score import OpenAICandidateScorer, score_candidate_batch
from app.scoring.clip_preferences import build_clip_selection_preferences
from app.scoring.quality_gate import evaluate_hard_gate
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
MAX_AV_STREAM_DURATION_DRIFT_SECONDS = 30.0
MAX_AV_STREAM_DURATION_DRIFT_RATIO = 0.1

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
DEFAULT_OPENAI_CANDIDATE_LIMIT = 40


@dataclass(frozen=True)
class ScoringResult:
    candidates: list[Candidate]
    openai_summary: dict[str, Any] | None = None
    openai_scorer: Any | None = None


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
    subtitle_review_preview_renderer: Callable[..., Path] = render_review_preview
    openai_scorer: OpenAICandidateScorer | None = None
    transcript_corrector: OpenAITranscriptCorrector | None = None


class PipelineExpectedError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


WHISPER_MODEL_SIZES = {"base", "small", "medium", "large-v3", "turbo"}
TRANSCRIPTION_LANGUAGES = {"auto", "ja"}
SUBTITLE_CORRECTION_REASONING_EFFORTS = {
    "default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}


def _whisper_model_size_setting(settings: dict[str, Any]) -> str:
    value = settings.get("whisperModelSize") or settings.get("whisper_model_size") or "base"
    normalized = str(value).strip()
    return normalized if normalized in WHISPER_MODEL_SIZES else "base"


def _transcription_language_setting(settings: dict[str, Any]) -> str:
    value = settings.get("transcriptionLanguage") or settings.get("transcription_language") or "auto"
    normalized = str(value).strip().lower()
    return normalized if normalized in TRANSCRIPTION_LANGUAGES else "auto"


def _transcription_device_setting(settings: dict[str, Any]) -> str:
    value = settings.get("transcriptionDevice") or settings.get("transcription_device") or "cpu"
    normalized = str(value).strip().lower()
    return normalized if normalized in TRANSCRIPTION_DEVICES else "cpu"


def _transcription_compute_type_setting(settings: dict[str, Any]) -> str:
    value = settings.get("transcriptionComputeType") or settings.get("transcription_compute_type") or "auto"
    normalized = str(value).strip().lower()
    return normalized if normalized in TRANSCRIPTION_COMPUTE_TYPES else "auto"


def _subtitle_correction_mode_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionMode") or settings.get("subtitle_correction_mode") or "off"
    normalized = str(value).strip().lower()
    return normalized if normalized in {"off", "openai"} else "off"


def _subtitle_correction_model_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionModel") or settings.get("subtitle_correction_model") or "gpt-5.5"
    normalized = str(value).strip()
    return normalized or "gpt-5.5"


def _subtitle_correction_reasoning_effort_setting(settings: dict[str, Any]) -> str:
    value = (
        settings.get("subtitleCorrectionReasoningEffort")
        or settings.get("subtitle_correction_reasoning_effort")
        or "default"
    )
    normalized = str(value).strip().lower()
    return normalized if normalized in SUBTITLE_CORRECTION_REASONING_EFFORTS else "default"


def _subtitle_correction_batch_size_setting(settings: dict[str, Any]) -> int:
    return max(1, min(100, _int_setting(settings, "subtitleCorrectionBatchSize", 40)))


def _subtitle_correction_scope_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionScope") or settings.get("subtitle_correction_scope") or "all"
    normalized = str(value).strip().lower()
    return normalized if normalized in {"all", "suspicious"} else "all"


def _float_setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def _transcript_correction_glossary(settings: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    if _bool_setting(settings, "useDefaultTranscriptDictionary", True):
        terms.extend(DEFAULT_TRANSCRIPT_REPLACEMENTS.values())
    replacements = settings.get("transcriptReplacements")
    if isinstance(replacements, dict):
        terms.extend(str(value).strip() for value in replacements.values())
    custom_glossary = settings.get("transcriptCorrectionGlossary")
    if isinstance(custom_glossary, list):
        terms.extend(str(term).strip() for term in custom_glossary)
    return list(dict.fromkeys(term for term in terms if term))


def _apply_transcript_correction(
    segments: Sequence[TranscriptSegment],
    settings: dict[str, Any],
    *,
    corrector: OpenAITranscriptCorrector | None = None,
    target_indices: Sequence[int] | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> TranscriptCorrectionResult:
    mode = _subtitle_correction_mode_setting(settings)
    model = _subtitle_correction_model_setting(settings)
    if mode == "off":
        return disabled_correction_result(segments, model)
    needs_api_call = target_indices is None or bool(target_indices)
    if corrector is None and needs_api_call and not os.getenv("OPENAI_API_KEY"):
        raise PipelineExpectedError(
            "openai_configuration_missing",
            "OPENAI_API_KEY is required when subtitleCorrectionMode is openai.",
            details={"setting": "OPENAI_API_KEY", "feature": "subtitle_correction"},
        )

    active_corrector = corrector or OpenAITranscriptCorrector(
        model=model,
        reasoning_effort=_subtitle_correction_reasoning_effort_setting(settings),
    )
    min_confidence = max(0.0, min(1.0, _float_setting(settings, "subtitleCorrectionMinConfidence", 0.9)))
    batch_size = _subtitle_correction_batch_size_setting(settings)
    context_segments = min(10, _int_setting(settings, "subtitleCorrectionContextSegments", 2))
    try:
        return active_corrector.correct_segments(
            segments,
            min_confidence=min_confidence,
            batch_size=batch_size,
            context_segments=context_segments,
            glossary=_transcript_correction_glossary(settings),
            target_indices=target_indices,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        if _bool_setting(settings, "subtitleCorrectionFallbackEnabled", True):
            return fallback_correction_result(segments, active_corrector, exc)
        raise PipelineExpectedError(
            "openai_subtitle_correction_failed",
            f"OpenAI subtitle correction failed: {exc}",
            details={
                "model": model,
                "reasoning_effort": _subtitle_correction_reasoning_effort_setting(settings),
                "fallback_enabled": False,
            },
        ) from exc


def _truthy_setting(settings: dict[str, Any], key: str) -> bool:
    value = settings.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _bool_setting(settings: dict[str, Any], key: str, default: bool) -> bool:
    if key not in settings:
        return default
    value = settings.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _openai_model_setting(settings: dict[str, Any]) -> str:
    value = settings.get("openaiModel") or settings.get("openai_model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "gpt-5.5"


def _openai_enabled(settings: dict[str, Any]) -> bool:
    return bool(
        settings.get("useOpenAIScoring")
        or settings.get("openaiScoring")
        or settings.get("enableOpenAIScoring")
    )


def _ensure_selected_openai_scored(settings: dict[str, Any]) -> bool:
    if "ensureSelectedOpenAIScored" in settings:
        return _bool_setting(settings, "ensureSelectedOpenAIScored", False)
    if "ensure_selected_openai_scored" in settings:
        return _bool_setting(settings, "ensure_selected_openai_scored", False)
    return settings.get("mode") == "high_quality"


def _requested_output_count(settings: dict[str, Any]) -> int:
    parsed = parse_selection_settings(settings)
    return parsed.normal_clip_count + parsed.short_count


def _openai_finalist_scoring_limit(settings: dict[str, Any]) -> int:
    requested_count = _requested_output_count(settings)
    default = requested_count + 2 if requested_count > 0 else 0
    return _int_setting(settings, "openaiFinalistScoringLimit", default)


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
    job.updated_at = utc_now()
    if status != "failed":
        job.error_code = None
        job.error_message = None
    db.commit()
    db.refresh(job)


def _heartbeat_job(db: Session, job: Job) -> None:
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)


def _set_subtitle_review_preview_progress(
    db: Session,
    job: Job,
    *,
    completed: int,
    total: int,
) -> None:
    bounded_total = max(1, total)
    bounded_completed = max(0, min(completed, bounded_total))
    job.status = "preparing_subtitle_review"
    job.progress = 74 + int(3 * bounded_completed / bounded_total)
    job.current_step = f"字幕確認用動画を準備中 ({bounded_completed}/{total})"
    job.updated_at = utc_now()
    job.error_code = None
    job.error_message = None
    db.commit()
    db.refresh(job)


def _set_clip_plan_preview_progress(
    db: Session,
    job: Job,
    *,
    completed: int,
    total: int,
) -> None:
    bounded_total = max(1, total)
    bounded_completed = max(0, min(completed, bounded_total))
    job.status = "preparing_clip_review"
    job.progress = 73 + int(2 * bounded_completed / bounded_total)
    job.current_step = (
        f"切り抜き予定の確認動画を準備中 ({bounded_completed}/{total})"
    )
    job.updated_at = utc_now()
    job.error_code = None
    job.error_message = None
    db.commit()
    db.refresh(job)


def _record_subtitle_correction_progress(
    db: Session,
    job: Job,
    output_path: Path,
    *,
    completed_batches: int,
    total_batches: int,
    retry_count: int,
    target_segments_completed: int = 0,
    target_segments_total: int = 0,
    transcript_segment_count: int = 0,
    finished: bool = False,
    fallback_used: bool = False,
) -> None:
    bounded_total = max(0, total_batches)
    bounded_completed = max(0, min(completed_batches, bounded_total))
    stage_progress = 100 if finished else (100 if bounded_total == 0 else int(bounded_completed * 100 / bounded_total))
    payload = {
        "stage": "correcting_subtitles",
        "stageProgress": stage_progress,
        "correctionBatchesCompleted": bounded_completed,
        "correctionBatchesTotal": bounded_total,
        "correctionRetryCount": max(0, retry_count),
        "correctionTargetsCompleted": max(0, min(target_segments_completed, target_segments_total)),
        "correctionTargetsTotal": max(0, target_segments_total),
        "transcriptSegmentCount": max(0, transcript_segment_count),
        "fallbackUsed": fallback_used,
        "finished": finished,
    }
    _write_json(output_path, payload)
    job.status = "correcting_subtitles"
    job.progress = min(39, PROGRESS_MAP["correcting_subtitles"] + int(stage_progress * 8 / 100))
    job.current_step = f"Correcting subtitles ({bounded_completed}/{bounded_total} batches)"
    job.updated_at = utc_now()
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
    job.updated_at = utc_now()
    db.commit()


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _metadata_to_jsonable(metadata: VideoMetadata) -> dict[str, Any]:
    return {
        "duration": metadata.duration,
        "video_stream_duration": metadata.video_stream_duration,
        "audio_stream_duration": metadata.audio_stream_duration,
        "container_duration": metadata.container_duration,
        "width": metadata.width,
        "height": metadata.height,
        "fps": metadata.fps,
        "has_audio": metadata.has_audio,
    }


def _format_media_duration(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _raise_if_stream_durations_mismatch(metadata: VideoMetadata) -> None:
    video_duration = metadata.video_stream_duration
    audio_duration = metadata.audio_stream_duration
    if not video_duration or not audio_duration:
        return

    difference = abs(video_duration - audio_duration)
    relative_difference = difference / max(1.0, min(video_duration, audio_duration))
    if (
        difference <= MAX_AV_STREAM_DURATION_DRIFT_SECONDS
        or relative_difference <= MAX_AV_STREAM_DURATION_DRIFT_RATIO
    ):
        return

    raise PipelineExpectedError(
        "media_stream_duration_mismatch",
        (
            "動画ファイルの映像と音声の長さが一致しません"
            f"（映像 {_format_media_duration(video_duration)} / "
            f"音声 {_format_media_duration(audio_duration)}）。"
            "ファイルが破損または不完全にダウンロードされています。"
            "元動画を再ダウンロードして、再アップロードしてください。"
        ),
    )


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


def _openai_summary(
    scorer: Any,
    *,
    candidate_limit: int,
    candidates_considered: int,
    skipped_due_to_limit: int,
    fallback_scores: int,
    rule_score_only_candidates: int,
    candidates_sent: int,
    initial_candidate_limit: int | None = None,
    finalist_scoring_limit: int | None = None,
    preselection_candidates_sent: int | None = None,
    finalist_candidates_sent: int = 0,
) -> dict[str, Any]:
    stats = getattr(scorer, "stats", None)
    if stats is not None and hasattr(stats, "to_summary"):
        summary = stats.to_summary(
            candidate_limit=candidate_limit,
            candidates_considered=candidates_considered,
            skipped_due_to_limit=skipped_due_to_limit,
            fallback_scores=fallback_scores,
            rule_score_only_candidates=rule_score_only_candidates,
            candidates_selected_for_openai=candidates_sent,
        )
    else:
        summary = {
            "model": getattr(scorer, "model", "unknown"),
            "candidate_limit": candidate_limit,
            "candidates_considered": candidates_considered,
            "candidates_eligible_for_openai_scoring": candidates_considered,
            "candidates_selected_for_openai": candidates_sent,
            "candidates_sent_to_openai": candidates_sent,
            "candidates_actually_sent": candidates_sent,
            "successful_scores": 0,
            "successful_structured_scores": 0,
            "failed_scores": fallback_scores,
            "failed_structured_scores": fallback_scores,
            "fallback_scores": fallback_scores,
            "rule_score_only_candidates": rule_score_only_candidates,
            "skipped_due_to_limit": skipped_due_to_limit,
            "cache_hits": 0,
            "average_latency_seconds": None,
            "avg_latency_seconds": None,
            "max_latency_seconds": None,
            "total_latency_seconds": None,
            "estimated_input_text_length": None,
            "estimated_output_text_length": None,
            "estimated_text_payload_size": None,
            "total_api_calls": None,
            "schema_validation_failures": 0,
            "error_types": {},
            "errors": ["scorer did not expose runtime stats"],
        }
    summary["initial_candidate_limit"] = initial_candidate_limit if initial_candidate_limit is not None else candidate_limit
    summary["finalist_scoring_limit"] = finalist_scoring_limit
    summary["candidates_sent_preselection"] = (
        preselection_candidates_sent if preselection_candidates_sent is not None else candidates_sent
    )
    summary["candidates_sent_as_finalists"] = finalist_candidates_sent
    return summary


def _candidate_rank_value(candidate: Candidate) -> tuple[float, float, float, int, float]:
    return (
        float(candidate.rule_score or candidate.final_score or 0.0),
        float(candidate.final_score or candidate.rule_score or 0.0),
        -candidate.duration,
        len(candidate.transcript_text),
        -candidate.start,
    )


def _candidate_midpoint(candidate: Candidate) -> float:
    return (candidate.start + candidate.end) / 2


def _openai_cluster_ids(candidates: Sequence[Candidate], requested_count: int) -> dict[str, int]:
    if not candidates:
        return {}
    min_start = min(candidate.start for candidate in candidates)
    max_end = max(candidate.end for candidate in candidates)
    span = max(max_end - min_start, 1.0)
    bucket_count = max(requested_count * 3, 1)
    bucket_size = max(60.0, span / bucket_count)
    return {candidate.id: int(_candidate_midpoint(candidate) // bucket_size) for candidate in candidates}


def _openai_cluster_diverse_order(candidates: Sequence[Candidate], requested_count: int) -> list[Candidate]:
    cluster_ids = _openai_cluster_ids(candidates, requested_count)
    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(cluster_ids.get(candidate.id, 0), []).append(candidate)
    for items in grouped.values():
        items.sort(key=_candidate_rank_value, reverse=True)

    cluster_order = sorted(
        grouped,
        key=lambda cluster: (
            _candidate_rank_value(grouped[cluster][0])
            if grouped[cluster]
            else (0.0, 0.0, 0.0, 0, 0.0)
        ),
        reverse=True,
    )
    ordered: list[Candidate] = []
    while any(grouped[cluster] for cluster in cluster_order):
        for cluster in cluster_order:
            if grouped[cluster]:
                ordered.append(grouped[cluster].pop(0))
    return ordered


def _append_openai_pool_candidates(
    pool: list[Candidate],
    candidates: Sequence[Candidate],
    limit: int,
    *,
    max_overlap_ratio: float,
) -> None:
    for candidate in candidates:
        if len(pool) >= limit:
            return
        if any(item.id == candidate.id for item in pool):
            continue
        if any(time_overlap_ratio(candidate, selected) >= max_overlap_ratio for selected in pool):
            continue
        pool.append(candidate)


def _openai_type_budgets(
    normal_candidates: Sequence[Candidate],
    short_candidates: Sequence[Candidate],
    settings: dict[str, Any],
    limit: int,
) -> dict[CandidateType, int]:
    if limit <= 0:
        return {"normal": 0, "short": 0}
    parsed = parse_selection_settings(settings)
    requested_normal = parsed.normal_clip_count if normal_candidates else 0
    requested_short = parsed.short_count if short_candidates else 0
    requested_total = requested_normal + requested_short
    if requested_total <= 0:
        normal_budget = limit // 2 if normal_candidates and short_candidates else limit
    else:
        normal_budget = round(limit * (requested_normal / requested_total)) if requested_normal > 0 else 0
    if normal_candidates and requested_normal > 0 and normal_budget == 0:
        normal_budget = 1
    if short_candidates and requested_short > 0 and limit - normal_budget == 0:
        normal_budget = max(0, normal_budget - 1)
    short_budget = limit - normal_budget
    normal_budget = min(normal_budget, len(normal_candidates))
    short_budget = min(short_budget, len(short_candidates))
    leftover = limit - normal_budget - short_budget
    if leftover > 0 and len(normal_candidates) > normal_budget:
        add = min(leftover, len(normal_candidates) - normal_budget)
        normal_budget += add
        leftover -= add
    if leftover > 0 and len(short_candidates) > short_budget:
        short_budget += min(leftover, len(short_candidates) - short_budget)
    return {"normal": normal_budget, "short": short_budget}


def _build_openai_scoring_pool(
    candidates: Sequence[Candidate],
    settings: dict[str, Any],
    audio_features: AudioFeatures,
    silence_segments: Sequence[SilenceSegment],
    candidate_limit: int,
) -> list[Candidate]:
    if candidate_limit <= 0:
        return []
    selection_settings = parse_selection_settings(settings)
    hard_gate_passed = [
        candidate
        for candidate in candidates
        if evaluate_hard_gate(
            candidate,
            settings=selection_settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        ).passed
    ]
    normal_candidates = [candidate for candidate in hard_gate_passed if candidate.type == "normal"]
    short_candidates = [candidate for candidate in hard_gate_passed if candidate.type == "short"]
    budgets = _openai_type_budgets(normal_candidates, short_candidates, settings, candidate_limit)
    selected: list[Candidate] = []
    for candidate_type, type_candidates in (("normal", normal_candidates), ("short", short_candidates)):
        budget = budgets[candidate_type]
        ordered = _openai_cluster_diverse_order(
            sorted(type_candidates, key=_candidate_rank_value, reverse=True),
            max(budget, 1),
        )
        type_pool: list[Candidate] = []
        _append_openai_pool_candidates(
            type_pool,
            ordered,
            budget,
            max_overlap_ratio=selection_settings.max_overlap_ratio,
        )
        if len(type_pool) < budget:
            _append_openai_pool_candidates(
                type_pool,
                ordered,
                budget,
                max_overlap_ratio=1.01,
            )
        selected.extend(type_pool)
    if len(selected) < candidate_limit:
        selected_ids = {candidate.id for candidate in selected}
        remaining = [
            candidate for candidate in _openai_cluster_diverse_order(hard_gate_passed, candidate_limit)
            if candidate.id not in selected_ids
        ]
        _append_openai_pool_candidates(
            selected,
            remaining,
            candidate_limit,
            max_overlap_ratio=selection_settings.max_overlap_ratio,
        )
        if len(selected) < candidate_limit:
            _append_openai_pool_candidates(
                selected,
                remaining,
                candidate_limit,
                max_overlap_ratio=1.01,
            )
    return selected[:candidate_limit]


def _candidate_with_openai_source(candidate: Candidate, source: OpenAIScoreSource) -> Candidate:
    flags = [flag for flag in candidate.risk_flags if flag != "openai_not_scored_candidate_limit"]
    fallback = "openai_fallback_rule_score" in flags
    used_ai_score = candidate.ai_score is not None and not fallback
    openai_source = "fallback_rule_score" if fallback else source
    return candidate.model_copy(
        update={
            "risk_flags": flags,
            "used_ai_score": used_ai_score,
            "openai_scored": used_ai_score,
            "openai_fallback_used": fallback,
            "openai_score_source": openai_source,
            "openai_not_scored_reason": None,
        }
    )


def _candidate_not_scored(candidate: Candidate, reason: str) -> Candidate:
    flags = list(candidate.risk_flags)
    if "openai_not_scored_candidate_limit" not in flags:
        flags.append("openai_not_scored_candidate_limit")
    return candidate.model_copy(
        update={
            "final_score": candidate.rule_score,
            "risk_flags": flags,
            "used_ai_score": False,
            "openai_scored": False,
            "openai_fallback_used": False,
            "openai_score_source": "not_scored",
            "openai_not_scored_reason": reason,
        }
    )


def _fallback_candidate(candidate: Candidate, source: OpenAIScoreSource) -> Candidate:
    flags = [flag for flag in candidate.risk_flags if flag != "openai_scoring_failed"]
    if "openai_fallback_rule_score" not in flags:
        flags.append("openai_fallback_rule_score")
    return candidate.model_copy(
        update={
            "ai_score": None,
            "final_score": candidate.rule_score,
            "should_use": None,
            "reject_reason": None,
            "reason": "OpenAI scoring failed; used rule score fallback.",
            "risk_flags": flags,
            "used_ai_score": False,
            "openai_scored": False,
            "openai_fallback_used": True,
            "openai_score_source": "fallback_rule_score",
            "openai_not_scored_reason": source,
        }
    )


def _replace_scored_candidates(
    candidates: Sequence[Candidate],
    replacements: dict[str, Candidate],
) -> list[Candidate]:
    return [replacements.get(candidate.id, candidate) for candidate in candidates]


def _score_candidate_list(
    candidates: Sequence[Candidate],
    settings: dict[str, Any],
    audio_features: AudioFeatures,
    silence_segments: Sequence[SilenceSegment],
    visual_quality: VisualQuality,
    scorer: OpenAICandidateScorer | None,
) -> ScoringResult:
    selection_preferences = build_clip_selection_preferences(settings)
    rule_scored = score_candidates(
        candidates,
        audio_features=audio_features,
        silence_segments=silence_segments,
        selection_preferences=selection_preferences,
    )
    use_openai = _openai_enabled(settings)
    if not use_openai:
        return ScoringResult(
            candidates=[candidate.model_copy(update={"final_score": candidate.rule_score}) for candidate in rule_scored]
        )

    if scorer is None and not os.getenv("OPENAI_API_KEY"):
        raise PipelineExpectedError(
            "openai_configuration_missing",
            "OPENAI_API_KEY is required when useOpenAIScoring is true.",
            details={"setting": "OPENAI_API_KEY"},
        )

    fallback_enabled = _bool_setting(settings, "openaiFallbackToRuleScore", True)
    candidate_limit = _int_setting(settings, "openaiCandidateLimit", DEFAULT_OPENAI_CANDIDATE_LIMIT)
    active_scorer = scorer or OpenAICandidateScorer(
        model=_openai_model_setting(settings),
        selection_preferences=selection_preferences,
    )
    if scorer is not None and hasattr(active_scorer, "selection_preferences"):
        active_scorer.selection_preferences = selection_preferences
    ranked_for_openai = _build_openai_scoring_pool(
        rule_scored,
        settings=settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
        candidate_limit=candidate_limit,
    )
    candidates_for_openai = ranked_for_openai if candidate_limit > 0 else []
    openai_candidate_ids = {candidate.id for candidate in candidates_for_openai}
    skipped_due_to_limit = max(0, len(rule_scored) - len(candidates_for_openai))
    scored_by_id: dict[str, Candidate] = {}
    fallback_scores = 0

    try:
        openai_scored = score_candidate_batch(
            candidates_for_openai,
            scorer=active_scorer,
            audio_features=audio_features,
            visual_features=visual_quality,
        )
    except Exception as exc:
        if not fallback_enabled:
            summary = _openai_summary(
                active_scorer,
                candidate_limit=candidate_limit,
                candidates_considered=len(rule_scored),
                skipped_due_to_limit=skipped_due_to_limit,
                fallback_scores=0,
                rule_score_only_candidates=skipped_due_to_limit,
                candidates_sent=len(candidates_for_openai),
                initial_candidate_limit=candidate_limit,
                finalist_scoring_limit=_openai_finalist_scoring_limit(settings),
                preselection_candidates_sent=len(candidates_for_openai),
            )
            raise PipelineExpectedError(
                "openai_scoring_failed",
                f"OpenAI scoring failed: {exc}",
                details=summary,
            ) from exc
        openai_scored = [
            candidate.model_copy(
                update={
                    "final_score": candidate.rule_score,
                    "should_use": None,
                    "reject_reason": None,
                    "reason": "OpenAI scoring failed; used rule score fallback.",
                    "risk_flags": [*candidate.risk_flags, "openai_fallback_rule_score"],
                }
            )
            for candidate in candidates_for_openai
        ]
        fallback_scores = len(candidates_for_openai)

    failed_candidates = [
        candidate for candidate in openai_scored if "openai_scoring_failed" in candidate.risk_flags
    ]
    if failed_candidates and not fallback_enabled:
        summary = _openai_summary(
            active_scorer,
            candidate_limit=candidate_limit,
            candidates_considered=len(rule_scored),
                skipped_due_to_limit=skipped_due_to_limit,
                fallback_scores=0,
                rule_score_only_candidates=skipped_due_to_limit,
                candidates_sent=len(candidates_for_openai),
                initial_candidate_limit=candidate_limit,
                finalist_scoring_limit=_openai_finalist_scoring_limit(settings),
                preselection_candidates_sent=len(candidates_for_openai),
            )
        raise PipelineExpectedError(
            "openai_scoring_failed",
            "OpenAI scoring failed for one or more candidates.",
            details={
                **summary,
                "failed_candidate_ids": [candidate.id for candidate in failed_candidates[:20]],
            },
        )

    for candidate in openai_scored:
        if "openai_scoring_failed" not in candidate.risk_flags:
            scored_by_id[candidate.id] = _candidate_with_openai_source(candidate, "preselection_pool")
            continue
        fallback_scores += 1
        scored_by_id[candidate.id] = _fallback_candidate(candidate, "preselection_pool")

    merged: list[Candidate] = []
    for candidate in rule_scored:
        if candidate.id in scored_by_id:
            merged.append(scored_by_id[candidate.id])
            continue
        reason = "candidate_limit" if openai_candidate_ids else "openai_candidate_limit_zero"
        merged.append(_candidate_not_scored(candidate, reason))

    summary = _openai_summary(
        active_scorer,
        candidate_limit=candidate_limit,
        candidates_considered=len(rule_scored),
        skipped_due_to_limit=skipped_due_to_limit,
        fallback_scores=fallback_scores,
        rule_score_only_candidates=skipped_due_to_limit,
        candidates_sent=len(candidates_for_openai),
        initial_candidate_limit=candidate_limit,
        finalist_scoring_limit=_openai_finalist_scoring_limit(settings),
        preselection_candidates_sent=len(candidates_for_openai),
    )
    summary["preselection_candidate_ids"] = [candidate.id for candidate in candidates_for_openai]
    summary["preselection_candidate_types"] = dict(Counter(candidate.type for candidate in candidates_for_openai))
    return ScoringResult(candidates=merged, openai_summary=summary, openai_scorer=active_scorer)


def _selected_candidates(selection: CandidateSelection) -> list[Candidate]:
    return [*selection.normal_clips, *selection.shorts]


def _selection_with_replacements(
    selection: CandidateSelection,
    replacements: dict[str, Candidate],
) -> CandidateSelection:
    normal_clips = [replacements.get(candidate.id, candidate) for candidate in selection.normal_clips]
    shorts = [replacements.get(candidate.id, candidate) for candidate in selection.shorts]
    selected = [*normal_clips, *shorts]
    return selection.model_copy(
        update={
            "normal_clips": normal_clips,
            "shorts": shorts,
            "selected_above_threshold_count": sum(
                1 for candidate in selected if candidate.below_quality_threshold is False
            ),
            "selected_below_threshold_backfill_count": sum(
                1 for candidate in selected if candidate.below_quality_threshold is True
            ),
        }
    )


def _selection_with_fallback_titles(
    selection: CandidateSelection,
    scored_candidates: Sequence[Candidate],
    transcript_segments: Sequence[TranscriptSegment],
) -> tuple[CandidateSelection, list[Candidate]]:
    normal_clips = titled_candidates(selection.normal_clips, transcript_segments=transcript_segments)
    shorts = titled_candidates(selection.shorts, transcript_segments=transcript_segments)
    replacements = {candidate.id: candidate for candidate in [*normal_clips, *shorts]}
    return (
        selection.model_copy(update={"normal_clips": normal_clips, "shorts": shorts}),
        _replace_scored_candidates(scored_candidates, replacements),
    )


def _selection_with_refined_boundaries(
    selection: CandidateSelection,
    scored_candidates: Sequence[Candidate],
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    settings: dict[str, Any],
    timeline_duration: float,
) -> tuple[CandidateSelection, list[Candidate]]:
    def refine_unlocked(candidates: Sequence[Candidate]) -> list[Candidate]:
        unlocked = [
            candidate
            for candidate in candidates
            if candidate.selection_reason != MANUAL_SELECTION_REASON
        ]
        refined = refine_selected_candidates(
            unlocked,
            transcript_segments=transcript_segments,
            silence_segments=silence_segments,
            scene_segments=scene_segments,
            settings=settings,
            timeline_duration=timeline_duration,
        )
        replacements = {candidate.id: candidate for candidate in refined}
        return [replacements.get(candidate.id, candidate) for candidate in candidates]

    normal_clips = refine_unlocked(selection.normal_clips)
    shorts = refine_unlocked(selection.shorts)
    replacements = {candidate.id: candidate for candidate in [*normal_clips, *shorts]}
    return (
        selection.model_copy(update={"normal_clips": normal_clips, "shorts": shorts}),
        _replace_scored_candidates(scored_candidates, replacements),
    )


def _candidate_needs_finalist_scoring(candidate: Candidate) -> bool:
    if candidate.used_ai_score is True and candidate.ai_score is not None:
        return False
    if candidate.openai_fallback_used is True:
        return False
    return True


def _candidate_with_final_quality_metadata(candidate: Candidate, settings: dict[str, Any]) -> Candidate:
    min_final_score = parse_selection_settings(settings).quality_gate.min_final_score
    score = candidate.final_score if candidate.final_score is not None else candidate.rule_score
    below_threshold = score is not None and float(score) < min_final_score
    return candidate.model_copy(
        update={
            "below_quality_threshold": below_threshold,
            "quality_warning": "below_min_final_score" if below_threshold else None,
        }
    )


def _ensure_selected_candidates_openai_scored(
    selection: CandidateSelection,
    scored_candidates: Sequence[Candidate],
    settings: dict[str, Any],
    audio_features: AudioFeatures,
    visual_quality: VisualQuality,
    scorer: Any | None,
    openai_summary: dict[str, Any] | None,
) -> tuple[CandidateSelection, list[Candidate], dict[str, Any] | None]:
    if not (_openai_enabled(settings) and _ensure_selected_openai_scored(settings)):
        return selection, list(scored_candidates), openai_summary
    if scorer is None or openai_summary is None:
        return selection, list(scored_candidates), openai_summary

    selected = _selected_candidates(selection)
    needs_scoring = [candidate for candidate in selected if _candidate_needs_finalist_scoring(candidate)]
    finalist_limit = _openai_finalist_scoring_limit(settings)
    finalists = needs_scoring[:finalist_limit] if finalist_limit > 0 else []
    not_scored_due_to_limit = needs_scoring[len(finalists):]
    fallback_enabled = _bool_setting(settings, "openaiFallbackToRuleScore", True)
    replacements: dict[str, Candidate] = {
        candidate.id: _candidate_not_scored(candidate, "finalist_scoring_limit")
        for candidate in not_scored_due_to_limit
    }
    finalist_fallback_scores = 0

    try:
        finalist_scored = score_candidate_batch(
            finalists,
            scorer=scorer,
            audio_features=audio_features,
            visual_features=visual_quality,
        )
    except Exception as exc:
        if not fallback_enabled:
            summary = dict(openai_summary)
            summary["finalist_candidate_ids"] = [candidate.id for candidate in finalists]
            summary["candidates_sent_as_finalists"] = len(finalists)
            raise PipelineExpectedError(
                "openai_scoring_failed",
                f"OpenAI finalist scoring failed: {exc}",
                details=summary,
            ) from exc
        finalist_scored = [_fallback_candidate(candidate, "finalist_on_demand") for candidate in finalists]
        finalist_fallback_scores = len(finalists)

    failed_finalists = [
        candidate for candidate in finalist_scored if "openai_scoring_failed" in candidate.risk_flags
    ]
    if failed_finalists and not fallback_enabled:
        summary = dict(openai_summary)
        summary["finalist_candidate_ids"] = [candidate.id for candidate in finalists]
        summary["failed_finalist_candidate_ids"] = [candidate.id for candidate in failed_finalists]
        summary["candidates_sent_as_finalists"] = len(finalists)
        raise PipelineExpectedError(
            "openai_scoring_failed",
            "OpenAI finalist scoring failed for one or more selected candidates.",
            details=summary,
        )

    for candidate in finalist_scored:
        if "openai_scoring_failed" in candidate.risk_flags:
            finalist_fallback_scores += 1
            replacements[candidate.id] = _fallback_candidate(candidate, "finalist_on_demand")
            continue
        replacements[candidate.id] = _candidate_with_openai_source(candidate, "finalist_on_demand")
    replacements = {
        candidate_id: _candidate_with_final_quality_metadata(candidate, settings)
        for candidate_id, candidate in replacements.items()
    }

    updated_selection = _selection_with_replacements(selection, replacements)
    updated_candidates = _replace_scored_candidates(scored_candidates, replacements)

    initial_limit = int(openai_summary.get("initial_candidate_limit") or openai_summary.get("candidate_limit") or 0)
    candidates_considered = int(openai_summary.get("candidates_considered") or len(scored_candidates))
    preselection_sent = int(openai_summary.get("candidates_sent_preselection") or 0)
    previous_fallback = int(openai_summary.get("fallback_scores") or 0)
    previous_rule_only = int(openai_summary.get("rule_score_only_candidates") or 0)
    previous_skipped = int(openai_summary.get("skipped_due_to_limit") or 0)
    updated_summary = _openai_summary(
        scorer,
        candidate_limit=initial_limit,
        candidates_considered=candidates_considered,
        skipped_due_to_limit=max(0, previous_skipped - len(finalists)),
        fallback_scores=previous_fallback + finalist_fallback_scores,
        rule_score_only_candidates=max(0, previous_rule_only - len(finalists)),
        candidates_sent=preselection_sent + len(finalists),
        initial_candidate_limit=initial_limit,
        finalist_scoring_limit=finalist_limit,
        preselection_candidates_sent=preselection_sent,
        finalist_candidates_sent=len(finalists),
    )
    updated_summary = {
        **openai_summary,
        **updated_summary,
        "finalist_candidate_ids": [candidate.id for candidate in finalists],
        "finalist_candidate_types": dict(Counter(candidate.type for candidate in finalists)),
        "finalist_not_scored_due_to_limit_ids": [candidate.id for candidate in not_scored_due_to_limit],
    }
    return updated_selection, updated_candidates, updated_summary


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


def _zip_type_dir(export_type: str) -> str:
    return "shorts" if export_type == "short" else "normal"


def _zip_export_arcname(export: ExportItem, path: Path, source_value: str) -> str:
    type_dir = _zip_type_dir(export.type)
    if source_value == export.video_path:
        return f"videos/{type_dir}/{path.name}"
    if source_value == export.subtitle_path:
        return f"subtitles/{type_dir}/{path.name}"
    if source_value == export.metadata_path:
        return f"metadata/{type_dir}/{path.name}"
    return f"metadata/{path.name}"


def _create_zip(zip_path: Path, exports: Sequence[ExportItem], metadata_files: Sequence[Path] | None = None) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for export in exports:
            for value in (export.video_path, export.subtitle_path, export.metadata_path):
                if not value:
                    continue
                path = Path(value)
                if path.is_file():
                    archive.write(path, arcname=_zip_export_arcname(export, path, value))
        for metadata_file in metadata_files or []:
            if metadata_file.is_file():
                archive.write(metadata_file, arcname=f"metadata/{metadata_file.name}")


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
    title_prefix = "Normal Clip" if export_type == "normal" else "Short"
    title = f"{title_prefix} {index:02d}"
    export_id = make_id("exp")
    video_path = output_dir / f"{export_type}_{index:02d}.mp4"
    metadata_path = output_dir / f"{export_type}_{index:02d}.json"
    _write_placeholder_mp4(video_path, title)
    _write_json(
        metadata_path,
        {
            "id": export_id,
            "type": export_type,
            "title": title,
            "title_source": "deterministic_fallback",
        },
    )

    export = ExportItem(
        id=export_id,
        job_id=job.id,
        video_id=job.video_id,
        candidate_id=None,
        type=export_type,
        title=title,
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


def _render_selected_outputs(
    *,
    db: Session,
    job: Job,
    video: Video,
    input_path: Path,
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    settings: dict[str, Any],
    storage_paths: StoragePaths,
    dependencies: AutoClipperPipelineDependencies,
    visited_statuses: list[str],
) -> tuple[NormalRenderBatchResult, ShortRenderBatchResult, list[ExportItem], Path]:
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
        renderer=dependencies.normal_renderer,
        normal_width=video.width or 1920,
        normal_height=video.height or 1080,
        subtitle_settings=settings,
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
        renderer=dependencies.short_renderer,
        source_width=video.width,
        source_height=video.height,
        subtitle_settings=settings,
        mode=settings.get("mode"),
        short_overlay_title_mode=settings.get("shortOverlayTitleMode"),
    )

    render_failures_path = _write_json(
        storage_paths.job_outputs(job.id) / "render_failures.json",
        _render_failures_to_jsonable(normal_result, short_result),
    )
    exports = [*normal_result.exports, *short_result.exports]
    return normal_result, short_result, exports, render_failures_path


@dataclass(frozen=True)
class _RerenderStoragePaths(StoragePaths):
    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def job_outputs(self, _job_id: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def job_subtitles(self, _job_id: str, clip_type: str) -> Path:
        folder_name = "shorts" if clip_type == "short" else "normal"
        path = self.root / "subtitles" / folder_name
        path.mkdir(parents=True, exist_ok=True)
        return path


def _prepare_subtitle_rerender_staging(
    storage_paths: StoragePaths,
    job_id: str,
    render_revision: int,
) -> StoragePaths:
    staging_root = (
        storage_paths.temp
        / "rr"
        / f"{job_id[-12:]}_r{render_revision}"
    )
    shutil.rmtree(staging_root, ignore_errors=True)
    staging_paths = _RerenderStoragePaths(staging_root)
    staging_paths.ensure()
    return staging_paths


def _promote_staged_export_file(
    source_value: str | None,
    *,
    staging_job_dir: Path,
    canonical_job_dir: Path,
) -> str | None:
    if source_value is None:
        return None
    source = Path(source_value)
    relative_path = source.resolve().relative_to(staging_job_dir.resolve())
    destination = canonical_job_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)
    return str(destination)


def _rewrite_export_metadata_paths(export: ExportItem) -> None:
    if not export.metadata_path:
        return
    metadata_path = Path(export.metadata_path)
    if not metadata_path.is_file():
        return
    payload = _read_json_file(metadata_path)
    if not isinstance(payload, dict):
        return
    payload["video_path"] = export.video_path
    payload["subtitle_path"] = export.subtitle_path
    _write_json(metadata_path, payload)


def _promote_subtitle_rerender(
    *,
    db: Session,
    job: Job,
    previous_exports: Sequence[ExportItem],
    staged_exports: Sequence[ExportItem],
    staged_render_failures_path: Path,
    staging_paths: StoragePaths,
    storage_paths: StoragePaths,
) -> tuple[list[ExportItem], Path]:
    staging_job_dir = staging_paths.job_outputs(job.id)
    canonical_job_dir = storage_paths.job_outputs(job.id)

    for export in staged_exports:
        export.video_path = _promote_staged_export_file(
            export.video_path,
            staging_job_dir=staging_job_dir,
            canonical_job_dir=canonical_job_dir,
        ) or export.video_path
        export.subtitle_path = _promote_staged_export_file(
            export.subtitle_path,
            staging_job_dir=staging_job_dir,
            canonical_job_dir=canonical_job_dir,
        )
        export.metadata_path = _promote_staged_export_file(
            export.metadata_path,
            staging_job_dir=staging_job_dir,
            canonical_job_dir=canonical_job_dir,
        )
        _rewrite_export_metadata_paths(export)

    successful_candidate_ids = {
        export.candidate_id
        for export in staged_exports
        if export.candidate_id is not None
    }
    for previous in previous_exports:
        if previous.candidate_id in successful_candidate_ids:
            db.delete(previous)

    canonical_render_failures_path = canonical_job_dir / "render_failures.json"
    if staged_render_failures_path.is_file():
        staged_render_failures_path.replace(canonical_render_failures_path)

    db.commit()
    current_exports = list(
        db.scalars(
            select(ExportItem)
            .where(ExportItem.job_id == job.id)
            .order_by(ExportItem.type, ExportItem.video_path)
        ).all()
    )
    shutil.rmtree(canonical_job_dir / "audit", ignore_errors=True)
    shutil.rmtree(staging_paths.root, ignore_errors=True)
    return current_exports, canonical_render_failures_path


def _discard_subtitle_rerender_staging(
    *,
    db: Session,
    job_id: str,
    previous_export_ids: set[str],
    staging_paths: StoragePaths,
) -> None:
    current_exports = db.scalars(
        select(ExportItem).where(ExportItem.job_id == job_id)
    ).all()
    for export in current_exports:
        if export.id not in previous_export_ids:
            db.delete(export)
    db.commit()
    shutil.rmtree(staging_paths.root, ignore_errors=True)


def _restore_subtitle_rerender_for_retry(
    *,
    db: Session,
    job: Job,
    review_document: SubtitleReviewDocument,
    review_path: Path,
    code: str,
    message: str,
) -> None:
    review_document = restore_review_after_render_failure(review_document)
    write_subtitle_review(review_document, review_path)
    write_subtitle_review_summary(
        review_document,
        subtitle_review_summary_path(review_path.parent),
    )
    job.status = "awaiting_subtitle_review"
    job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
    job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
    job.error_code = code
    job.error_message = message
    job.updated_at = utc_now()
    db.commit()


def _read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_model_list(path: Path, model_type: type[Candidate]) -> list[Candidate]:
    if not path.is_file():
        return []
    payload = _read_json_file(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a list in {path.name}")
    return [model_type.model_validate(item) for item in payload]


def _read_transcript_segments(path: Path) -> list[TranscriptSegment]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = _read_json_file(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a list in {path.name}")
    return [TranscriptSegment.model_validate(item) for item in payload]


def _top_level_metadata_files(job_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in job_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".json", ".md"}
        ),
        key=lambda path: path.name,
    )


def _next_clip_plan_revision(job_dir: Path) -> int:
    path = clip_plan_output_path(job_dir)
    if not path.is_file():
        return 1
    try:
        return load_clip_plan(path).revision + 1
    except (OSError, ValueError, json.JSONDecodeError):
        return 1


def _render_candidate_review_preview(
    renderer: Callable[..., Path],
    input_path: Path,
    output_path: Path,
    candidate: Any,
) -> Path:
    kwargs: dict[str, float] = {
        "start": float(candidate.start),
        "duration": float(candidate.end - candidate.start),
    }
    hook_start = getattr(candidate, "hook_scene_start", None)
    hook_end = getattr(candidate, "hook_scene_end", None)
    if hook_start is not None and hook_end is not None:
        kwargs["hook_start"] = float(hook_start)
        kwargs["hook_duration"] = float(hook_end - hook_start)
    return renderer(
        input_path,
        output_path,
        **kwargs,
    )


def _prepare_clip_plan_review(
    *,
    db: Session,
    job: Job,
    input_path: Path,
    selection: CandidateSelection,
    settings: dict[str, Any],
    job_dir: Path,
    preview_renderer: Callable[..., Path],
    source_duration: float,
) -> Path:
    selected = [*selection.normal_clips, *selection.shorts]
    if not selected:
        raise PipelineExpectedError(
            "no_usable_output",
            "Pipeline completed analysis but produced no usable clips.",
        )

    document = build_clip_plan(
        job.id,
        selection,
        settings,
        revision=_next_clip_plan_revision(job_dir),
        source_duration=source_duration,
    )
    output_path = clip_plan_output_path(job_dir)
    write_clip_plan(document, output_path)
    total = len(selected)
    _set_clip_plan_preview_progress(db, job, completed=0, total=total)

    available_clip_ids: list[str] = []
    current_preview_paths: set[Path] = set()
    for preview_index, candidate in enumerate(selected, start=1):
        preview_path = subtitle_review_preview_path(job_dir, candidate.id)
        current_preview_paths.add(preview_path.resolve())
        try:
            if not preview_path.is_file() or preview_path.stat().st_size <= 0:
                _render_candidate_review_preview(
                    preview_renderer,
                    input_path,
                    preview_path,
                    candidate,
                )
        except Exception as exc:
            raise PipelineExpectedError(
                "clip_plan_preview_failed",
                (
                    "Could not prepare clip plan preview for "
                    f"clip {preview_index}/{total}: {exc}"
                ),
            ) from exc
        available_clip_ids.append(candidate.id)
        _set_clip_plan_preview_progress(
            db,
            job,
            completed=preview_index,
            total=total,
        )

    preview_dir = subtitle_review_preview_path(job_dir, "placeholder").parent
    if preview_dir.is_dir():
        for stale_path in preview_dir.glob("*.mp4"):
            if stale_path.resolve() not in current_preview_paths:
                stale_path.unlink(missing_ok=True)

    document = mark_clip_plan_awaiting_review(
        document,
        preview_clip_ids=available_clip_ids,
    )
    write_clip_plan(document, output_path)
    _set_status(db, job, "awaiting_clip_review")
    return output_path


def run_autoclipper_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    transcribe_audio = deps.transcribe_audio
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
    candidate_generation_summary: dict[str, Any] | None = None
    scored_candidates: list[Candidate] = []
    selection: CandidateSelection | None = None
    openai_scoring_summary: dict[str, Any] | None = None
    exports: list[ExportItem] = []
    transcription_engine = "not_run"
    transcription_model: str | None = None
    transcription_language: str | None = None
    transcription_diagnostics: dict[str, Any] | None = None
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
        configured_transcription_model = _whisper_model_size_setting(settings)
        configured_transcription_language = _transcription_language_setting(settings)
        configured_transcription_device = _transcription_device_setting(settings)
        configured_transcription_compute_type = _transcription_compute_type_setting(settings)
        transcription_diagnostics = {
            "requested_device": configured_transcription_device,
            "actual_device": None,
            "requested_compute_type": configured_transcription_compute_type,
            "actual_compute_type": None,
            "model": configured_transcription_model,
            "language": configured_transcription_language,
            "gpu_name": None,
            "gpu_memory_total_mb": None,
            "model_load_seconds": 0.0,
            "transcription_seconds": 0.0,
            "peak_vram_mb": None,
            "fallback_used": False,
            "fallback_reason": None,
        }
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
                candidate_generation_summary=candidate_generation_summary,
                scored_candidates=scored_candidates,
                selection=selection,
                openai_scoring_summary=openai_scoring_summary,
                normal_result=normal_result,
                short_result=short_result,
                exports=exports,
                transcription_engine=transcription_engine,
                used_fixture_transcript=used_fixture_transcript,
                transcription_model=transcription_model,
                transcription_language=transcription_language,
                transcription_diagnostics=transcription_diagnostics,
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
            _raise_if_stream_durations_mismatch(metadata)
            try:
                validate_manual_ranges_for_duration(
                    settings,
                    video_duration=duration,
                )
            except ValueError as exc:
                raise PipelineExpectedError(
                    "manual_clip_range_invalid",
                    f"Manual clip time range is invalid: {exc}",
                ) from exc

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
                transcription_model = "fixture"
                transcription_language = "fixture"
                transcription_diagnostics = {
                    "requested_device": configured_transcription_device,
                    "actual_device": "fixture",
                    "requested_compute_type": configured_transcription_compute_type,
                    "actual_compute_type": "fixture",
                    "model": "fixture",
                    "language": "fixture",
                    "gpu_name": None,
                    "gpu_memory_total_mb": None,
                    "model_load_seconds": 0.0,
                    "transcription_seconds": 0.0,
                    "peak_vram_mb": None,
                    "fallback_used": False,
                    "fallback_reason": None,
                }
                transcript_segments = _e2e_fixture_transcript(duration)
            else:
                transcription_engine = "faster_whisper"
                transcription_model = configured_transcription_model
                transcription_language = configured_transcription_language
                try:
                    if transcribe_audio is not None:
                        transcript_segments = transcribe_audio(audio_path)
                        transcription_diagnostics = {
                            **(transcription_diagnostics or {}),
                            "actual_device": "injected",
                            "actual_compute_type": "injected",
                        }
                    else:
                        engine = FasterWhisperTranscriptionEngine(
                            model_size=configured_transcription_model,
                            device=configured_transcription_device,
                            compute_type=configured_transcription_compute_type,
                            language=None if configured_transcription_language == "auto" else configured_transcription_language,
                        )
                        transcript_segments = engine.transcribe(audio_path)
                        transcription_diagnostics = engine.diagnostics
                except TranscriptionRuntimeError as exc:
                    transcription_diagnostics = {
                        **(transcription_diagnostics or {}),
                        **exc.details,
                        "error_code": exc.code,
                    }
                    raise PipelineExpectedError(
                        exc.code,
                        str(exc),
                        details=transcription_diagnostics,
                    ) from exc
                except Exception as exc:
                    raise PipelineExpectedError(
                        "transcription_failed",
                        f"Could not transcribe audio: {exc}",
                    ) from exc
            raw_transcript_path = write_transcript_segments(transcript_segments, raw_transcript_output_path(job_dir))
            metadata_files.append(raw_transcript_path)
            postprocess_result = postprocess_transcript_segments(transcript_segments, settings)
            transcript_segments = postprocess_result.segments
            postprocess_summary_path = write_transcript_postprocess_summary(
                postprocess_result.summary,
                transcript_postprocess_summary_path(job_dir),
            )
            metadata_files.append(postprocess_summary_path)
            deterministic_path = write_transcript_segments(
                transcript_segments,
                deterministic_transcript_output_path(job_dir),
            )
            metadata_files.append(deterministic_path)

            correction_mode = _subtitle_correction_mode_setting(settings)
            correction_scope = _subtitle_correction_scope_setting(settings)
            correction_progress_path = correction_progress_output_path(job_dir)
            correction_progress_state = {"completed": 0, "total": 0, "retries": 0}
            correction_progress_callback: Callable[[int, int, int], None] | None = None
            correction_target_indices: list[int] | None = None
            suspicion_result: TranscriptSuspicionResult | None = None
            suspicion_filter_error: Exception | None = None
            if correction_mode == "openai":
                if correction_scope == "suspicious":
                    try:
                        suspicion_result = analyze_transcript_suspicion(
                            transcript_segments,
                            threshold=max(
                                0.0,
                                min(1.0, _float_setting(settings, "subtitleCorrectionSuspicionThreshold", 0.40)),
                            ),
                            context_segments=min(10, _int_setting(settings, "subtitleCorrectionContextSegments", 2)),
                            batch_size=_subtitle_correction_batch_size_setting(settings),
                            glossary=_transcript_correction_glossary(settings),
                            replacements=(
                                settings.get("transcriptReplacements")
                                if isinstance(settings.get("transcriptReplacements"), dict)
                                else None
                            ),
                        )
                        correction_target_indices = suspicion_result.target_indices
                        metadata_files.extend(write_suspicion_artifacts(suspicion_result, job_dir))
                    except Exception as exc:
                        suspicion_filter_error = exc
                        correction_target_indices = []
                        metadata_files.append(
                            write_suspicion_failure_summary(
                                job_dir,
                                segment_count=len(transcript_segments),
                                threshold=max(
                                    0.0,
                                    min(
                                        1.0,
                                        _float_setting(settings, "subtitleCorrectionSuspicionThreshold", 0.40),
                                    ),
                                ),
                                exc=exc,
                            )
                        )
                _set_status(db, job, "correcting_subtitles")
                visited_statuses.append("correcting_subtitles")
                batch_size = _subtitle_correction_batch_size_setting(settings)
                target_segment_count = (
                    len(correction_target_indices)
                    if correction_target_indices is not None
                    else len(transcript_segments)
                )
                total_batches = (target_segment_count + batch_size - 1) // batch_size
                _record_subtitle_correction_progress(
                    db,
                    job,
                    correction_progress_path,
                    completed_batches=0,
                    total_batches=total_batches,
                    retry_count=0,
                    target_segments_total=target_segment_count,
                    transcript_segment_count=len(transcript_segments),
                )
                metadata_files.append(correction_progress_path)

                def correction_progress_callback(completed: int, total: int, retries: int) -> None:
                    correction_progress_state.update(completed=completed, total=total, retries=retries)
                    completed_targets = min(completed * batch_size, target_segment_count)
                    _record_subtitle_correction_progress(
                        db,
                        job,
                        correction_progress_path,
                        completed_batches=completed,
                        total_batches=total,
                        retry_count=retries,
                        target_segments_completed=completed_targets,
                        target_segments_total=target_segment_count,
                        transcript_segment_count=len(transcript_segments),
                    )

            if suspicion_filter_error is not None:
                correction_result = filter_failed_correction_result(
                    transcript_segments,
                    _subtitle_correction_model_setting(settings),
                    suspicion_filter_error,
                )
            else:
                correction_result = _apply_transcript_correction(
                    transcript_segments,
                    settings,
                    corrector=deps.transcript_corrector,
                    target_indices=correction_target_indices,
                    progress_callback=correction_progress_callback,
                )
            if correction_mode == "openai":
                final_target_total = int(correction_result.summary.get("target_segment_count", 0))
                _record_subtitle_correction_progress(
                    db,
                    job,
                    correction_progress_path,
                    completed_batches=correction_progress_state["completed"],
                    total_batches=correction_progress_state["total"],
                    retry_count=correction_progress_state["retries"],
                    target_segments_completed=(
                        0 if correction_result.summary.get("fallback_used") else final_target_total
                    ),
                    target_segments_total=final_target_total,
                    transcript_segment_count=len(transcript_segments),
                    finished=True,
                    fallback_used=bool(correction_result.summary.get("fallback_used")),
                )
            correction_summary_path = write_correction_summary(
                correction_result.summary,
                correction_summary_output_path(job_dir),
            )
            correction_diff_path = write_correction_diff(
                correction_result,
                correction_diff_output_path(job_dir),
            )
            metadata_files.extend([correction_summary_path, correction_diff_path])
            if correction_mode == "openai":
                metadata_files.append(write_corrected_transcript(correction_result, job_dir))

            transcript_segments = correction_result.segments
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
            candidate_generation_summary_path = job_dir / "candidate_generation_summary.json"

            def candidate_generation_heartbeat(summary: dict[str, Any]) -> None:
                nonlocal candidate_generation_summary
                candidate_generation_summary = summary
                _write_json(candidate_generation_summary_path, summary)
                _heartbeat_job(db, job)

            normal_manual_ranges = manual_ranges_for_type(settings, "normal")
            short_manual_ranges = manual_ranges_for_type(settings, "short")
            automatic_settings = automatic_selection_settings(
                settings,
                manual_normal=bool(normal_manual_ranges),
                manual_short=bool(short_manual_ranges),
            )
            try:
                normal_generation_result = (
                    build_manual_candidates(
                        "normal",
                        normal_manual_ranges,
                        transcript_segments,
                    )
                    if normal_manual_ranges
                    else generate_normal_candidates_with_summary(
                        transcript_segments,
                        scene_segments,
                        silence_segments,
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                )
                normal_candidates = normal_generation_result.candidates
                short_generation_result = (
                    build_manual_candidates(
                        "short",
                        short_manual_ranges,
                        transcript_segments,
                    )
                    if short_manual_ranges
                    else generate_short_candidates_with_summary(
                        transcript_segments,
                        scene_segments,
                        silence_segments,
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                )
                short_candidates = short_generation_result.candidates
                candidate_generation_summary = merge_candidate_generation_summaries(
                    [normal_generation_result.summary, short_generation_result.summary],
                    video_duration=duration,
                    transcript_segment_count=len(transcript_segments),
                )
                metadata_files.append(_write_json(candidate_generation_summary_path, candidate_generation_summary))
            except CandidateGenerationMemoryLimitError as exc:
                candidate_generation_summary = exc.summary
                metadata_files.append(_write_json(candidate_generation_summary_path, candidate_generation_summary))
                raise PipelineExpectedError(
                    "candidate_generation_memory_limit",
                    "Candidate generation exceeded the configured memory limit.",
                    details=candidate_generation_summary,
                ) from exc
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

            manual_candidates = [
                *(normal_candidates if normal_manual_ranges else []),
                *(short_candidates if short_manual_ranges else []),
            ]
            automatic_candidates = [
                *(normal_candidates if not normal_manual_ranges else []),
                *(short_candidates if not short_manual_ranges else []),
            ]
            _set_status(db, job, "scoring_candidates")
            visited_statuses.append("scoring_candidates")
            scoring_result = (
                _score_candidate_list(
                    automatic_candidates,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    silence_segments=silence_segments,
                    visual_quality=visual_quality,
                    scorer=deps.openai_scorer,
                )
                if automatic_candidates
                else ScoringResult(candidates=[])
            )
            scored_candidates = [*scoring_result.candidates, *manual_candidates]
            openai_scoring_summary = scoring_result.openai_summary

            _set_status(db, job, "selecting_clips")
            visited_statuses.append("selecting_clips")
            automatic_selection = select_candidates(
                scoring_result.candidates,
                settings=automatic_settings,
                audio_features=audio_features,
                silence_segments=silence_segments,
            )
            automatic_selection, automatic_scored, openai_scoring_summary = (
                _ensure_selected_candidates_openai_scored(
                    automatic_selection,
                    scoring_result.candidates,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    visual_quality=visual_quality,
                    scorer=scoring_result.openai_scorer,
                    openai_summary=openai_scoring_summary,
                )
            )
            scored_candidates = [*automatic_scored, *manual_candidates]
            selection = merge_manual_candidates_into_selection(
                automatic_selection,
                settings=settings,
                manual_normal_candidates=(
                    normal_candidates if normal_manual_ranges else []
                ),
                manual_short_candidates=(
                    short_candidates if short_manual_ranges else []
                ),
            )
            selection, scored_candidates = _selection_with_refined_boundaries(
                selection,
                scored_candidates,
                transcript_segments=transcript_segments,
                silence_segments=silence_segments,
                scene_segments=scene_segments,
                settings=settings,
                timeline_duration=duration,
            )
            selection, scored_candidates = _selection_with_fallback_titles(
                selection,
                scored_candidates,
                transcript_segments,
            )
            metadata_files.append(write_candidates(scored_candidates, job_dir / "scored_candidates.json"))
            selected_path = write_selected_clips(selection, job_dir / "selected_clips.json")
            metadata_files.append(selected_path)

            if (
                bool(settings.get("requireClipPlanReview", False))
                and bool(settings.get("requireSubtitleReview", False))
                and bool(settings.get("burnSubtitles", True))
            ):
                plan_path = _prepare_clip_plan_review(
                    db=db,
                    job=job,
                    input_path=input_path,
                    selection=selection,
                    settings=settings,
                    job_dir=job_dir,
                    preview_renderer=deps.subtitle_review_preview_renderer,
                    source_duration=duration,
                )
                metadata_files.append(plan_path)
                summary_files = write_summaries()
                metadata_files.extend(
                    path for path in summary_files if path not in metadata_files
                )
                visited_statuses.extend(
                    ["preparing_clip_review", "awaiting_clip_review"]
                )
                return visited_statuses

            if bool(settings.get("requireSubtitleReview", False)) and bool(settings.get("burnSubtitles", True)):
                if not selection.normal_clips and not selection.shorts:
                    raise PipelineExpectedError(
                        "no_usable_output",
                        "Pipeline completed analysis but produced no usable clips.",
                    )
                review_document = build_subtitle_review(
                    job.id,
                    selection,
                    transcript_segments,
                    short_max_duration=float(
                        settings.get("shortMaxDuration", 75.0)
                    ),
                )
                preview_total = len(review_document.clips)
                _set_subtitle_review_preview_progress(
                    db,
                    job,
                    completed=0,
                    total=preview_total,
                )
                visited_statuses.append("preparing_subtitle_review")
                for preview_index, clip in enumerate(review_document.clips, start=1):
                    try:
                        _render_candidate_review_preview(
                            deps.subtitle_review_preview_renderer,
                            input_path,
                            subtitle_review_preview_path(job_dir, clip.id),
                            clip,
                        )
                    except Exception as exc:
                        raise PipelineExpectedError(
                            "subtitle_review_preview_failed",
                            f"Could not prepare subtitle review video for clip {preview_index}/{preview_total}: {exc}",
                        ) from exc
                    clip.preview_video_url = subtitle_review_preview_url(job.id, clip.id)
                    _set_subtitle_review_preview_progress(
                        db,
                        job,
                        completed=preview_index,
                        total=preview_total,
                    )
                review_path = write_subtitle_review(
                    review_document,
                    subtitle_review_output_path(job_dir),
                )
                review_summary_path = write_subtitle_review_summary(
                    review_document,
                    subtitle_review_summary_path(job_dir),
                )
                metadata_files.extend([review_path, review_summary_path])
                summary_files = write_summaries()
                metadata_files.extend(path for path in summary_files if path not in metadata_files)
                _set_status(db, job, "awaiting_subtitle_review")
                visited_statuses.append("awaiting_subtitle_review")
                return visited_statuses

            normal_result, short_result, exports, render_failures_path = _render_selected_outputs(
                db=db,
                job=job,
                video=video,
                input_path=input_path,
                selection=selection,
                transcript_segments=transcript_segments,
                settings=settings,
                storage_paths=storage_paths,
                dependencies=deps,
                visited_statuses=visited_statuses,
            )
            metadata_files.append(render_failures_path)
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


def _restore_clip_plan_after_reselection_failure(
    db: Session,
    job: Job,
    *,
    job_dir: Path,
    previous_plan: Any,
    previous_artifacts: dict[Path, bytes | None],
    code: str,
    message: str,
) -> None:
    for path, payload in previous_artifacts.items():
        if payload is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if previous_plan is not None:
        previous_plan.state = "awaiting_review"
        write_clip_plan(previous_plan, clip_plan_output_path(job_dir))
        job.settings_json = dict(previous_plan.settings)
    job.status = "awaiting_clip_review"
    job.progress = PROGRESS_MAP["awaiting_clip_review"]
    job.current_step = "再選定に失敗しました。設定を確認して再試行してください"
    job.error_code = code
    job.error_message = message
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)


def _candidate_with_clip_plan_boundary(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    *,
    start: float,
    end: float,
) -> Candidate:
    overlapping = [
        (index, segment)
        for index, segment in enumerate(transcript_segments)
        if segment.end > start and segment.start < end
    ]
    transcript_text = _transcript_text([segment for _, segment in overlapping])
    recommended_start = (
        candidate.clip_plan_recommended_start
        if candidate.clip_plan_recommended_start is not None
        else candidate.start
    )
    recommended_end = (
        candidate.clip_plan_recommended_end
        if candidate.clip_plan_recommended_end is not None
        else candidate.end
    )
    updated = candidate.model_dump()
    updated.update(
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "transcript_text": transcript_text,
            "segment_start_index": overlapping[0][0] if overlapping else None,
            "segment_end_index": overlapping[-1][0] + 1 if overlapping else None,
            "transcript_char_count": sum(
                len(segment.text.strip()) for _, segment in overlapping
            ),
            "speech_seconds": round(
                sum(
                    max(
                        0.0,
                        min(float(segment.end), end)
                        - max(float(segment.start), start),
                    )
                    for _, segment in overlapping
                    if segment.text.strip()
                ),
                3,
            ),
            "clip_plan_recommended_start": recommended_start,
            "clip_plan_recommended_end": recommended_end,
            "clip_plan_boundary_adjusted": not (
                abs(start - recommended_start) < 0.001
                and abs(end - recommended_end) < 0.001
            ),
        }
    )
    return Candidate.model_validate(updated)


def _restore_clip_plan_after_boundary_failure(
    db: Session,
    job: Job,
    *,
    document: Any,
    plan_path: Path,
    selected_path: Path,
    selected_payload: bytes | None,
    preview_path: Path,
    preview_payload: bytes | None,
    code: str,
    message: str,
    current_step: str = "範囲の更新に失敗しました。時間を確認して再試行してください",
) -> None:
    if selected_payload is not None:
        selected_path.write_bytes(selected_payload)
    if preview_payload is None:
        preview_path.unlink(missing_ok=True)
    else:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(preview_payload)
    if document is not None:
        document.state = "awaiting_review"
        write_clip_plan(document, plan_path)
    job.status = "awaiting_clip_review"
    job.progress = PROGRESS_MAP["awaiting_clip_review"]
    job.current_step = current_step
    job.error_code = code
    job.error_message = message
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)


def run_clip_plan_boundary_update(
    job_id: str,
    clip_id: str,
    start: float,
    end: float,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        plan_path = clip_plan_output_path(job_dir)
        selected_path = job_dir / "selected_clips.json"
        preview_path = subtitle_review_preview_path(job_dir, clip_id)
        document = None
        selected_payload = (
            selected_path.read_bytes() if selected_path.is_file() else None
        )
        preview_payload = (
            preview_path.read_bytes() if preview_path.is_file() else None
        )
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(
                _read_json_file(selected_path)
            )
            transcript_segments = _read_transcript_segments(
                transcript_output_path(job_dir)
            )
            planned_clip = next(
                (clip for clip in document.clips if clip.id == clip_id),
                None,
            )
            if planned_clip is None:
                raise ValueError(f"clip plan item not found: {clip_id}")
            candidates = [*selection.normal_clips, *selection.shorts]
            candidate = next(
                (item for item in candidates if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected clip not found: {clip_id}")

            source_duration = float(
                video.duration
                or document.source_duration
                or max((clip.end for clip in document.clips), default=0.0)
            )
            if start < 0 or end <= start or end > source_duration + 0.001:
                raise ValueError(
                    "requested clip boundary is outside the source video"
                )

            _set_status(db, job, "preparing_clip_review")
            job.current_step = "調整した範囲の確認動画を準備中"
            job.error_code = None
            job.error_message = None
            job.updated_at = utc_now()
            document.state = "preparing"
            write_clip_plan(document, plan_path)
            db.commit()
            db.refresh(job)
            visited_statuses.append("preparing_clip_review")

            updated_candidate = _candidate_with_clip_plan_boundary(
                candidate,
                transcript_segments,
                start=start,
                end=end,
            )
            _render_candidate_review_preview(
                deps.subtitle_review_preview_renderer,
                storage_paths.resolve_stored_file(video.stored_path),
                preview_path,
                updated_candidate,
            )
            target_collection = (
                selection.normal_clips
                if updated_candidate.type == "normal"
                else selection.shorts
            )
            target_index = next(
                index
                for index, item in enumerate(target_collection)
                if item.id == clip_id
            )
            target_collection[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)

            update_clip_plan_boundary(
                document,
                clip_id,
                start=start,
                end=end,
                transcript_excerpt=updated_candidate.transcript_text,
            )
            document.source_duration = source_duration
            available_clip_ids = [
                clip.id
                for clip in document.clips
                if subtitle_review_preview_path(job_dir, clip.id).is_file()
            ]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            _set_status(db, job, "awaiting_clip_review")
            job.error_code = None
            job.error_message = None
            db.commit()
            db.refresh(job)
            visited_statuses.append("awaiting_clip_review")
        except Exception as exc:
            _restore_clip_plan_after_boundary_failure(
                db,
                job,
                document=document,
                plan_path=plan_path,
                selected_path=selected_path,
                selected_payload=selected_payload,
                preview_path=preview_path,
                preview_payload=preview_payload,
                code="clip_plan_boundary_update_failed",
                message=str(exc),
            )
            raise

    return visited_statuses


def run_clip_plan_hook_scene_update(
    job_id: str,
    clip_id: str,
    start: float | None,
    end: float | None,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        plan_path = clip_plan_output_path(job_dir)
        selected_path = job_dir / "selected_clips.json"
        preview_path = subtitle_review_preview_path(job_dir, clip_id)
        document = None
        selected_payload = (
            selected_path.read_bytes() if selected_path.is_file() else None
        )
        preview_payload = (
            preview_path.read_bytes() if preview_path.is_file() else None
        )
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(
                _read_json_file(selected_path)
            )
            planned_clip = next(
                (clip for clip in document.clips if clip.id == clip_id),
                None,
            )
            if planned_clip is None:
                raise ValueError(f"clip plan item not found: {clip_id}")
            if planned_clip.type != "short":
                raise ValueError("hook scene is only supported for short clips")

            candidate = next(
                (item for item in selection.shorts if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected short not found: {clip_id}")
            if (start is None) != (end is None):
                raise ValueError("hook scene requires both start and end")
            if start is not None and end is not None:
                hook_duration = end - start
                if not 0.5 <= hook_duration <= 3.0:
                    raise ValueError(
                        "hook scene duration must be between 0.5 and 3 seconds"
                    )
                if (
                    start < candidate.start - 0.001
                    or end > candidate.end + 0.001
                ):
                    raise ValueError(
                        "hook scene must stay within the selected clip"
                    )
                short_max_duration = float(
                    (job.settings_json or {}).get("shortMaxDuration", 75.0)
                )
                if candidate.duration + hook_duration > short_max_duration + 0.001:
                    raise ValueError(
                        "hook scene would exceed the configured short maximum duration"
                    )

            candidate_payload = candidate.model_dump(mode="python")
            candidate_payload["hook_scene_start"] = start
            candidate_payload["hook_scene_end"] = end
            updated_candidate = Candidate.model_validate(candidate_payload)

            _set_status(db, job, "preparing_clip_review")
            job.current_step = "冒頭フック映像の確認動画を準備中"
            job.error_code = None
            job.error_message = None
            job.updated_at = utc_now()
            document.state = "preparing"
            write_clip_plan(document, plan_path)
            db.commit()
            db.refresh(job)
            visited_statuses.append("preparing_clip_review")

            _render_candidate_review_preview(
                deps.subtitle_review_preview_renderer,
                storage_paths.resolve_stored_file(video.stored_path),
                preview_path,
                updated_candidate,
            )
            target_index = next(
                index
                for index, item in enumerate(selection.shorts)
                if item.id == clip_id
            )
            selection.shorts[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)

            update_clip_plan_hook_scene(
                document,
                clip_id,
                start=start,
                end=end,
            )
            available_clip_ids = [
                clip.id
                for clip in document.clips
                if subtitle_review_preview_path(job_dir, clip.id).is_file()
            ]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            _set_status(db, job, "awaiting_clip_review")
            job.error_code = None
            job.error_message = None
            db.commit()
            db.refresh(job)
            visited_statuses.append("awaiting_clip_review")
        except Exception as exc:
            _restore_clip_plan_after_boundary_failure(
                db,
                job,
                document=document,
                plan_path=plan_path,
                selected_path=selected_path,
                selected_payload=selected_payload,
                preview_path=preview_path,
                preview_payload=preview_payload,
                code="clip_plan_hook_scene_update_failed",
                message=str(exc),
                current_step=(
                    "冒頭フック映像の更新に失敗しました。"
                    "時間を確認して再試行してください"
                ),
            )
            raise

    return visited_statuses


def run_subtitle_review_hook_scene_update(
    job_id: str,
    clip_id: str,
    start: float | None,
    end: float | None,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        review_path = subtitle_review_output_path(job_dir)
        summary_path = subtitle_review_summary_path(job_dir)
        selected_path = job_dir / "selected_clips.json"
        preview_path = subtitle_review_preview_path(job_dir, clip_id)
        stored_payloads = {
            path: path.read_bytes() if path.is_file() else None
            for path in (review_path, summary_path, selected_path, preview_path)
        }

        try:
            document = load_subtitle_review(review_path)
            selection = CandidateSelection.model_validate(
                _read_json_file(selected_path)
            )
            candidate = next(
                (item for item in selection.shorts if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected short not found: {clip_id}")

            next_document = document.model_copy(deep=True)
            next_document.short_max_duration = float(
                (job.settings_json or {}).get("shortMaxDuration", 75.0)
            )
            update_review_hook_scene(
                next_document,
                clip_id,
                start=start,
                end=end,
            )

            candidate_payload = candidate.model_dump(mode="python")
            candidate_payload["hook_scene_start"] = start
            candidate_payload["hook_scene_end"] = end
            updated_candidate = Candidate.model_validate(candidate_payload)

            _set_status(db, job, "preparing_subtitle_review")
            job.current_step = "冒頭フック映像の確認動画を準備中"
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
            visited_statuses.append("preparing_subtitle_review")

            _render_candidate_review_preview(
                deps.subtitle_review_preview_renderer,
                storage_paths.resolve_stored_file(video.stored_path),
                preview_path,
                updated_candidate,
            )
            target_index = next(
                index
                for index, item in enumerate(selection.shorts)
                if item.id == clip_id
            )
            selection.shorts[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)
            write_subtitle_review(next_document, review_path)
            write_subtitle_review_summary(next_document, summary_path)

            _set_status(db, job, "awaiting_subtitle_review")
            visited_statuses.append("awaiting_subtitle_review")
        except Exception as exc:
            for path, payload in stored_payloads.items():
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
            job.current_step = (
                "冒頭フック映像の更新に失敗しました。"
                "時間を確認して再試行してください"
            )
            job.error_code = "subtitle_review_hook_scene_update_failed"
            job.error_message = str(exc)
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
            raise

    return visited_statuses


def run_clip_plan_reselection(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        settings = dict(job.settings_json or {})
        input_path = storage_paths.resolve_stored_file(video.stored_path)
        previous_plan_path = clip_plan_output_path(job_dir)
        previous_plan = (
            load_clip_plan(previous_plan_path)
            if previous_plan_path.is_file()
            else None
        )
        previous_artifact_paths = [
            job_dir / "selected_clips.json",
            job_dir / "scored_candidates.json",
            job_dir / "openai_scoring_summary.json",
            job_dir / "candidate_summary.json",
            job_dir / "rejection_summary.json",
            job_dir / "selected_clips_summary.json",
        ]
        previous_artifacts = {
            path: path.read_bytes() if path.is_file() else None
            for path in previous_artifact_paths
        }

        try:
            _set_status(db, job, "reselecting_clips")
            visited_statuses.append("reselecting_clips")
            transcript_segments = _read_transcript_segments(
                transcript_output_path(job_dir)
            )
            audio_features = AudioFeatures.model_validate(
                _read_json_file(job_dir / "audio_features.json")
            )
            silence_segments = [
                SilenceSegment.model_validate(item)
                for item in _read_json_file(job_dir / "silence_segments.json")
            ]
            scene_segments = [
                SceneSegment.model_validate(item)
                for item in _read_json_file(job_dir / "scene_segments.json")
            ]
            visual_quality = VisualQuality.model_validate(
                _read_json_file(job_dir / "visual_quality.json")
            )
            base_candidates = _read_model_list(
                job_dir / "candidates.json",
                Candidate,
            )
            if not base_candidates:
                raise PipelineExpectedError(
                    "clip_plan_candidates_missing",
                    "Saved clip candidates are unavailable for reselection.",
                )

            normal_manual_ranges = manual_ranges_for_type(settings, "normal")
            short_manual_ranges = manual_ranges_for_type(settings, "short")
            automatic_settings = automatic_selection_settings(
                settings,
                manual_normal=bool(normal_manual_ranges),
                manual_short=bool(short_manual_ranges),
            )
            normal_candidates = (
                build_manual_candidates(
                    "normal",
                    normal_manual_ranges,
                    transcript_segments,
                ).candidates
                if normal_manual_ranges
                else [
                    candidate
                    for candidate in base_candidates
                    if candidate.type == "normal"
                ]
            )
            short_candidates = (
                build_manual_candidates(
                    "short",
                    short_manual_ranges,
                    transcript_segments,
                ).candidates
                if short_manual_ranges
                else [
                    candidate
                    for candidate in base_candidates
                    if candidate.type == "short"
                ]
            )
            manual_candidates = [
                *(normal_candidates if normal_manual_ranges else []),
                *(short_candidates if short_manual_ranges else []),
            ]
            automatic_candidates = [
                *(normal_candidates if not normal_manual_ranges else []),
                *(short_candidates if not short_manual_ranges else []),
            ]

            scoring_result = (
                _score_candidate_list(
                    automatic_candidates,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    silence_segments=silence_segments,
                    visual_quality=visual_quality,
                    scorer=deps.openai_scorer,
                )
                if automatic_candidates
                else ScoringResult(candidates=[])
            )
            automatic_selection = select_candidates(
                scoring_result.candidates,
                settings=automatic_settings,
                audio_features=audio_features,
                silence_segments=silence_segments,
            )
            automatic_selection, automatic_scored, openai_scoring_summary = (
                _ensure_selected_candidates_openai_scored(
                    automatic_selection,
                    scoring_result.candidates,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    visual_quality=visual_quality,
                    scorer=scoring_result.openai_scorer,
                    openai_summary=scoring_result.openai_summary,
                )
            )
            scored_candidates = [*automatic_scored, *manual_candidates]
            selection = merge_manual_candidates_into_selection(
                automatic_selection,
                settings=settings,
                manual_normal_candidates=(
                    normal_candidates if normal_manual_ranges else []
                ),
                manual_short_candidates=(
                    short_candidates if short_manual_ranges else []
                ),
            )
            selection, scored_candidates = _selection_with_refined_boundaries(
                selection,
                scored_candidates,
                transcript_segments=transcript_segments,
                silence_segments=silence_segments,
                scene_segments=scene_segments,
                settings=settings,
                timeline_duration=float(video.duration or visual_quality.duration),
            )
            selection, scored_candidates = _selection_with_fallback_titles(
                selection,
                scored_candidates,
                transcript_segments,
            )
            write_candidates(
                scored_candidates,
                job_dir / "scored_candidates.json",
            )
            write_selected_clips(selection, job_dir / "selected_clips.json")

            openai_summary_path = job_dir / "openai_scoring_summary.json"
            if openai_scoring_summary is None:
                openai_summary_path.unlink(missing_ok=True)
            candidate_generation_summary = _read_json_file(
                job_dir / "candidate_generation_summary.json"
            )
            transcript_summary_path = job_dir / "transcript_summary.json"
            transcript_summary = (
                _read_json_file(transcript_summary_path)
                if transcript_summary_path.is_file()
                else {}
            )
            write_generation_summaries(
                job_dir,
                transcript_segments=transcript_segments,
                audio_features=audio_features,
                normal_candidates=normal_candidates,
                short_candidates=short_candidates,
                candidate_generation_summary=candidate_generation_summary,
                scored_candidates=scored_candidates,
                selection=selection,
                openai_scoring_summary=openai_scoring_summary,
                transcription_engine=str(
                    transcript_summary.get("transcription_engine", "not_run")
                ),
                used_fixture_transcript=bool(
                    transcript_summary.get("used_fixture_transcript", False)
                ),
                transcription_model=transcript_summary.get(
                    "transcription_model"
                ),
                transcription_language=transcript_summary.get(
                    "transcription_language"
                ),
                transcription_diagnostics=transcript_summary.get(
                    "transcription_runtime"
                ),
            )
            _prepare_clip_plan_review(
                db=db,
                job=job,
                input_path=input_path,
                selection=selection,
                settings=settings,
                job_dir=job_dir,
                preview_renderer=deps.subtitle_review_preview_renderer,
                source_duration=float(video.duration or visual_quality.duration),
            )
            visited_statuses.extend(
                ["preparing_clip_review", "awaiting_clip_review"]
            )
        except PipelineExpectedError as exc:
            _restore_clip_plan_after_reselection_failure(
                db,
                job,
                job_dir=job_dir,
                previous_plan=previous_plan,
                previous_artifacts=previous_artifacts,
                code=exc.code,
                message=exc.message,
            )
        except Exception as exc:
            _restore_clip_plan_after_reselection_failure(
                db,
                job,
                job_dir=job_dir,
                previous_plan=previous_plan,
                previous_artifacts=previous_artifacts,
                code="clip_plan_reselection_failed",
                message=str(exc),
            )
            raise

    return visited_statuses


def run_subtitle_review_render(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        review_path = subtitle_review_output_path(job_dir)
        settings = dict(job.settings_json or {})
        input_path = storage_paths.resolve_stored_file(video.stored_path)
        review_document: SubtitleReviewDocument | None = None
        rerender_staging_paths: StoragePaths | None = None
        previous_export_ids: set[str] = set()
        rerender_promoted = False
        is_rerender = False
        pending_rerender_zip: Path | None = None

        try:
            review_document = load_subtitle_review(review_path)
            is_rerender = review_document.render_revision > 1
            if review_document.state not in {"render_queued", "rendering"}:
                raise PipelineExpectedError(
                    "subtitle_review_not_ready",
                    "Subtitle review has not been finalized.",
                )

            review_document = mark_review_rendering(review_document)
            write_subtitle_review(review_document, review_path)
            write_subtitle_review_summary(
                review_document,
                subtitle_review_summary_path(job_dir),
            )

            transcript_segments = _read_transcript_segments(transcript_output_path(job_dir))
            transcript_segments = apply_reviewed_text(transcript_segments, review_document)
            write_transcript_segments(
                transcript_segments,
                reviewed_transcript_output_path(job_dir),
            )
            write_transcript_segments(
                transcript_segments,
                transcript_output_path(job_dir),
            )

            selection_payload = _read_json_file(job_dir / "selected_clips.json")
            selection = CandidateSelection.model_validate(selection_payload)
            selection = apply_reviewed_clip_content(selection, review_document)
            write_selected_clips(selection, job_dir / "selected_clips.json")
            previous_exports = list(
                db.scalars(
                    select(ExportItem).where(ExportItem.job_id == job.id)
                ).all()
            )
            previous_export_ids = {export.id for export in previous_exports}
            render_paths = storage_paths
            if is_rerender:
                rerender_staging_paths = _prepare_subtitle_rerender_staging(
                    storage_paths,
                    job.id,
                    review_document.render_revision,
                )
                render_paths = rerender_staging_paths
            normal_result, short_result, exports, _render_failures_path = _render_selected_outputs(
                db=db,
                job=job,
                video=video,
                input_path=input_path,
                selection=selection,
                transcript_segments=transcript_segments,
                settings=settings,
                storage_paths=render_paths,
                dependencies=deps,
                visited_statuses=visited_statuses,
            )
            if not exports:
                raise PipelineExpectedError(
                    "no_usable_output",
                    "Pipeline completed analysis but produced no usable clips.",
                )
            if rerender_staging_paths is not None and (
                normal_result.failures or short_result.failures
            ):
                raise PipelineExpectedError(
                    "subtitle_rerender_incomplete",
                    "Re-render did not complete for every existing clip. Previous outputs were kept.",
                )
            if rerender_staging_paths is not None:
                exports, _render_failures_path = _promote_subtitle_rerender(
                    db=db,
                    job=job,
                    previous_exports=previous_exports,
                    staged_exports=exports,
                    staged_render_failures_path=_render_failures_path,
                    staging_paths=rerender_staging_paths,
                    storage_paths=storage_paths,
                )
                rerender_promoted = True

            audio_features_payload = _read_json_file(job_dir / "audio_features.json")
            audio_features = AudioFeatures.model_validate(audio_features_payload)
            normal_candidates = _read_model_list(job_dir / "normal_candidates.json", Candidate)
            short_candidates = _read_model_list(job_dir / "short_candidates.json", Candidate)
            scored_candidates = _read_model_list(job_dir / "scored_candidates.json", Candidate)
            candidate_generation_summary = _read_json_file(job_dir / "candidate_generation_summary.json")
            openai_summary_path = job_dir / "openai_scoring_summary.json"
            openai_scoring_summary = _read_json_file(openai_summary_path) if openai_summary_path.is_file() else None
            transcript_summary_path = job_dir / "transcript_summary.json"
            transcript_summary = (
                _read_json_file(transcript_summary_path)
                if transcript_summary_path.is_file()
                else {}
            )

            write_generation_summaries(
                job_dir,
                transcript_segments=transcript_segments,
                audio_features=audio_features,
                normal_candidates=normal_candidates,
                short_candidates=short_candidates,
                candidate_generation_summary=candidate_generation_summary,
                scored_candidates=scored_candidates,
                selection=selection,
                openai_scoring_summary=openai_scoring_summary,
                normal_result=normal_result,
                short_result=short_result,
                exports=exports,
                transcription_engine=str(transcript_summary.get("transcription_engine", "not_run")),
                used_fixture_transcript=bool(transcript_summary.get("used_fixture_transcript", False)),
                transcription_model=transcript_summary.get("transcription_model"),
                transcription_language=transcript_summary.get("transcription_language"),
                transcription_diagnostics=transcript_summary.get("transcription_runtime"),
            )

            _set_status(db, job, "packaging_zip")
            visited_statuses.append("packaging_zip")
            review_document = mark_review_completed(review_document)
            write_subtitle_review(review_document, review_path)
            write_subtitle_review_summary(
                review_document,
                subtitle_review_summary_path(job_dir),
            )
            zip_path = storage_paths.zip_path(job.id)
            if is_rerender:
                pending_rerender_zip = (
                    job_dir
                    / f".download_revision_{review_document.render_revision}.tmp.zip"
                )
                pending_rerender_zip.unlink(missing_ok=True)
                _create_zip(
                    pending_rerender_zip,
                    exports,
                    metadata_files=_top_level_metadata_files(job_dir),
                )
                pending_rerender_zip.replace(zip_path)
                pending_rerender_zip = None
            else:
                _create_zip(
                    zip_path,
                    exports,
                    metadata_files=_top_level_metadata_files(job_dir),
                )

            _set_status(db, job, "completed")
            visited_statuses.append("completed")
        except PipelineExpectedError as exc:
            if pending_rerender_zip is not None:
                pending_rerender_zip.unlink(missing_ok=True)
            if is_rerender and review_document is not None:
                if rerender_staging_paths is not None and not rerender_promoted:
                    _discard_subtitle_rerender_staging(
                        db=db,
                        job_id=job.id,
                        previous_export_ids=previous_export_ids,
                        staging_paths=rerender_staging_paths,
                    )
                _restore_subtitle_rerender_for_retry(
                    db=db,
                    job=job,
                    review_document=review_document,
                    review_path=review_path,
                    code=exc.code,
                    message=exc.message,
                )
            else:
                _fail_job(db, job_id, exc.code, exc.message, details=exc.details)
        except Exception as exc:
            if pending_rerender_zip is not None:
                pending_rerender_zip.unlink(missing_ok=True)
            if is_rerender and review_document is not None:
                if rerender_staging_paths is not None and not rerender_promoted:
                    _discard_subtitle_rerender_staging(
                        db=db,
                        job_id=job.id,
                        previous_export_ids=previous_export_ids,
                        staging_paths=rerender_staging_paths,
                    )
                _restore_subtitle_rerender_for_retry(
                    db=db,
                    job=job,
                    review_document=review_document,
                    review_path=review_path,
                    code="subtitle_review_render_failed",
                    message=str(exc),
                )
            else:
                _fail_job(db, job_id, "subtitle_review_render_failed", str(exc))
            raise

    return visited_statuses
