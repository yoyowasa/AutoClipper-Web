from app.storage.completed_previews import prune_job_previews_after_completion
from app.clip_allocation import is_ai_allocation, allocate_selection, allocation_summary, candidate_pool_counts
from app.jobs.character_asset_harvest_state import enqueue_completed_job_harvest
import json
from app.duration_rules import duration_search_settings
import re
import unicodedata
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio.silence_detect import SilenceSegment, detect_silence, silence_output_path, write_silence_segments
from app.audio.transcript_postprocess import (
    deterministic_transcript_output_path,
    finalize_transcript_width,
    postprocess_transcript_segments,
    raw_transcript_output_path,
    transcript_postprocess_summary_path,
    write_transcript_postprocess_summary,
)
from app.audio.transcribe_faster_whisper import (
    DEFAULT_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
    DEFAULT_TRANSCRIPTION_CHUNK_SECONDS,
    TranscriptSegment,
    transcript_output_path,
    write_transcript_segments,
)
from app.audio.transcription_runtime import (
    TRANSCRIPTION_COMPUTE_TYPES,
    TRANSCRIPTION_DEVICES,
    TranscriptionRuntimeError,
)
from app.audio.volume_features import (
    AudioFeatures,
    audio_features_output_path,
    build_audio_features,
    write_audio_features,
)
from app.candidates.codex_initial_selection import (
    CodexInitialSelectionError,
    codex_initial_selection_summary_output_path,
    write_codex_initial_selection_summary,
)
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
    CandidateGenerationResult,
    CandidateGenerationMemoryLimitError,
    merge_candidate_generation_summaries,
    write_candidates,
)
from app.candidates.select_candidates import (
    CandidateSelection,
    select_candidates,
    write_selected_clips,
)
from app.config import get_settings
from app.db import SessionLocal
from app.ids import make_id
from app.jobs.clip_plan import (
    build_clip_plan,
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_approved,
    write_clip_plan,
)
from app.jobs.automation import (
    AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING,
    automation_manifest_path,
    build_automation_manifest,
    write_automation_manifest,
)
from app.jobs.quality_gate import (
    QualityGateDecision,
    evaluate_content_quality_gate,
    evaluate_post_render_quality_gate,
    invalidate_quality_gate_decisions,
    quality_gate_decision_path,
    unknown_quality_gate_decision,
)
from app.jobs.publication_state import (
    clear_rerender_publication_unresolved,
    mark_rerender_publication_unresolved,
    rerender_publication_is_unresolved,
    try_acquire_rerender_publication_lease,
)
from app.jobs.manual_workflow import (
    apply_manual_clip_metadata,
    build_manual_selection,
    is_manual_workflow,
    manual_edit_is_finalized,
    manual_subtitle_mode,
)
from app.jobs.summaries import write_generation_summaries
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    apply_reviewed_text,
    build_manual_subtitle_segments,
    build_subtitle_review,
    load_subtitle_review,
    mark_review_completed,
    mark_review_rendering,
    queue_auto_review_render,
    queue_review_render,
    refresh_review_overlay_title_expectations,
    reviewed_transcript_output_path,
    subtitle_review_source_path,
    restore_review_after_render_failure,
    subtitle_review_output_path,
    subtitle_review_summary_path,
    update_review_hook_scene,
    write_subtitle_review,
    write_subtitle_review_summary,
)
from app.jobs.subtitle_review_preview import (
    current_subtitle_review_preview_spec,
    exact_subtitle_review_preview_is_ready,
    exact_subtitle_review_preview_error_path,
    live_subtitle_review_preview_is_ready,
    live_subtitle_review_preview_url,
    refresh_subtitle_review_preview_states,
    subtitle_review_document_lock,
    subtitle_review_preview_url as exact_subtitle_review_preview_url,
    write_subtitle_review_preview_error,
)
from app.jobs.thumbnails import (
    generate_export_thumbnails,
    read_export_metadata,
    thumbnail_path_from_export,
)
from app.jobs.title_hook_suggestions import (
    TitleHookSuggestionsDocument,
    apply_recommended_title_hook_suggestions,
    load_title_hook_suggestions,
    title_hook_suggestions_path,
)
from app.models import ExportItem, Job, Video, utc_now
from app.candidates.used_ranges import (
    unused_items,
    used_ranges,
)
from app.source_clip_history import (
    record_completed_exports,
)
from app.posting_metadata import write_youtube_posting_artifacts
from app.render.render_normal import NormalRenderBatchResult, render_selected_normal_candidates
from app.render.render_exact_review_preview import (
    ExactPreviewResult,
    build_live_subtitle_review_preview_spec,
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
    subtitle_review_preview_spec_hash,
)
from app.render.render_manual_source_proxy import (
    manual_source_proxy_path,
    manual_source_proxy_url,
)
from app.render.render_short import ShortRenderBatchResult, render_selected_short_candidates
from app.scoring.heatmap import annotate_candidates_with_heatmap
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.black_screen import (
    VisualQuality,
    build_visual_quality,
    visual_quality_output_path,
    write_visual_quality,
)
from app.video.heatmap import HeatmapSegment, load_heatmap_for_video
from app.video.probe import VideoMetadata
from app.video.scene_detect import SceneSegment, scene_output_path, scene_segments_from_boundaries, write_scene_segments


from app.jobs.pipeline_common import (
    AutoClipperPipelineDependencies as AutoClipperPipelineDependencies,
    ComputeAudioFeatures,
    DetectBlackScreen,
    DetectScenes,
    DetectSilence,
    PipelineExpectedError as PipelineExpectedError,
    SessionFactory,
    TranscriptionEngineFactory,
    _active_quality_gate_mode,
    _assign_status,
    _bool_setting,
    _codex_initial_selection_enabled,
    _evaluate_selection_quality_gate_for_mode,
    _heartbeat_job,
    _heatmap_summary_for_selection_mode,
    _int_setting,
    _prepare_clip_plan_review,
    _read_json_file,
    _read_transcript_segments,
    _score_local_candidates,
    _selection_with_fallback_titles,
    _filter_user_rejections,
    _set_status,
    _settings_with_source_history,
    _transcript_text,
    _try_write_quality_gate_decision,
    _unused_candidates,
    _write_json,
)

# RQ互換: 保存済みの仕事は runner の旧パスで関数を読み込む。
from app.jobs.clip_plan_runner import (
    _automatic_selection_with_diverse_refined_shorts,
    _codex_selection_with_diverse_refined_shorts,
    run_clip_plan_boundary_update as run_clip_plan_boundary_update,
    run_clip_plan_hook_scene_update as run_clip_plan_hook_scene_update,
    run_clip_plan_reselection as run_clip_plan_reselection,
)

MIN_AUDIO_VOLUME_PEAK = 0.005
MAX_AUDIO_SILENCE_RATIO = 0.98
MIN_AUDIO_SPEECH_SECONDS = 1.0
MIN_AUDIO_SPEECH_DENSITY = 0.02
MAX_AV_STREAM_DURATION_DRIFT_SECONDS = 30.0
MAX_AV_STREAM_DURATION_DRIFT_RATIO = 0.1

MIN_TRANSCRIPT_TEXT_LENGTH = 20
MIN_TRANSCRIPT_SPEECH_SECONDS = 3.0
MIN_AVERAGE_TRANSCRIPT_CONFIDENCE = 0.25
MIN_REPEATED_SEGMENT_COUNT = 5
MIN_REPEATED_SEGMENT_RATIO = 0.6
MIN_REPEATED_SEGMENT_TEXT_LENGTH = 6
MIN_CLUSTERED_REPEATED_SEGMENT_COUNT = 20
MIN_CLUSTERED_REPEATED_SEGMENT_RATIO = 0.65
MAX_CLUSTERED_REPEATED_UNIQUE_RATIO = 0.35
LONG_FORM_TRANSCRIPTION_SECONDS = 30 * 60
MIN_LONG_FORM_EXPECTED_SPEECH_SECONDS = 5 * 60
MIN_LONG_FORM_TRANSCRIPT_AUDIO_COVERAGE = 0.08
MIN_LONG_FORM_TRANSCRIPT_CHARACTERS_PER_MINUTE = 12.0
TRANSCRIPTION_RECOVERY_SUMMARY_FILENAME = "transcription_recovery_summary.json"
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


WHISPER_MODEL_SIZES = {"base", "small", "medium", "large-v3", "turbo"}


def _whisper_model_size_setting(settings: dict[str, Any]) -> str:
    value = settings.get("whisperModelSize") or settings.get("whisper_model_size") or "base"
    normalized = str(value).strip()
    return normalized if normalized in WHISPER_MODEL_SIZES else "base"


def _transcription_language_setting(_settings: dict[str, Any]) -> str:
    return "ja"


def _transcription_device_setting(settings: dict[str, Any]) -> str:
    value = settings.get("transcriptionDevice") or settings.get("transcription_device") or "cpu"
    normalized = str(value).strip().lower()
    return normalized if normalized in TRANSCRIPTION_DEVICES else "cpu"


def _transcription_compute_type_setting(settings: dict[str, Any]) -> str:
    value = settings.get("transcriptionComputeType") or settings.get("transcription_compute_type") or "auto"
    normalized = str(value).strip().lower()
    return normalized if normalized in TRANSCRIPTION_COMPUTE_TYPES else "auto"


def _float_setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


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
    if difference <= MAX_AV_STREAM_DURATION_DRIFT_SECONDS or relative_difference <= MAX_AV_STREAM_DURATION_DRIFT_RATIO:
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
    if audio_features.silence_ratio >= MAX_AUDIO_SILENCE_RATIO and audio_features.speech_seconds <= MIN_AUDIO_SPEECH_SECONDS:
        return True
    return audio_features.speech_density <= MIN_AUDIO_SPEECH_DENSITY and audio_features.speech_seconds <= MIN_AUDIO_SPEECH_SECONDS


def _raise_if_audio_unusable(audio_features: AudioFeatures) -> None:
    if not _audio_is_silent_or_unusable(audio_features):
        return
    details = _audio_diagnostics(audio_features)
    raise PipelineExpectedError(
        "audio_silent_or_unusable",
        "Audio is silent or too weak for reliable transcription.",
        details=details,
    )


def _transcript_speech_duration(segments: Sequence[TranscriptSegment]) -> float:
    return sum(max(0.0, segment.end - segment.start) for segment in segments if segment.text.strip())


def _average_transcript_confidence(segments: Sequence[TranscriptSegment]) -> float | None:
    values = [segment.confidence for segment in segments if segment.confidence is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _transcript_has_repeated_low_information_text(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", unicodedata.normalize("NFKC", text).lower())
    if len(words) < 5:
        return False
    counts = Counter(words)
    word, count = counts.most_common(1)[0]
    return word in LOW_INFORMATION_WORDS and count / len(words) >= 0.8


def _normalized_segment_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold(), flags=re.UNICODE)


def _repeated_segment_diagnostics(segments: Sequence[TranscriptSegment]) -> dict[str, Any]:
    normalized_texts = [normalized for segment in segments if (normalized := _normalized_segment_text(segment.text))]
    if not normalized_texts:
        return {
            "dominant_segment_count": 0,
            "dominant_segment_ratio": 0.0,
            "unique_segment_text_ratio": 0.0,
            "repeated_segment_text": False,
            "clustered_repeated_segment_count": 0,
            "clustered_repeated_segment_ratio": 0.0,
            "clustered_repeated_segment_text": False,
        }

    counts = Counter(normalized_texts)
    dominant_text, dominant_count = counts.most_common(1)[0]
    dominant_ratio = dominant_count / len(normalized_texts)
    unique_ratio = len(counts) / len(normalized_texts)
    clustered_count = sum(count for _text, count in counts.most_common(3) if count >= MIN_REPEATED_SEGMENT_COUNT)
    clustered_ratio = clustered_count / len(normalized_texts)
    return {
        "dominant_segment_count": dominant_count,
        "dominant_segment_ratio": round(dominant_ratio, 6),
        "unique_segment_text_ratio": round(unique_ratio, 6),
        "repeated_segment_text": (
            len(dominant_text) >= MIN_REPEATED_SEGMENT_TEXT_LENGTH
            and dominant_count >= MIN_REPEATED_SEGMENT_COUNT
            and dominant_ratio >= MIN_REPEATED_SEGMENT_RATIO
        ),
        "clustered_repeated_segment_count": clustered_count,
        "clustered_repeated_segment_ratio": round(clustered_ratio, 6),
        "clustered_repeated_segment_text": (
            len(normalized_texts) >= MIN_CLUSTERED_REPEATED_SEGMENT_COUNT
            and clustered_count >= MIN_CLUSTERED_REPEATED_SEGMENT_COUNT
            and clustered_ratio >= MIN_CLUSTERED_REPEATED_SEGMENT_RATIO
            and unique_ratio <= MAX_CLUSTERED_REPEATED_UNIQUE_RATIO
        ),
    }


def _transcript_diagnostics(
    segments: Sequence[TranscriptSegment],
    *,
    timeline_duration: float | None = None,
    expected_speech_seconds: float | None = None,
) -> dict[str, Any]:
    text = _transcript_text(segments)
    average_confidence = _average_transcript_confidence(segments)
    transcript_speech_duration = _transcript_speech_duration(segments)
    details: dict[str, Any] = {
        "segment_count": len(segments),
        "total_text_length": len(text),
        "total_speech_duration": round(transcript_speech_duration, 6),
        **_repeated_segment_diagnostics(segments),
    }
    if timeline_duration is not None and timeline_duration > 0:
        details["timeline_duration"] = round(timeline_duration, 6)
        details["characters_per_minute"] = round(
            len(text) / (timeline_duration / 60),
            6,
        )
    if expected_speech_seconds is not None and expected_speech_seconds > 0:
        details["expected_speech_seconds"] = round(expected_speech_seconds, 6)
        details["transcript_audio_coverage"] = round(
            transcript_speech_duration / expected_speech_seconds,
            6,
        )
    if average_confidence is not None:
        details["average_confidence"] = round(average_confidence, 6)
    return details


def _transcript_unusable_reasons(
    segments: Sequence[TranscriptSegment],
    *,
    timeline_duration: float | None = None,
    expected_speech_seconds: float | None = None,
) -> list[str]:
    details = _transcript_diagnostics(
        segments,
        timeline_duration=timeline_duration,
        expected_speech_seconds=expected_speech_seconds,
    )
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
    if details["repeated_segment_text"]:
        reasons.append("repeated_segment_text")
    if (
        details["clustered_repeated_segment_text"]
        and timeline_duration is not None
        and timeline_duration >= LONG_FORM_TRANSCRIPTION_SECONDS
        and average_confidence is not None
        and average_confidence < 0.5
        and details.get("transcript_audio_coverage", 1.0) < MIN_LONG_FORM_TRANSCRIPT_AUDIO_COVERAGE
        and details.get("characters_per_minute", MIN_LONG_FORM_TRANSCRIPT_CHARACTERS_PER_MINUTE)
        < MIN_LONG_FORM_TRANSCRIPT_CHARACTERS_PER_MINUTE
    ):
        reasons.append("clustered_repeated_segment_text")
    if (
        timeline_duration is not None
        and timeline_duration >= LONG_FORM_TRANSCRIPTION_SECONDS
        and expected_speech_seconds is not None
        and expected_speech_seconds >= MIN_LONG_FORM_EXPECTED_SPEECH_SECONDS
        and details.get("transcript_audio_coverage", 1.0) < MIN_LONG_FORM_TRANSCRIPT_AUDIO_COVERAGE
        and details.get("characters_per_minute", MIN_LONG_FORM_TRANSCRIPT_CHARACTERS_PER_MINUTE)
        < MIN_LONG_FORM_TRANSCRIPT_CHARACTERS_PER_MINUTE
    ):
        reasons.append("long_form_transcript_too_sparse")
    return reasons


def _transcript_quality_diagnostics(
    segments: Sequence[TranscriptSegment],
    *,
    timeline_duration: float | None = None,
    expected_speech_seconds: float | None = None,
) -> dict[str, Any]:
    details = _transcript_diagnostics(
        segments,
        timeline_duration=timeline_duration,
        expected_speech_seconds=expected_speech_seconds,
    )
    details["reasons"] = _transcript_unusable_reasons(
        segments,
        timeline_duration=timeline_duration,
        expected_speech_seconds=expected_speech_seconds,
    )
    return details


def _raise_if_transcript_unusable(
    segments: Sequence[TranscriptSegment],
    *,
    timeline_duration: float | None = None,
    expected_speech_seconds: float | None = None,
) -> None:
    details = _transcript_quality_diagnostics(
        segments,
        timeline_duration=timeline_duration,
        expected_speech_seconds=expected_speech_seconds,
    )
    reasons = details["reasons"]

    if not reasons:
        return

    raise PipelineExpectedError(
        "transcript_unusable",
        ("音声から信頼できる字幕を生成できませんでした。日本語固定またはGPU推奨設定で再試行してください。"),
        details=details,
    )


def _should_retry_transcription_with_small(
    *,
    model: str,
    language: str,
    diagnostics: dict[str, Any],
    reasons: Sequence[str],
) -> bool:
    return bool(reasons and model == "turbo" and language == "ja" and diagnostics.get("actual_device") == "cuda")


def _should_retry_long_form_transcription_in_chunks(
    *,
    duration: float,
    diagnostics: dict[str, Any],
    reasons: Sequence[str],
) -> bool:
    return bool(duration >= LONG_FORM_TRANSCRIPTION_SECONDS and reasons and diagnostics.get("actual_device") == "cuda")


def _transcribe_with_faster_whisper(
    factory: TranscriptionEngineFactory,
    audio_path: Path,
    *,
    model: str,
    language: str,
    device: str,
    compute_type: str,
) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    engine = factory(
        model_size=model,
        device=device,
        compute_type=compute_type,
        language=language,
    )
    segments = engine.transcribe(audio_path)
    return segments, dict(engine.diagnostics)


def _transcribe_with_faster_whisper_in_chunks(
    factory: TranscriptionEngineFactory,
    audio_path: Path,
    *,
    model: str,
    language: str,
    device: str,
    compute_type: str,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    engine = factory(
        model_size=model,
        device=device,
        compute_type=compute_type,
        language=language,
    )
    segments = engine.transcribe_chunked(
        audio_path,
        chunk_seconds=DEFAULT_TRANSCRIPTION_CHUNK_SECONDS,
        overlap_seconds=DEFAULT_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
        progress_callback=progress_callback,
    )
    return segments, dict(engine.diagnostics)


def _chunked_transcription_diagnostics(
    *,
    primary: dict[str, Any],
    primary_quality: dict[str, Any],
    chunked: dict[str, Any],
    chunked_quality: dict[str, Any],
) -> dict[str, Any]:
    primary_load_seconds = float(primary.get("model_load_seconds") or 0.0)
    primary_transcription_seconds = float(primary.get("transcription_seconds") or 0.0)
    chunked_load_seconds = float(chunked.get("model_load_seconds") or 0.0)
    chunked_transcription_seconds = float(chunked.get("transcription_seconds") or 0.0)
    peak_values = [int(value) for value in (primary.get("peak_vram_mb"), chunked.get("peak_vram_mb")) if isinstance(value, (int, float))]
    return {
        **chunked,
        "requested_model": primary.get("model"),
        "actual_model": chunked.get("model"),
        "model_load_seconds": round(primary_load_seconds + chunked_load_seconds, 3),
        "transcription_seconds": round(
            primary_transcription_seconds + chunked_transcription_seconds,
            3,
        ),
        "peak_vram_mb": max(peak_values) if peak_values else None,
        "quality_fallback_used": True,
        "quality_fallback_reason": "primary_transcript_unusable",
        "chunked_quality_fallback_used": True,
        "selected_attempt": "chunked_same_model",
        "selected_attempt_reason": "primary_transcript_unusable",
        "primary_transcription": primary,
        "primary_transcript_quality": primary_quality,
        "chunked_transcription": chunked,
        "chunked_transcript_quality": chunked_quality,
    }


def _fallback_transcription_diagnostics(
    *,
    primary: dict[str, Any],
    primary_quality: dict[str, Any],
    fallback: dict[str, Any],
    fallback_quality: dict[str, Any],
) -> dict[str, Any]:
    primary_load_seconds = float(primary.get("model_load_seconds") or 0.0)
    primary_transcription_seconds = float(primary.get("transcription_seconds") or 0.0)
    fallback_load_seconds = float(fallback.get("model_load_seconds") or 0.0)
    fallback_transcription_seconds = float(fallback.get("transcription_seconds") or 0.0)
    peak_values = [int(value) for value in (primary.get("peak_vram_mb"), fallback.get("peak_vram_mb")) if isinstance(value, (int, float))]
    return {
        **fallback,
        "requested_model": primary.get("model"),
        "actual_model": fallback.get("model"),
        "model_load_seconds": round(primary_load_seconds + fallback_load_seconds, 3),
        "transcription_seconds": round(
            primary_transcription_seconds + fallback_transcription_seconds,
            3,
        ),
        "peak_vram_mb": max(peak_values) if peak_values else None,
        "quality_fallback_used": True,
        "quality_fallback_reason": "primary_transcript_unusable",
        "selected_attempt": ("small_ja_chunked" if fallback.get("chunked") else "small_ja_whole_file"),
        "selected_attempt_reason": "previous_transcript_unusable",
        "primary_transcription": primary,
        "primary_transcript_quality": primary_quality,
        "fallback_transcription": fallback,
        "fallback_transcript_quality": fallback_quality,
    }


def _write_transcription_recovery_failure_summary(
    output_dir: Path,
    *,
    prior: dict[str, Any],
    prior_quality: dict[str, Any],
    fallback_chunked: bool,
    exc: Exception,
) -> Path:
    attempts: list[dict[str, Any]] = []
    if prior.get("chunked_quality_fallback_used") is True:
        attempts.extend(
            [
                {
                    "name": "primary_whole_file",
                    "status": "completed_unusable",
                    "runtime": prior.get("primary_transcription", {}),
                    "quality": prior.get("primary_transcript_quality", {}),
                },
                {
                    "name": "chunked_same_model",
                    "status": "completed_unusable",
                    "runtime": prior.get("chunked_transcription", {}),
                    "quality": prior.get("chunked_transcript_quality", prior_quality),
                },
            ]
        )
    else:
        attempts.append(
            {
                "name": "primary_whole_file",
                "status": "completed_unusable",
                "runtime": prior.get("primary_transcription", prior),
                "quality": prior.get("primary_transcript_quality", prior_quality),
            }
        )
        if "chunked_quality_fallback_used" in prior:
            attempts.append(
                {
                    "name": "chunked_same_model",
                    "status": "failed",
                    "error_type": prior.get("chunked_quality_fallback_error_type"),
                }
            )

    failed_attempt = "small_ja_chunked" if fallback_chunked else "small_ja_whole_file"
    failure: dict[str, Any] = {
        "name": failed_attempt,
        "status": "failed",
        "error_type": type(exc).__name__,
    }
    if isinstance(exc, TranscriptionRuntimeError):
        failure["error_code"] = exc.code
        failure["error_details"] = exc.details
    attempts.append(failure)

    runtime = {
        **prior,
        "quality_fallback_used": True,
        "quality_fallback_reason": "previous_transcript_unusable",
        "selected_attempt": None,
        "failed_attempt": failed_attempt,
        "fallback_error_type": type(exc).__name__,
    }
    if isinstance(exc, TranscriptionRuntimeError):
        runtime["fallback_error_code"] = exc.code
        runtime["fallback_error_details"] = exc.details
    return _write_json(
        output_dir / TRANSCRIPTION_RECOVERY_SUMMARY_FILENAME,
        {
            "recovery_failed": True,
            "selected_model": None,
            "selected_language": None,
            "selected_quality": prior_quality,
            "attempts": attempts,
            "runtime": runtime,
        },
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
            "selected_above_threshold_count": sum(1 for candidate in selected if candidate.below_quality_threshold is False),
            "selected_below_threshold_backfill_count": sum(1 for candidate in selected if candidate.below_quality_threshold is True),
        }
    )


def _render_failures_to_jsonable(
    normal_result: NormalRenderBatchResult | None,
    short_result: ShortRenderBatchResult | None,
) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    if normal_result is not None:
        payload.extend(
            {"type": "normal", "candidate_id": failure.candidate_id, "error": failure.error} for failure in normal_result.failures
        )
    if short_result is not None:
        payload.extend({"type": "short", "candidate_id": failure.candidate_id, "error": failure.error} for failure in short_result.failures)
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
    resolved_job_dir = zip_path.parent.resolve(strict=False)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for export in exports:
            for value in (export.video_path, export.subtitle_path, export.metadata_path):
                if not value:
                    continue
                path = Path(value)
                if path.is_file():
                    archive.write(path, arcname=_zip_export_arcname(export, path, value))
            thumbnail_path = thumbnail_path_from_export(export)
            if thumbnail_path is not None:
                try:
                    thumbnail_path.resolve(strict=False).relative_to(resolved_job_dir)
                except (OSError, ValueError):
                    thumbnail_path = None
            if thumbnail_path is not None and thumbnail_path.is_file():
                archive.write(
                    thumbnail_path,
                    arcname=(
                        f"thumbnails/{_zip_type_dir(export.type)}/{thumbnail_path.name}"
                    ),
                )
        for metadata_file in metadata_files or []:
            if metadata_file.is_file():
                archive.write(metadata_file, arcname=f"metadata/{metadata_file.name}")


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
    asset_storage_paths: StoragePaths | None = None,
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
        short_top_banner_enabled=bool(settings.get("shortTopBannerEnabled", False)),
        short_bottom_banner_enabled=bool(settings.get("shortBottomBannerEnabled", False)),
        banner_paths=asset_storage_paths,
    )

    render_failures_path = _write_json(
        storage_paths.job_outputs(job.id) / "render_failures.json",
        _render_failures_to_jsonable(normal_result, short_result),
    )
    exports = [*normal_result.exports, *short_result.exports]
    return normal_result, short_result, exports, render_failures_path


def _discard_unpublished_exports(
    db: Session,
    exports: Sequence[ExportItem],
    *,
    job_dir: Path,
) -> None:
    resolved_job_dir = job_dir.resolve()
    for export in exports:
        thumbnail_path = thumbnail_path_from_export(export)
        values = [export.video_path, export.subtitle_path]
        if thumbnail_path is not None:
            values.append(str(thumbnail_path))
        values.append(export.metadata_path)
        for value in values:
            if not value:
                continue
            candidate_path = Path(value)
            try:
                resolved_path = candidate_path.resolve()
                resolved_path.relative_to(resolved_job_dir)
            except (OSError, ValueError):
                continue
            try:
                resolved_path.unlink(missing_ok=True)
            except OSError:
                continue
        db.delete(export)
    db.commit()


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
    *,
    attempt_id: str | None = None,
) -> StoragePaths:
    attempt_suffix = (attempt_id or make_id("attempt"))[-8:]
    staging_root = (
        storage_paths.temp
        / "rr"
        / f"{job_id[-12:]}_r{render_revision}_{attempt_suffix}"
    )
    staging_paths = _RerenderStoragePaths(staging_root)
    staging_paths.ensure()
    return staging_paths


def _promote_staged_export_file(
    source_value: str | None,
    *,
    staging_job_dir: Path,
    canonical_job_dir: Path,
    promotion: "_SubtitleRerenderPromotion",
) -> str | None:
    if source_value is None:
        return None
    source = Path(source_value)
    relative_path = source.resolve().relative_to(staging_job_dir.resolve())
    destination = canonical_job_dir / relative_path
    promotion.publish(source, destination)
    return str(destination)


@dataclass
class _RerenderFileChange:
    destination: Path
    backup: Path
    original_backed_up: bool = False
    new_published: bool = False


@dataclass
class _SubtitleRerenderPromotion:
    staging_root: Path
    canonical_job_dir: Path
    changes: list[_RerenderFileChange]

    @property
    def backup_root(self) -> Path:
        return self.staging_root / ".canonical_backup"

    def publish(self, source: Path, destination: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        resolved_destination = destination.resolve(strict=False)
        resolved_destination.relative_to(self.canonical_job_dir.resolve(strict=False))
        if any(change.destination == resolved_destination for change in self.changes):
            raise ValueError(f"duplicate rerender promotion destination: {resolved_destination}")

        backup = self.backup_root / f"{len(self.changes):04d}" / destination.name
        change = _RerenderFileChange(
            destination=resolved_destination,
            backup=backup,
        )
        self.changes.append(change)
        resolved_destination.parent.mkdir(parents=True, exist_ok=True)
        if resolved_destination.exists():
            if not resolved_destination.is_file():
                raise ValueError(f"rerender promotion destination is not a file: {resolved_destination}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            resolved_destination.replace(backup)
            change.original_backed_up = True
        source.replace(resolved_destination)
        change.new_published = True

    def remove(self, destination: Path) -> None:
        resolved_destination = destination.resolve(strict=False)
        resolved_destination.relative_to(self.canonical_job_dir.resolve(strict=False))
        if any(change.destination == resolved_destination for change in self.changes):
            raise ValueError(f"duplicate rerender promotion destination: {resolved_destination}")

        backup = self.backup_root / f"{len(self.changes):04d}" / destination.name
        change = _RerenderFileChange(
            destination=resolved_destination,
            backup=backup,
        )
        self.changes.append(change)
        if resolved_destination.exists():
            if not resolved_destination.is_file():
                raise ValueError(f"rerender promotion destination is not a file: {resolved_destination}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            resolved_destination.replace(backup)
            change.original_backed_up = True

    def rollback(self) -> None:
        failures: list[str] = []
        for change in reversed(self.changes):
            try:
                if change.new_published:
                    change.destination.unlink(missing_ok=True)
                if change.original_backed_up:
                    if not change.backup.is_file():
                        raise FileNotFoundError(change.backup)
                    change.destination.parent.mkdir(parents=True, exist_ok=True)
                    change.backup.replace(change.destination)
            except OSError as exc:
                failures.append(f"{change.destination}: {exc.__class__.__name__}")
        if failures:
            raise RuntimeError("; ".join(failures))

    def finalize(self) -> None:
        shutil.rmtree(self.canonical_job_dir / "audit", ignore_errors=True)
        shutil.rmtree(self.staging_root, ignore_errors=True)


class _SubtitleRerenderRollbackError(RuntimeError):
    pass


def _thumbnail_metadata_by_candidate_id(
    exports: Sequence[ExportItem],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(export.candidate_id): read_export_metadata(export)
        for export in exports
        if export.candidate_id is not None
    }


def _write_youtube_posting_artifacts_for_publication(
    clips: Sequence[Any],
    exports: Sequence[ExportItem],
    *,
    job_dir: Path,
    staging_job_dir: Path | None = None,
    promotion: _SubtitleRerenderPromotion | None = None,
) -> list[Path]:
    if (staging_job_dir is None) != (promotion is None):
        raise ValueError("posting artifact staging and promotion must be supplied together")
    output_dir = staging_job_dir or job_dir
    written_paths = write_youtube_posting_artifacts(
        clips,
        output_dir,
        thumbnail_metadata_by_clip_id=_thumbnail_metadata_by_candidate_id(exports),
        thumbnail_root=job_dir,
    )
    if promotion is None:
        return written_paths

    published_paths: list[Path] = []
    for written_path in written_paths:
        destination = job_dir / written_path.name
        promotion.publish(written_path, destination)
        published_paths.append(destination)
    return published_paths


def _project_staged_exports_for_quality_gate(
    staged_exports: Sequence[ExportItem],
    *,
    staging_job_dir: Path,
    canonical_job_dir: Path,
) -> list[dict[str, Any]]:
    def project_path(value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        source_path = Path(value)
        relative_path = source_path.resolve().relative_to(resolved_staging_dir)
        return str(canonical_job_dir / relative_path), str(source_path)

    projected: list[dict[str, Any]] = []
    resolved_staging_dir = staging_job_dir.resolve()
    for export in staged_exports:
        video_path, inspection_video_path = project_path(export.video_path)
        subtitle_path, inspection_subtitle_path = project_path(
            getattr(export, "subtitle_path", None)
        )
        metadata_path, inspection_metadata_path = project_path(
            getattr(export, "metadata_path", None)
        )
        projected.append(
            {
                "id": export.id,
                "candidateId": export.candidate_id,
                "type": export.type,
                "videoPath": video_path,
                "subtitlePath": subtitle_path,
                "metadataPath": metadata_path,
                "inspectionVideoPath": inspection_video_path,
                "inspectionSubtitlePath": inspection_subtitle_path,
                "inspectionMetadataPath": inspection_metadata_path,
            }
        )
    return projected


def _rewrite_export_metadata_paths(
    export: ExportItem,
    *,
    thumbnail_path: str | None = None,
) -> None:
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
    if "thumbnail_path" in payload:
        payload["thumbnail_path"] = thumbnail_path
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
) -> tuple[list[ExportItem], Path, _SubtitleRerenderPromotion]:
    staging_job_dir = staging_paths.job_outputs(job.id)
    canonical_job_dir = storage_paths.job_outputs(job.id)
    promotion = _SubtitleRerenderPromotion(
        staging_root=staging_paths.root,
        canonical_job_dir=canonical_job_dir,
        changes=[],
    )
    previous_thumbnails = {
        previous.candidate_id: thumbnail_path_from_export(previous)
        for previous in previous_exports
        if previous.candidate_id is not None
    }

    try:
        for export in staged_exports:
            staged_thumbnail_path = thumbnail_path_from_export(export)
            from app.jobs.thumbnail_candidates import candidate_directory
            frame_directory = candidate_directory(staging_job_dir, export.id)
            for cached_frame in sorted(frame_directory.glob("*.jpg")):
                _promote_staged_export_file(
                    str(cached_frame), staging_job_dir=staging_job_dir,
                    canonical_job_dir=canonical_job_dir, promotion=promotion,
                )
            expected_thumbnail_path = (
                canonical_job_dir
                / "thumbnails"
                / _zip_type_dir(export.type)
                / f"{Path(export.video_path).stem}.jpg"
            )
            export.video_path = (
                _promote_staged_export_file(
                    export.video_path,
                    staging_job_dir=staging_job_dir,
                    canonical_job_dir=canonical_job_dir,
                    promotion=promotion,
                )
                or export.video_path
            )
            export.subtitle_path = _promote_staged_export_file(
                export.subtitle_path,
                staging_job_dir=staging_job_dir,
                canonical_job_dir=canonical_job_dir,
                promotion=promotion,
            )
            if staged_thumbnail_path is not None:
                promoted_thumbnail_path = _promote_staged_export_file(
                    str(staged_thumbnail_path),
                    staging_job_dir=staging_job_dir,
                    canonical_job_dir=canonical_job_dir,
                    promotion=promotion,
                )
            else:
                previous_thumbnail_path = previous_thumbnails.get(export.candidate_id)
                if previous_thumbnail_path is not None:
                    try:
                        previous_thumbnail_path.resolve(strict=False).relative_to(
                            canonical_job_dir.resolve(strict=False)
                        )
                    except (OSError, ValueError):
                        previous_thumbnail_path = None
                promotion.remove(previous_thumbnail_path or expected_thumbnail_path)
                promoted_thumbnail_path = None
            export.metadata_path = _promote_staged_export_file(
                export.metadata_path,
                staging_job_dir=staging_job_dir,
                canonical_job_dir=canonical_job_dir,
                promotion=promotion,
            )
            _rewrite_export_metadata_paths(
                export,
                thumbnail_path=promoted_thumbnail_path,
            )

        successful_candidate_ids = {
            export.candidate_id
            for export in staged_exports
            if export.candidate_id is not None
        }
        preserved_exports: list[ExportItem] = []
        for previous in previous_exports:
            if previous.candidate_id in successful_candidate_ids:
                db.delete(previous)
            else:
                preserved_exports.append(previous)

        canonical_render_failures_path = canonical_job_dir / "render_failures.json"
        if staged_render_failures_path.is_file():
            promotion.publish(
                staged_render_failures_path,
                canonical_render_failures_path,
            )

        db.flush()
        current_exports = sorted(
            [*preserved_exports, *staged_exports],
            key=lambda export: (export.type, export.video_path),
        )
        return current_exports, canonical_render_failures_path, promotion
    except Exception as exc:
        rollback_failures: list[Exception] = []
        try:
            db.rollback()
        except Exception as rollback_exc:
            rollback_failures.append(rollback_exc)
        try:
            promotion.rollback()
        except Exception as rollback_exc:
            rollback_failures.append(rollback_exc)
        if rollback_failures:
            raise _SubtitleRerenderRollbackError(
                "Subtitle re-render promotion rollback failed."
            ) from rollback_failures[0]
        raise exc


def _discard_subtitle_rerender_staging(
    *,
    db: Session,
    job_id: str,
    previous_export_ids: set[str],
    staging_paths: StoragePaths,
    remove_files: bool = True,
) -> None:
    current_exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)).all()
    for export in current_exports:
        if export.id not in previous_export_ids:
            db.delete(export)
    db.commit()
    if remove_files:
        shutil.rmtree(staging_paths.root, ignore_errors=True)


def _rollback_subtitle_rerender_publication(
    *,
    db: Session,
    promotion: _SubtitleRerenderPromotion | None,
    error: Exception,
) -> bool:
    rollback_succeeded = not isinstance(error, _SubtitleRerenderRollbackError)
    try:
        db.rollback()
    except Exception:
        rollback_succeeded = False
    if promotion is not None:
        try:
            promotion.rollback()
        except Exception:
            rollback_succeeded = False
    return rollback_succeeded


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


def _read_model_list(path: Path, model_type: type[Candidate]) -> list[Candidate]:
    if not path.is_file():
        return []
    payload = _read_json_file(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a list in {path.name}")
    return [model_type.model_validate(item) for item in payload]


def _top_level_metadata_files(job_dir: Path) -> list[Path]:
    metadata_files = [
        path
        for path in job_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".json", ".md"}
    ]
    quality_dir = job_dir / "quality_gate"
    if quality_dir.is_dir():
        metadata_files.extend(
            path
            for path in quality_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        )
    return sorted(metadata_files, key=lambda path: (path.parent.name, path.name))


def _render_exact_subtitle_review_preview_for_clip(
    *,
    dependencies: AutoClipperPipelineDependencies,
    input_path: Path,
    job_dir: Path,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_id: str,
) -> ExactPreviewResult:
    spec, expected_hash, inputs = current_subtitle_review_preview_spec(
        job=job,
        video=video,
        document=document,
        paths=paths,
        clip_id=clip_id,
    )
    result = dependencies.subtitle_review_exact_preview_renderer(
        input_path,
        job_dir,
        candidate=inputs.candidate,
        transcript_segments=inputs.transcript_segments,
        settings=inputs.settings,
        source_fingerprint=inputs.source_fingerprint,
        source_width=inputs.source_width,
        source_height=inputs.source_height,
        candidate_index=inputs.candidate_index,
        overlay_title_expected=inputs.overlay_title_expected,
        normal_renderer=dependencies.normal_renderer,
        short_renderer=dependencies.short_renderer,
    )
    if result.spec_hash != expected_hash:
        raise RuntimeError("subtitle review preview renderer returned a stale spec")
    expected_paths = exact_subtitle_review_preview_paths(
        job_dir,
        clip_id,
        expected_hash,
    )
    if (
        result.path != expected_paths.video_path
        or result.subtitle_path != expected_paths.subtitle_path
        or result.spec_path != expected_paths.spec_path
    ):
        raise RuntimeError("subtitle review preview renderer returned unexpected paths")
    if not exact_subtitle_review_preview_is_ready(expected_paths, expected_hash):
        raise RuntimeError("subtitle review preview renderer returned invalid artifacts")
    expected_live_spec = build_live_subtitle_review_preview_spec(spec)
    expected_live_hash = subtitle_review_preview_spec_hash(expected_live_spec)
    expected_live_paths = live_subtitle_review_preview_paths(
        job_dir,
        clip_id,
        expected_live_hash,
    )
    if (
        result.live_spec_hash != expected_live_hash
        or result.live_path != expected_live_paths.video_path
        or result.live_spec_path != expected_live_paths.spec_path
        or not live_subtitle_review_preview_is_ready(
            expected_live_paths,
            expected_live_hash,
        )
    ):
        raise RuntimeError("subtitle review live preview renderer returned invalid artifacts")
    return result


def _load_title_hook_evidence(
    job_dir: Path,
    document: SubtitleReviewDocument,
) -> dict[str, TitleHookSuggestionsDocument]:
    artifacts: dict[str, TitleHookSuggestionsDocument] = {}
    for clip in document.clips:
        path = title_hook_suggestions_path(job_dir, clip.id)
        if not path.is_file():
            continue
        try:
            artifact = load_title_hook_suggestions(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if artifact.state == "ready":
            artifacts[clip.id] = artifact
    return artifacts


def _prepare_auto_render_after_preview(
    *,
    db: Session,
    job: Job,
    video: Video,
    storage_paths: StoragePaths,
) -> int | None:
    job_dir = storage_paths.job_outputs(job.id)
    review_path = subtitle_review_output_path(job_dir)
    with subtitle_review_document_lock(job_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            return None
        document = load_subtitle_review(review_path)
        if document.state != "awaiting_review":
            return None
        document, _queued, changed = refresh_subtitle_review_preview_states(
            job=job,
            video=video,
            document=document,
            paths=storage_paths,
        )
        if changed:
            write_subtitle_review(document, review_path)
            write_subtitle_review_summary(
                document,
                subtitle_review_summary_path(job_dir),
            )

        settings = dict(job.settings_json or {})
        if _active_quality_gate_mode(job_dir, settings) != "auto":
            return None
        invalidate_quality_gate_decisions(job_dir, ("content", "post_render"))
        try:
            content_gate = evaluate_content_quality_gate(
                job_id=job.id,
                document=document,
                settings=settings,
                mode="auto",
                title_hook_evidence=_load_title_hook_evidence(job_dir, document),
            )
        except Exception as exc:
            content_gate = unknown_quality_gate_decision(
                job_id=job.id,
                stage="content",
                reason_code="content_gate_evaluation_failed",
                evidence={"errorType": exc.__class__.__name__},
                mode="auto",
            )
        content_gate_path = _try_write_quality_gate_decision(
            content_gate,
            quality_gate_decision_path(job_dir, "content"),
        )
        if content_gate_path is None or content_gate.route != "continue":
            return None

        document = queue_auto_review_render(document)
        write_subtitle_review(document, review_path)
        write_subtitle_review_summary(
            document,
            subtitle_review_summary_path(job_dir),
        )
        _set_status(db, job, "rendering_normal_clips")
        return document.render_revision


def _restore_auto_review_after_enqueue_failure(
    *,
    db: Session,
    job: Job,
    storage_paths: StoragePaths,
) -> None:
    job_dir = storage_paths.job_outputs(job.id)
    review_path = subtitle_review_output_path(job_dir)
    with subtitle_review_document_lock(job_dir):
        document = load_subtitle_review(review_path)
        if document.state == "render_queued":
            document = restore_review_after_render_failure(document)
            write_subtitle_review(document, review_path)
            write_subtitle_review_summary(
                document,
                subtitle_review_summary_path(job_dir),
            )
        db.refresh(job)
        _set_status(db, job, "awaiting_subtitle_review")


def _generate_auto_title_hook_evidence(
    *,
    dependencies: AutoClipperPipelineDependencies,
    document: SubtitleReviewDocument,
    input_path: Path,
    paths: StoragePaths,
    model: str,
    settings: Mapping[str, Any] | None = None,
) -> tuple[dict[str, TitleHookSuggestionsDocument], dict[str, str]]:
    artifacts: dict[str, TitleHookSuggestionsDocument] = {}
    failures: dict[str, str] = {}
    posting_settings = settings or {}
    for clip in document.clips:
        try:
            artifact = dependencies.auto_title_hook_generator(
                document=document,
                clip_id=clip.id,
                source_path=input_path,
                paths=paths,
                model=model,
            )
            apply_recommended_title_hook_suggestions(
                document,
                artifact,
                youtube_source_title=str(
                    posting_settings.get("youtubeSourceTitle") or ""
                ),
                youtube_source_url=str(
                    posting_settings.get("youtubeSourceUrl") or ""
                ),
                youtube_posting_profile=posting_settings.get("youtubePostingProfile"),
            )
            artifacts[clip.id] = artifact
        except Exception as exc:
            failures[clip.id] = exc.__class__.__name__
    refresh_review_overlay_title_expectations(
        document,
        render_mode=document.render_mode,
    )
    return artifacts, failures


def _mark_subtitle_review_preview_ready(
    document: SubtitleReviewDocument,
    *,
    clip_id: str,
    spec_hash: str,
    live_spec_hash: str,
) -> None:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    clip.preview_state = "ready"
    clip.preview_spec_hash = spec_hash
    clip.preview_video_url = exact_subtitle_review_preview_url(
        document.job_id,
        clip_id,
        spec_hash,
    )
    clip.live_preview_spec_hash = live_spec_hash
    clip.live_preview_video_url = live_subtitle_review_preview_url(
        document.job_id,
        clip_id,
        live_spec_hash,
    )
    clip.preview_error = None


def _resume_auto_after_clip_review(
    *,
    db: Session,
    job: Job,
    video: Video,
    settings: Mapping[str, Any],
    session_factory: SessionFactory,
    storage_paths: StoragePaths,
    dependencies: AutoClipperPipelineDependencies,
) -> list[str]:
    """Resume auto processing after the selection exception was accepted."""
    visited_statuses: list[str] = []
    job_dir = storage_paths.job_outputs(job.id)
    review_path = subtitle_review_output_path(job_dir)
    review_document = load_subtitle_review(review_path)
    if review_document.state == "completed":
        zip_path = storage_paths.zip_path(job.id)
        try:
            publication_completed = (
                job.status == "completed"
                and zip_path.is_file()
                and zip_path.stat().st_size > 0
            )
        except OSError:
            publication_completed = False
        if publication_completed:
            return ["completed"]
    if review_document.state in {"render_queued", "rendering", "completed"}:
        partial_exports = list(
            db.scalars(
                select(ExportItem).where(ExportItem.job_id == job.id)
            ).all()
        )
        _discard_unpublished_exports(
            db,
            partial_exports,
            job_dir=job_dir,
        )
        review_document = restore_review_after_render_failure(review_document)
        write_subtitle_review(review_document, review_path)
        write_subtitle_review_summary(
            review_document,
            subtitle_review_summary_path(job_dir),
        )
        _set_status(db, job, "awaiting_subtitle_review")
        return ["awaiting_subtitle_review"]
    if review_document.state != "awaiting_review":
        _set_status(db, job, "awaiting_subtitle_review")
        return ["awaiting_subtitle_review"]
    input_path = storage_paths.resolve_stored_file(video.stored_path)

    title_hook_evidence, _generation_failures = _generate_auto_title_hook_evidence(
        dependencies=dependencies,
        document=review_document,
        input_path=input_path,
        paths=storage_paths,
        model=str(settings.get("titleHookModel") or "codex-default"),
        settings=settings,
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
            result = _render_exact_subtitle_review_preview_for_clip(
                dependencies=dependencies,
                input_path=input_path,
                job_dir=job_dir,
                job=job,
                video=video,
                document=review_document,
                paths=storage_paths,
                clip_id=clip.id,
            )
        except Exception:
            # The content gate observes the missing current preview and returns
            # unknown. The review UI can retry only the unavailable preview.
            pass
        else:
            _mark_subtitle_review_preview_ready(
                review_document,
                clip_id=clip.id,
                spec_hash=result.spec_hash,
                live_spec_hash=result.live_spec_hash,
            )
        _set_subtitle_review_preview_progress(
            db,
            job,
            completed=preview_index,
            total=preview_total,
        )

    write_subtitle_review(review_document, review_path)
    write_subtitle_review_summary(
        review_document,
        subtitle_review_summary_path(job_dir),
    )
    invalidate_quality_gate_decisions(job_dir, ("content", "post_render"))
    try:
        content_gate = evaluate_content_quality_gate(
            job_id=job.id,
            document=review_document,
            settings=settings,
            mode="auto",
            title_hook_evidence=title_hook_evidence,
        )
    except Exception as exc:
        content_gate = unknown_quality_gate_decision(
            job_id=job.id,
            stage="content",
            reason_code="content_gate_evaluation_failed",
            evidence={"errorType": exc.__class__.__name__},
            mode="auto",
        )
    content_gate_path = _try_write_quality_gate_decision(
        content_gate,
        quality_gate_decision_path(job_dir, "content"),
    )
    if content_gate_path is None or content_gate.route != "continue":
        _set_status(db, job, "awaiting_subtitle_review")
        visited_statuses.append("awaiting_subtitle_review")
        return visited_statuses

    review_document = queue_auto_review_render(review_document)
    write_subtitle_review(review_document, review_path)
    write_subtitle_review_summary(
        review_document,
        subtitle_review_summary_path(job_dir),
    )
    db.commit()
    render_statuses = run_subtitle_review_render(
        job.id,
        render_revision=review_document.render_revision,
        session_factory=session_factory,
        paths=storage_paths,
        dependencies=dependencies,
    )
    return [*visited_statuses, *render_statuses]


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
    heatmap_segments: list[HeatmapSegment] = []
    normal_candidates: list[Candidate] = []
    short_candidates: list[Candidate] = []
    candidate_generation_summary: dict[str, Any] | None = None
    scored_candidates: list[Candidate] = []
    selection: CandidateSelection | None = None
    codex_initial_selection_result: Any | None = None
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

        settings = duration_search_settings(dict(job.settings_json or {}))
        automation_mode = str(settings.get("automationMode") or "manual").strip()
        manual_workflow = is_manual_workflow(settings)
        active_manual_subtitle_mode = manual_subtitle_mode(settings)
        skip_automatic_transcription = manual_workflow and active_manual_subtitle_mode in {"none", "manual"}
        skip_automatic_audio_analysis = skip_automatic_transcription
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

        resume_after_clip_review = bool(
            settings.get(AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING, False)
        )
        if resume_after_clip_review:
            consume_resume_marker = True
            resume_settings = dict(settings)
            resume_settings.pop(AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING, None)
            if automation_mode != "auto":
                _set_status(db, job, "awaiting_subtitle_review")
                resume_statuses = ["awaiting_subtitle_review"]
            else:
                try:
                    resume_statuses = _resume_auto_after_clip_review(
                        db=db,
                        job=job,
                        video=video,
                        settings=resume_settings,
                        session_factory=session_factory,
                        storage_paths=storage_paths,
                        dependencies=deps,
                    )
                except Exception as exc:
                    try:
                        failed_review = load_subtitle_review(
                            subtitle_review_output_path(job_dir)
                        )
                        if failed_review.state in {
                            "render_queued",
                            "rendering",
                            "completed",
                        }:
                            partial_exports = list(
                                db.scalars(
                                    select(ExportItem).where(ExportItem.job_id == job.id)
                                ).all()
                            )
                            _discard_unpublished_exports(
                                db,
                                partial_exports,
                                job_dir=job_dir,
                            )
                            failed_review = restore_review_after_render_failure(
                                failed_review
                            )
                            write_subtitle_review(
                                failed_review,
                                subtitle_review_output_path(job_dir),
                            )
                            write_subtitle_review_summary(
                                failed_review,
                                subtitle_review_summary_path(job_dir),
                            )
                    except Exception:
                        # Preserve the durable marker so a retry can recover a
                        # review left in render_queued/rendering.
                        consume_resume_marker = False
                    resume_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="content",
                        reason_code="auto_resume_after_clip_review_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode="auto",
                    )
                    _try_write_quality_gate_decision(
                        resume_gate,
                        quality_gate_decision_path(job_dir, "content"),
                    )
                    _set_status(db, job, "awaiting_subtitle_review")
                    resume_statuses = ["awaiting_subtitle_review"]
            db.refresh(job)
            persisted_settings = dict(job.settings_json or {})
            if consume_resume_marker:
                persisted_settings.pop(AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING, None)
            job.settings_json = persisted_settings
            db.commit()
            shutil.rmtree(temp_dir, ignore_errors=True)
            return resume_statuses

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
            automation_manifest = build_automation_manifest(
                job_id=job.id,
                video_id=video.id,
                stored_path=video.stored_path,
                settings=settings,
            )
            automation_mode = automation_manifest.effective_mode
            metadata_files.append(
                write_automation_manifest(
                    automation_manifest,
                    automation_manifest_path(job_dir),
                )
            )
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
            if manual_workflow and not manual_edit_is_finalized(settings):
                job.current_step = "手動編集用の動画を準備中"
                _heartbeat_job(db, job)
                proxy_path = manual_source_proxy_path(job_dir)
                try:
                    proxy_path = deps.manual_source_proxy_renderer(
                        input_path,
                        proxy_path,
                        duration=duration,
                        has_audio=metadata.has_audio,
                    )
                except Exception as exc:
                    raise PipelineExpectedError(
                        "manual_source_proxy_failed",
                        f"Could not create the manual editor video: {exc}",
                    ) from exc
                metadata_files.append(proxy_path)
                document = build_clip_plan(
                    job.id,
                    CandidateSelection(),
                    settings,
                    source_duration=duration,
                    editor_video_url=manual_source_proxy_url(job.id),
                )
                document.state = "manual_editing"
                metadata_files.append(write_clip_plan(document, clip_plan_output_path(job_dir)))
                _set_status(db, job, "awaiting_manual_edit")
                visited_statuses.append("awaiting_manual_edit")
                return visited_statuses

            if not manual_workflow:
                heatmap_result = load_heatmap_for_video(
                    input_path,
                    original_filename=video.original_filename,
                    actual_duration=duration,
                    max_sidecar_size_bytes=get_settings().max_heatmap_sidecar_size_bytes,
                    sidecar_path=storage_paths.resolve_video_heatmap(
                        video.id,
                        video.stored_path,
                    ),
                )
                heatmap_segments = heatmap_result.segments
                heatmap_summary, _ = _heatmap_summary_for_selection_mode(
                    heatmap_result.summary,
                    heatmap_segments,
                    settings,
                    video_duration=duration,
                )
                metadata_files.append(
                    _write_json(
                        job_dir / "heatmap_validation_summary.json",
                        heatmap_summary,
                    )
                )
            if not skip_automatic_audio_analysis and not metadata.has_audio:
                raise PipelineExpectedError(
                    "missing_audio",
                    "Video has no audio track. AutoClipper needs audio for transcription.",
                )
            if not skip_automatic_audio_analysis:
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

            if skip_automatic_audio_analysis:
                silence_segments = []
                metadata_files.append(
                    write_silence_segments(
                        silence_segments,
                        silence_output_path(job_dir),
                    )
                )
                audio_features = build_audio_features(duration, [], 0.0)
                metadata_files.append(
                    write_audio_features(
                        audio_features,
                        audio_features_output_path(job_dir),
                    )
                )
                transcript_segments = []
                metadata_files.append(
                    write_transcript_segments(
                        transcript_segments,
                        transcript_output_path(job_dir),
                    )
                )
                transcription_engine = f"manual_{active_manual_subtitle_mode}"
                transcription_model = None
                transcription_language = None
                transcription_diagnostics = None
            else:
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
                            transcript_segments, transcription_diagnostics = _transcribe_with_faster_whisper(
                                deps.transcription_engine_factory,
                                audio_path,
                                model=configured_transcription_model,
                                language=configured_transcription_language,
                                device=configured_transcription_device,
                                compute_type=configured_transcription_compute_type,
                            )
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

                    quality_context = {
                        "timeline_duration": duration,
                        "expected_speech_seconds": audio_features.speech_seconds,
                    }
                    primary_quality = _transcript_quality_diagnostics(
                        transcript_segments,
                        **quality_context,
                    )
                    active_quality = primary_quality
                    primary_transcript_path: Path | None = None
                    chunk_progress_label = "長尺音声を分割して文字起こしを再試行中"

                    def transcription_chunk_progress(completed: int, total: int) -> None:
                        job.current_step = f"{chunk_progress_label} ({completed}/{total})"
                        _heartbeat_job(db, job)

                    if (
                        transcribe_audio is None
                        and transcription_diagnostics is not None
                        and _should_retry_long_form_transcription_in_chunks(
                            duration=duration,
                            diagnostics=transcription_diagnostics,
                            reasons=primary_quality["reasons"],
                        )
                    ):
                        primary_transcript_path = write_transcript_segments(
                            transcript_segments,
                            job_dir / "primary_raw_transcript_segments.json",
                        )
                        metadata_files.append(primary_transcript_path)
                        job.current_step = chunk_progress_label
                        _heartbeat_job(db, job)
                        primary_diagnostics = dict(transcription_diagnostics)
                        try:
                            chunked_segments, chunked_diagnostics = _transcribe_with_faster_whisper_in_chunks(
                                deps.transcription_engine_factory,
                                audio_path,
                                model=configured_transcription_model,
                                language=configured_transcription_language,
                                device=configured_transcription_device,
                                compute_type=configured_transcription_compute_type,
                                progress_callback=transcription_chunk_progress,
                            )
                        except Exception as exc:
                            transcription_diagnostics = {
                                **primary_diagnostics,
                                "chunked_quality_fallback_used": False,
                                "chunked_quality_fallback_error_type": type(exc).__name__,
                                "primary_transcript_quality": primary_quality,
                            }
                        else:
                            chunked_quality = _transcript_quality_diagnostics(
                                chunked_segments,
                                **quality_context,
                            )
                            transcript_segments = chunked_segments
                            active_quality = chunked_quality
                            transcription_diagnostics = _chunked_transcription_diagnostics(
                                primary=primary_diagnostics,
                                primary_quality=primary_quality,
                                chunked=chunked_diagnostics,
                                chunked_quality=chunked_quality,
                            )

                    if (
                        transcribe_audio is None
                        and transcription_diagnostics is not None
                        and _should_retry_transcription_with_small(
                            model=configured_transcription_model,
                            language=configured_transcription_language,
                            diagnostics=transcription_diagnostics,
                            reasons=active_quality["reasons"],
                        )
                    ):
                        if primary_transcript_path is None:
                            primary_transcript_path = write_transcript_segments(
                                transcript_segments,
                                job_dir / "primary_raw_transcript_segments.json",
                            )
                            metadata_files.append(primary_transcript_path)
                        elif transcription_diagnostics.get("chunked_quality_fallback_used"):
                            chunked_transcript_path = write_transcript_segments(
                                transcript_segments,
                                job_dir / "chunked_raw_transcript_segments.json",
                            )
                            metadata_files.append(chunked_transcript_path)
                        job.current_step = "文字起こし品質が低いため small + ja で再試行中"
                        _heartbeat_job(db, job)
                        primary_diagnostics = dict(transcription_diagnostics)
                        fallback_is_chunked = duration >= LONG_FORM_TRANSCRIPTION_SECONDS
                        try:
                            if fallback_is_chunked:
                                chunk_progress_label = "small + ja で分割文字起こしを再試行中"
                                fallback_segments, fallback_diagnostics = _transcribe_with_faster_whisper_in_chunks(
                                    deps.transcription_engine_factory,
                                    audio_path,
                                    model="small",
                                    language="ja",
                                    device=configured_transcription_device,
                                    compute_type=configured_transcription_compute_type,
                                    progress_callback=transcription_chunk_progress,
                                )
                            else:
                                fallback_segments, fallback_diagnostics = _transcribe_with_faster_whisper(
                                    deps.transcription_engine_factory,
                                    audio_path,
                                    model="small",
                                    language="ja",
                                    device=configured_transcription_device,
                                    compute_type=configured_transcription_compute_type,
                                )
                        except TranscriptionRuntimeError as exc:
                            recovery_summary_path = _write_transcription_recovery_failure_summary(
                                job_dir,
                                prior=primary_diagnostics,
                                prior_quality=active_quality,
                                fallback_chunked=fallback_is_chunked,
                                exc=exc,
                            )
                            metadata_files.append(recovery_summary_path)
                            raise PipelineExpectedError(
                                "transcription_quality_fallback_failed",
                                "高精度モデルによる文字起こしの再試行に失敗しました。",
                                details={
                                    "primary_transcript_quality": active_quality,
                                    "fallback_error_code": exc.code,
                                    "recovery_summary_file": recovery_summary_path.name,
                                    **exc.details,
                                },
                            ) from exc
                        except Exception as exc:
                            recovery_summary_path = _write_transcription_recovery_failure_summary(
                                job_dir,
                                prior=primary_diagnostics,
                                prior_quality=active_quality,
                                fallback_chunked=fallback_is_chunked,
                                exc=exc,
                            )
                            metadata_files.append(recovery_summary_path)
                            raise PipelineExpectedError(
                                "transcription_quality_fallback_failed",
                                "高精度モデルによる文字起こしの再試行に失敗しました。",
                                details={
                                    "primary_transcript_quality": active_quality,
                                    "fallback_error_type": type(exc).__name__,
                                    "recovery_summary_file": recovery_summary_path.name,
                                },
                            ) from exc

                        fallback_quality = _transcript_quality_diagnostics(
                            fallback_segments,
                            **quality_context,
                        )
                        transcript_segments = fallback_segments
                        transcription_model = "small"
                        transcription_language = "ja"
                        transcription_diagnostics = _fallback_transcription_diagnostics(
                            primary=primary_diagnostics,
                            primary_quality=active_quality,
                            fallback=fallback_diagnostics,
                            fallback_quality=fallback_quality,
                        )
                    if transcription_diagnostics is not None and (
                        transcription_diagnostics.get("quality_fallback_used")
                        or "chunked_quality_fallback_used" in transcription_diagnostics
                    ):
                        recovery_summary_path = _write_json(
                            job_dir / TRANSCRIPTION_RECOVERY_SUMMARY_FILENAME,
                            {
                                "selected_model": transcription_model,
                                "selected_language": transcription_language,
                                "selected_quality": _transcript_quality_diagnostics(
                                    transcript_segments,
                                    **quality_context,
                                ),
                                "runtime": transcription_diagnostics,
                            },
                        )
                        metadata_files.append(recovery_summary_path)
                raw_transcript_path = write_transcript_segments(transcript_segments, raw_transcript_output_path(job_dir))
                metadata_files.append(raw_transcript_path)
                postprocess_result = postprocess_transcript_segments(transcript_segments, settings)
                transcript_segments = postprocess_result.segments
                postprocess_summary_path = write_transcript_postprocess_summary(
                    postprocess_result.summary,
                    transcript_postprocess_summary_path(job_dir),
                )
                metadata_files.append(postprocess_summary_path)
                metadata_files.append(write_transcript_segments(
                    transcript_segments, deterministic_transcript_output_path(job_dir),
                ))
                transcript_segments = finalize_transcript_width(transcript_segments, settings)
                transcript_path = write_transcript_segments(transcript_segments, transcript_output_path(job_dir))
                metadata_files.append(transcript_path)
                _raise_if_transcript_unusable(
                    transcript_segments,
                    timeline_duration=duration,
                    expected_speech_seconds=audio_features.speech_seconds,
                )

            if manual_workflow:
                scene_segments = []
                metadata_files.append(write_scene_segments(scene_segments, scene_output_path(job_dir)))
                visual_quality = build_visual_quality(duration, [])
                metadata_files.append(
                    write_visual_quality(
                        visual_quality,
                        visual_quality_output_path(job_dir),
                    )
                )
            else:
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
            settings = _settings_with_source_history(db, job, video, storage_paths)
            metadata_files.append(job_dir / "source_clip_history_summary.json")
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
            heatmap_interval_mode = _bool_setting(settings, "heatmapIntervalMode", False)
            heatmap_reference_segments = (
                heatmap_segments if heatmap_interval_mode else ()
            )
            codex_summary_path = codex_initial_selection_summary_output_path(job_dir)
            codex_requested = _codex_initial_selection_enabled(
                settings,
                manual_workflow=manual_workflow,
                has_manual_ranges=bool(normal_manual_ranges or short_manual_ranges),
            )
            if codex_requested:
                job.current_step = "Codexで初期選定中"
                _heartbeat_job(db, job)

                def codex_selection_heartbeat(summary: dict[str, Any]) -> None:
                    write_codex_initial_selection_summary(summary, codex_summary_path)
                    job.current_step = "Codexで初期選定中"
                    _heartbeat_job(db, job)

                try:
                    codex_initial_selection_result = deps.codex_initial_selector(
                        job_id=job.id,
                        storage_root=storage_paths.root,
                        transcript_segments=transcript_segments,
                        heatmap_segments=heatmap_reference_segments,
                        video_duration=duration,
                        settings=settings,
                        heartbeat=codex_selection_heartbeat,
                    )
                    metadata_files.append(
                        write_codex_initial_selection_summary(
                            codex_initial_selection_result.summary,
                            codex_summary_path,
                        )
                    )
                except CodexInitialSelectionError as exc:
                    metadata_files.append(
                        write_codex_initial_selection_summary(
                            exc.fallback_summary(
                                requested_normal_count=_int_setting(settings, "normalClipCount", 2),
                                requested_short_count=_int_setting(settings, "shortCount", 3),
                            ),
                            codex_summary_path,
                        )
                    )
                except Exception:
                    metadata_files.append(
                        write_codex_initial_selection_summary(
                            {
                                "provider": "codex",
                                "status": "fallback",
                                "fallbackUsed": True,
                                "error": {
                                    "code": "codex_initial_selection_unexpected_error",
                                    "message": "Codex初期選定を完了できなかったため、従来選定へ切り替えました。",
                                },
                                "requestedNormalCount": _int_setting(settings, "normalClipCount", 2),
                                "requestedShortCount": _int_setting(settings, "shortCount", 3),
                                "selectedNormalCount": 0,
                                "selectedShortCount": 0,
                                "threadId": None,
                            },
                            codex_summary_path,
                        )
                    )
            codex_normal_candidates = (
                [candidate for candidate in codex_initial_selection_result.candidates if candidate.type == "normal"]
                if codex_initial_selection_result is not None
                else []
            )
            codex_short_candidates = (
                [candidate for candidate in codex_initial_selection_result.candidates if candidate.type == "short"]
                if codex_initial_selection_result is not None
                else []
            )
            try:
                normal_generation_result = (
                    CandidateGenerationResult(
                        candidates=codex_normal_candidates,
                        summary={
                            "type": "normal",
                            "strategy": "codex_content_selection",
                            "raw_candidates_considered": len(codex_normal_candidates),
                            "candidates_kept_by_type": {"normal": len(codex_normal_candidates)},
                        },
                    )
                    if codex_initial_selection_result is not None
                    else build_manual_candidates(
                        "normal",
                        normal_manual_ranges,
                        transcript_segments,
                    )
                    if manual_workflow or (is_ai_allocation(settings) and not any(candidate_pool_counts(settings)))
                    or (normal_manual_ranges and not is_ai_allocation(settings))
                    else generate_normal_candidates_with_summary(
                        unused_items(transcript_segments, settings),
                        scene_segments,
                        silence_segments,
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                )
                normal_candidates = (
                    list(normal_generation_result.candidates)
                    if manual_workflow
                    else annotate_candidates_with_heatmap(
                        normal_generation_result.candidates,
                        heatmap_reference_segments,
                    )
                )
                short_generation_result = (
                    CandidateGenerationResult(
                        candidates=codex_short_candidates,
                        summary={
                            "type": "short",
                            "strategy": "codex_content_selection",
                            "raw_candidates_considered": len(codex_short_candidates),
                            "candidates_kept_by_type": {"short": len(codex_short_candidates)},
                        },
                    )
                    if codex_initial_selection_result is not None
                    else build_manual_candidates(
                        "short",
                        short_manual_ranges,
                        transcript_segments,
                    )
                    if manual_workflow or (is_ai_allocation(settings) and not any(candidate_pool_counts(settings)))
                    or (short_manual_ranges and not is_ai_allocation(settings))
                    else generate_short_candidates_with_summary(
                        unused_items(transcript_segments, settings),
                        scene_segments,
                        silence_segments,
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                )
                short_candidates = (
                    list(short_generation_result.candidates)
                    if manual_workflow
                    else annotate_candidates_with_heatmap(
                        short_generation_result.candidates,
                        heatmap_reference_segments,
                    )
                )
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
            if is_ai_allocation(settings) and not manual_workflow:
                normal_candidates = list({c.id: c for c in [*normal_candidates,
                    *annotate_candidates_with_heatmap(
                        build_manual_candidates('normal', normal_manual_ranges, transcript_segments).candidates,
                                                     heatmap_reference_segments)]}.values())
                short_candidates = list({c.id: c for c in [*short_candidates,
                    *annotate_candidates_with_heatmap(build_manual_candidates('short', short_manual_ranges, transcript_segments).candidates,
                                                     heatmap_reference_segments)]}.values())
            if manual_workflow:
                normal_candidates = apply_manual_clip_metadata(
                    normal_candidates,
                    settings,
                )
                short_candidates = apply_manual_clip_metadata(
                    short_candidates,
                    settings,
                )
            normal_candidates = _unused_candidates(normal_candidates, settings)
            short_candidates = _unused_candidates(short_candidates, settings)
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
                    "source_history_no_unused_candidates" if used_ranges(settings) else "no_candidates_found",
                    "使用済み区間の除外後、新しい候補が見つかりませんでした。"
                    if used_ranges(settings) else "No clip candidates were found for the selected settings.",
                )

            manual_candidates = [c for c in [*normal_candidates, *short_candidates] if c.selection_reason == MANUAL_SELECTION_REASON]
            automatic_candidates = [c for c in [*normal_candidates, *short_candidates] if c.selection_reason != MANUAL_SELECTION_REASON]
            if manual_workflow:
                scored_candidates = list(manual_candidates)
                selection = build_manual_selection(
                    normal_candidates,
                    short_candidates,
                )
            elif codex_initial_selection_result is not None:
                _set_status(db, job, "selecting_clips")
                if "selecting_clips" not in visited_statuses:
                    visited_statuses.append("selecting_clips")
                selection, scored_candidates, _ = _codex_selection_with_diverse_refined_shorts(
                    codex_initial_selection_result,
                    transcript_segments=transcript_segments,
                    silence_segments=silence_segments,
                    scene_segments=scene_segments,
                    settings=settings,
                    timeline_duration=duration,
                    heatmap_segments=heatmap_reference_segments,
                )
                final_codex_summary = {
                    **codex_initial_selection_result.summary,
                    "selectedNormalCount": len(selection.normal_clips),
                    "selectedShortCount": len(selection.shorts),
                }
                write_codex_initial_selection_summary(
                    final_codex_summary,
                    codex_summary_path,
                )
            else:
                _set_status(db, job, "scoring_candidates")
                visited_statuses.append("scoring_candidates")
                automatic_scored = _score_local_candidates(
                    automatic_candidates, settings=automatic_settings,
                    audio_features=audio_features, silence_segments=silence_segments,
                )
                scored_candidates = [*automatic_scored, *manual_candidates]

                _set_status(db, job, "selecting_clips")
                visited_statuses.append("selecting_clips")
                automatic_selection = select_candidates(
                    automatic_scored,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    silence_segments=silence_segments,
                )
                automatic_selection, automatic_scored, _ = (
                    _automatic_selection_with_diverse_refined_shorts(
                        automatic_scored,
                        transcript_segments=transcript_segments,
                        silence_segments=silence_segments,
                        scene_segments=scene_segments,
                        settings=automatic_settings,
                        timeline_duration=duration,
                        audio_features=audio_features,
                        heatmap_segments=heatmap_reference_segments,
                    )
                )
                scored_candidates = [*automatic_scored, *manual_candidates]
                selection = merge_manual_candidates_into_selection(
                    automatic_selection,
                    settings=settings,
                    manual_normal_candidates=[c for c in manual_candidates if c.type == "normal"],
                    manual_short_candidates=[c for c in manual_candidates if c.type == "short"],
                )
            if is_ai_allocation(settings):
                if codex_initial_selection_result is not None:
                    selection = merge_manual_candidates_into_selection(selection, settings=settings,
                        manual_normal_candidates=[c for c in manual_candidates if c.type == 'normal'],
                        manual_short_candidates=[c for c in manual_candidates if c.type == 'short'])
                    scored_candidates = [*scored_candidates, *manual_candidates]
                selection, scored_candidates = _filter_user_rejections(selection, scored_candidates, settings)
                selection = allocate_selection(selection, settings)
                scored_by_id = {c.id: c for c in [*scored_candidates, *manual_candidates]}
                scored_candidates = list(scored_by_id.values())
                if codex_initial_selection_result is not None:
                    write_codex_initial_selection_summary({
                        **codex_initial_selection_result.summary, **allocation_summary(selection),
                        'selectedNormalCount': len(selection.normal_clips), 'selectedShortCount': len(selection.shorts),
                    }, codex_summary_path)
            selection, scored_candidates = _selection_with_fallback_titles(
                selection,
                scored_candidates,
                transcript_segments,
            )
            if manual_workflow and active_manual_subtitle_mode == "manual":
                transcript_segments = build_manual_subtitle_segments(selection)
                transcript_path = write_transcript_segments(
                    transcript_segments,
                    transcript_output_path(job_dir),
                )
                if transcript_path not in metadata_files:
                    metadata_files.append(transcript_path)
            metadata_files.append(write_candidates(scored_candidates, job_dir / "scored_candidates.json"))
            selected_path = write_selected_clips(selection, job_dir / "selected_clips.json")
            metadata_files.append(selected_path)

            if not selection.normal_clips and not selection.shorts:
                raise PipelineExpectedError(
                    "no_usable_selection",
                    "Pipeline completed analysis but selection produced no usable clips.",
                )

            selection_gate = None
            if automation_mode in {"shadow", "guarded", "auto"}:
                selection_gate, selection_gate_path = (
                    _evaluate_selection_quality_gate_for_mode(
                        job_id=job.id,
                        job_dir=job_dir,
                        selection=selection,
                        transcript_segments=transcript_segments,
                        settings=settings,
                        source_duration=duration,
                        mode=automation_mode,
                    )
                )
                if selection_gate_path is not None:
                    metadata_files.append(selection_gate_path)

            if manual_workflow:
                manual_plan_path = clip_plan_output_path(job_dir)
                manual_document = (
                    load_clip_plan(manual_plan_path)
                    if manual_plan_path.is_file()
                    else build_clip_plan(
                        job.id,
                        selection,
                        settings,
                        source_duration=duration,
                    )
                )
                manual_document.settings = settings
                write_clip_plan(
                    mark_clip_plan_approved(manual_document),
                    manual_plan_path,
                )

            guarded_selection_needs_review = bool(
                automation_mode in {"guarded", "auto"}
                and selection_gate is not None
                and selection_gate.route != "continue"
            )
            manual_clip_plan_review = bool(
                automation_mode not in {"guarded", "auto"}
                and bool(settings.get("requireClipPlanReview", False))
                and bool(settings.get("requireSubtitleReview", False))
                and bool(settings.get("burnSubtitles", True))
            )
            allocation_needs_review = bool(
                is_ai_allocation(settings) and selection.shortfall_reasons and not manual_workflow
            )
            if guarded_selection_needs_review or manual_clip_plan_review or allocation_needs_review:
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
                metadata_files.extend(path for path in summary_files if path not in metadata_files)
                visited_statuses.extend(["preparing_clip_review", "awaiting_clip_review"])
                return visited_statuses

            subtitle_review_requested = bool(settings.get("requireSubtitleReview", False)) and (
                bool(settings.get("burnSubtitles", True)) or (manual_workflow and active_manual_subtitle_mode in {"none", "manual"})
            )
            content_gate: QualityGateDecision | None = None
            guarded_content_auto_passed = False
            title_hook_evidence: dict[str, TitleHookSuggestionsDocument] = {}
            if subtitle_review_requested:
                review_document = build_subtitle_review(
                    job.id,
                    selection,
                    transcript_segments,
                    short_max_duration=float(settings.get("shortMaxDuration", 75.0)),
                    render_mode=str(settings.get("mode", "high_quality")),
                    short_overlay_title_mode=settings.get(
                        "shortOverlayTitleMode",
                        "auto",
                    ),
                    short_layout=settings.get("shortLayout", "auto"),
                    short_top_banner_enabled=bool(settings.get("shortTopBannerEnabled", False)),
                    short_bottom_banner_enabled=bool(settings.get("shortBottomBannerEnabled", False)),
                    render_settings=settings,
                    source_width=video.width,
                    source_height=video.height,
                )
                if automation_mode == "auto":
                    title_hook_evidence, _title_hook_failures = (
                        _generate_auto_title_hook_evidence(
                            dependencies=deps,
                            document=review_document,
                            input_path=input_path,
                            paths=storage_paths,
                            model=str(
                                settings.get("titleHookModel") or "codex-default"
                            ),
                            settings=settings,
                        )
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
                        result = _render_exact_subtitle_review_preview_for_clip(
                            dependencies=deps,
                            input_path=input_path,
                            job_dir=job_dir,
                            job=job,
                            video=video,
                            document=review_document,
                            paths=storage_paths,
                            clip_id=clip.id,
                        )
                    except Exception as exc:
                        raise PipelineExpectedError(
                            "subtitle_review_preview_failed",
                            f"Could not prepare subtitle review video for clip {preview_index}/{preview_total}: {exc}",
                        ) from exc
                    _mark_subtitle_review_preview_ready(
                        review_document,
                        clip_id=clip.id,
                        spec_hash=result.spec_hash,
                        live_spec_hash=result.live_spec_hash,
                    )
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

                if automation_mode in {"shadow", "guarded", "auto"}:
                    invalidate_quality_gate_decisions(
                        job_dir,
                        ("content", "post_render"),
                    )
                    try:
                        content_gate = evaluate_content_quality_gate(
                            job_id=job.id,
                            document=review_document,
                            settings=settings,
                            mode=automation_mode,
                            title_hook_evidence=title_hook_evidence,
                        )
                    except Exception as exc:
                        content_gate = unknown_quality_gate_decision(
                            job_id=job.id,
                            stage="content",
                            reason_code="content_gate_evaluation_failed",
                            evidence={"errorType": exc.__class__.__name__},
                            mode=automation_mode,
                        )
                    content_gate_path = _try_write_quality_gate_decision(
                        content_gate,
                        quality_gate_decision_path(job_dir, "content"),
                    )
                    if content_gate_path is not None:
                        metadata_files.append(content_gate_path)
                    elif automation_mode in {"guarded", "auto"}:
                        content_gate = unknown_quality_gate_decision(
                            job_id=job.id,
                            stage="content",
                            reason_code="content_gate_record_unavailable",
                            mode=automation_mode,
                        )

                summary_files = write_summaries()
                metadata_files.extend(path for path in summary_files if path not in metadata_files)
                guarded_content_auto_passed = bool(
                    automation_mode in {"guarded", "auto"}
                    and content_gate is not None
                    and content_gate.route == "continue"
                )
                if subtitle_review_requested and not guarded_content_auto_passed:
                    _set_status(db, job, "awaiting_subtitle_review")
                    visited_statuses.append("awaiting_subtitle_review")
                    return visited_statuses

                if guarded_content_auto_passed:
                    transcript_segments = apply_reviewed_text(
                        transcript_segments,
                        review_document,
                    )
                    selection = apply_reviewed_clip_content(
                        selection,
                        review_document,
                    )
                    write_transcript_segments(
                        transcript_segments,
                        transcript_output_path(job_dir),
                    )
                    write_selected_clips(
                        selection,
                        job_dir / "selected_clips.json",
                    )

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
            if automation_mode in {"shadow", "guarded", "auto"}:
                invalidate_quality_gate_decisions(job_dir, ("post_render",))
                try:
                    post_render_gate = evaluate_post_render_quality_gate(
                        job_id=job.id,
                        expected_export_count=(
                            len(selection.normal_clips) + len(selection.shorts)
                        ),
                        exports=exports,
                        render_failures=[
                            *normal_result.failures,
                            *short_result.failures,
                        ],
                        mode=automation_mode,
                        document=review_document,
                    )
                except Exception as exc:
                    post_render_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="post_render",
                        reason_code="post_render_gate_evaluation_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode=automation_mode,
                    )
                post_render_gate_path = _try_write_quality_gate_decision(
                    post_render_gate,
                    quality_gate_decision_path(job_dir, "post_render"),
                )
                if post_render_gate_path is not None:
                    metadata_files.append(post_render_gate_path)
                elif automation_mode in {"guarded", "auto"}:
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    if automation_mode == "auto":
                        _set_status(db, job, "awaiting_subtitle_review")
                        visited_statuses.append("awaiting_subtitle_review")
                        return visited_statuses
                    raise PipelineExpectedError(
                        "quality_gate_record_failed",
                        "Guarded post-render quality decision could not be recorded.",
                    )
                if (
                    automation_mode in {"guarded", "auto"}
                    and post_render_gate.route != "continue"
                ):
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    if automation_mode == "auto":
                        _set_status(db, job, "awaiting_subtitle_review")
                        visited_statuses.append("awaiting_subtitle_review")
                        return visited_statuses
                    raise PipelineExpectedError(
                        "quality_gate_render_failed",
                        "Guarded quality gate rejected incomplete rendered output.",
                        details={
                            "qualityGateStage": "post_render",
                            "qualityGateOutcome": post_render_gate.outcome,
                            "qualityGateInputHash": post_render_gate.input_hash,
                        },
                    )
            generate_export_thumbnails(
                exports=exports,
                selection=selection,
                input_path=input_path,
                job_output_dir=storage_paths.job_outputs(job.id),
                normal_renderer=deps.normal_thumbnail_renderer,
                short_renderer=deps.short_thumbnail_renderer,
                character_style=settings.get("normalThumbnailStyle"),
                db=db, job=job, paths=storage_paths,
            )
            if guarded_content_auto_passed:
                review_document = mark_review_completed(review_document)
                write_subtitle_review(
                    review_document,
                    subtitle_review_output_path(job_dir),
                )
                write_subtitle_review_summary(
                    review_document,
                    subtitle_review_summary_path(job_dir),
                )
                posting_files = _write_youtube_posting_artifacts_for_publication(
                    review_document.clips,
                    exports,
                    job_dir=job_dir,
                )
                metadata_files.extend(
                    path for path in posting_files if path not in metadata_files
                )
                invalidate_quality_gate_decisions(job_dir, ("content",))
                try:
                    content_gate = evaluate_content_quality_gate(
                        job_id=job.id,
                        document=review_document,
                        settings=settings,
                        mode=automation_mode,
                        title_hook_evidence=title_hook_evidence,
                    )
                except Exception as exc:
                    content_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="content",
                        reason_code="content_gate_evaluation_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode=automation_mode,
                    )
                content_gate_path = _try_write_quality_gate_decision(
                    content_gate,
                    quality_gate_decision_path(job_dir, "content"),
                )
                if content_gate_path is None or content_gate.route != "continue":
                    invalidate_quality_gate_decisions(job_dir, ("post_render",))
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    raise PipelineExpectedError(
                        (
                            "quality_gate_record_failed"
                            if content_gate_path is None
                            else "quality_gate_render_failed"
                        ),
                        "Guarded content decision changed before packaging.",
                        details={
                            "qualityGateStage": "content",
                            "qualityGateOutcome": content_gate.outcome,
                            "qualityGateInputHash": content_gate.input_hash,
                        },
                    )
            summary_files = write_summaries()
            metadata_files.extend(path for path in summary_files if path not in metadata_files)
            if not exports:
                raise PipelineExpectedError(
                    "no_usable_output",
                    "Selected clips did not produce usable rendered output.",
                )

            _set_status(db, job, "packaging_zip")
            visited_statuses.append("packaging_zip")
            _create_zip(storage_paths.zip_path(job.id), exports, metadata_files=metadata_files)

            _set_status(db, job, "completed")
            visited_statuses.append("completed")
            prune_job_previews_after_completion(db, job, storage_paths)
            enqueue_completed_job_harvest(db, job, storage_paths)
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


def run_subtitle_review_preview(
    job_id: str,
    clip_id: str,
    spec_hash: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        if job.status == "completed":
            return ["completed"]
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")
        job_dir = storage_paths.job_outputs(job.id)
        review_path = subtitle_review_output_path(job_dir)
        document = load_subtitle_review(review_path)
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise ValueError(f"subtitle review clip not found: {clip_id}")
        if clip.preview_spec_hash != spec_hash:
            return ["superseded"]

        current_spec, current_hash, _inputs = current_subtitle_review_preview_spec(
            job=job,
            video=video,
            document=document,
            paths=storage_paths,
            clip_id=clip_id,
        )
        if current_hash != spec_hash:
            return ["superseded"]

        artifacts = exact_subtitle_review_preview_paths(
            job_dir,
            clip_id,
            spec_hash,
        )
        live_spec = build_live_subtitle_review_preview_spec(current_spec)
        live_hash = subtitle_review_preview_spec_hash(live_spec)
        live_artifacts = live_subtitle_review_preview_paths(
            job_dir,
            clip_id,
            live_hash,
        )
        preview_ready = exact_subtitle_review_preview_is_ready(
            artifacts,
            spec_hash,
        ) and live_subtitle_review_preview_is_ready(live_artifacts, live_hash)

        if not preview_ready:
            try:
                result = _render_exact_subtitle_review_preview_for_clip(
                    dependencies=deps,
                    input_path=storage_paths.resolve_stored_file(video.stored_path),
                    job_dir=job_dir,
                    job=job,
                    video=video,
                    document=document,
                    paths=storage_paths,
                    clip_id=clip_id,
                )
            except Exception as exc:
                write_subtitle_review_preview_error(
                    job_dir,
                    clip_id,
                    spec_hash,
                    str(exc),
                )
                raise

            if result.spec_hash != spec_hash:
                raise RuntimeError("subtitle review preview renderer returned a stale spec")
            try:
                exact_subtitle_review_preview_error_path(
                    job_dir,
                    clip_id,
                    spec_hash,
                ).unlink(missing_ok=True)
            except OSError:
                pass

        render_revision = _prepare_auto_render_after_preview(
            db=db,
            job=job,
            video=video,
            storage_paths=storage_paths,
        )
        if render_revision is None:
            return ["ready"]
        try:
            from app.jobs.queue import enqueue_subtitle_review_render

            enqueue_subtitle_review_render(job.id, render_revision)
        except Exception:
            _restore_auto_review_after_enqueue_failure(
                db=db,
                job=job,
                storage_paths=storage_paths,
            )
            raise
        return ["ready", "render_queued"]


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

        try:
            with subtitle_review_document_lock(job_dir):
                stored_payloads = {
                    path: path.read_bytes() if path.is_file() else None for path in (review_path, summary_path, selected_path)
                }
                document = load_subtitle_review(review_path)
                selection = CandidateSelection.model_validate(_read_json_file(selected_path))
                reviewed_clip = next(
                    (item for item in document.clips if item.id == clip_id),
                    None,
                )
                if reviewed_clip is None:
                    raise ValueError(f"subtitle review clip not found: {clip_id}")
                target_candidates = selection.shorts if reviewed_clip.type == "short" else selection.normal_clips
                candidate = next(
                    (item for item in target_candidates if item.id == clip_id),
                    None,
                )
                if candidate is None:
                    raise ValueError(f"selected clip not found: {clip_id}")

                next_document = document.model_copy(deep=True)
                next_document.short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
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

            result = _render_exact_subtitle_review_preview_for_clip(
                dependencies=deps,
                input_path=storage_paths.resolve_stored_file(video.stored_path),
                job_dir=job_dir,
                job=job,
                video=video,
                document=next_document,
                paths=storage_paths,
                clip_id=clip_id,
            )
            _mark_subtitle_review_preview_ready(
                next_document,
                clip_id=clip_id,
                spec_hash=result.spec_hash,
                live_spec_hash=result.live_spec_hash,
            )
            target_index = next(index for index, item in enumerate(target_candidates) if item.id == clip_id)
            target_candidates[target_index] = updated_candidate
            with subtitle_review_document_lock(job_dir):
                current_review_payload = review_path.read_bytes() if review_path.is_file() else None
                current_selected_payload = selected_path.read_bytes() if selected_path.is_file() else None
                if current_review_payload != stored_payloads[review_path] or current_selected_payload != stored_payloads[selected_path]:
                    raise RuntimeError("subtitle review changed while hook preview was rendering")
                try:
                    write_selected_clips(selection, selected_path)
                    write_subtitle_review(next_document, review_path)
                    write_subtitle_review_summary(next_document, summary_path)
                except Exception:
                    for path, payload in stored_payloads.items():
                        if payload is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(payload)
                    raise

            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )

            _set_status(db, job, "awaiting_subtitle_review")
            visited_statuses.append("awaiting_subtitle_review")
        except Exception as exc:
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
            job.current_step = "冒頭フック映像の更新に失敗しました。時間を確認して再試行してください"
            job.error_code = "subtitle_review_hook_scene_update_failed"
            job.error_message = str(exc)
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
            raise

    return visited_statuses


def run_subtitle_review_render(
    job_id: str,
    *,
    render_revision: int,
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
        rerender_promotion: _SubtitleRerenderPromotion | None = None
        previous_export_ids: set[str] = set()
        rerender_publication_committed = False
        is_rerender = False
        pending_rerender_zip: Path | None = None
        rerender_publication_was_unresolved = False
        rerender_publication_lease: Any | None = None
        rerender_attempt_id: str | None = None
        rerender_publication_marker_created = False

        try:
            review_document = load_subtitle_review(review_path)
            if review_document.render_revision != render_revision:
                return visited_statuses
            is_rerender = review_document.render_revision > 1
            if not is_rerender:
                if review_document.state == "completed":
                    return visited_statuses
                if review_document.state not in {"render_queued", "rendering"}:
                    raise PipelineExpectedError(
                        "subtitle_review_not_ready",
                        "Subtitle review has not been finalized.",
                    )
            if is_rerender:
                if review_document.state not in {
                    "render_queued",
                    "rendering",
                    "completed",
                }:
                    return visited_statuses
                rerender_publication_lease = try_acquire_rerender_publication_lease(
                    job_dir,
                    job_id=job.id,
                    render_revision=review_document.render_revision,
                )
                if rerender_publication_lease is None:
                    return visited_statuses
                rerender_attempt_id = rerender_publication_lease.attempt_id
                rerender_publication_was_unresolved = (
                    rerender_publication_is_unresolved(job_dir)
                )
                if review_document.state == "completed":
                    if not rerender_publication_was_unresolved:
                        return visited_statuses
                    review_document = queue_review_render(
                        restore_review_after_render_failure(review_document)
                    )
                    write_subtitle_review(review_document, review_path)
                    write_subtitle_review_summary(
                        review_document,
                        subtitle_review_summary_path(job_dir),
                    )
                if not rerender_publication_was_unresolved:
                    mark_rerender_publication_unresolved(
                        job_dir,
                        job_id=job.id,
                        render_revision=review_document.render_revision,
                        attempt_id=rerender_attempt_id,
                    )
                    rerender_publication_marker_created = True

            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )
            effective_automation_mode = _active_quality_gate_mode(
                job_dir,
                settings,
            )
            if effective_automation_mode is not None:
                title_hook_evidence = (
                    _load_title_hook_evidence(job_dir, review_document)
                    if effective_automation_mode == "auto"
                    else {}
                )
                try:
                    content_gate = evaluate_content_quality_gate(
                        job_id=job.id,
                        document=review_document,
                        settings=settings,
                        mode=effective_automation_mode,
                        title_hook_evidence=title_hook_evidence,
                    )
                except Exception as exc:
                    content_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="content",
                        reason_code="content_gate_evaluation_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode=effective_automation_mode,
                    )
                content_gate_path = _try_write_quality_gate_decision(
                    content_gate,
                    quality_gate_decision_path(job_dir, "content"),
                )
                enforced_content_blocked = (
                    effective_automation_mode in {"guarded", "auto"}
                    and (
                        content_gate_path is None
                        or content_gate.route != "continue"
                    )
                )
                if enforced_content_blocked:
                    if (
                        is_rerender
                        and rerender_publication_marker_created
                        and rerender_attempt_id is not None
                    ):
                        clear_rerender_publication_unresolved(
                            job_dir,
                            expected_attempt_id=rerender_attempt_id,
                        )
                    _restore_subtitle_rerender_for_retry(
                        db=db,
                        job=job,
                        review_document=review_document,
                        review_path=review_path,
                        code=(
                            "quality_gate_record_failed"
                            if content_gate_path is None
                            else "quality_gate_content_review_required"
                        ),
                        message=(
                            "Enforced content quality decision could not be recorded."
                            if content_gate_path is None
                            else "Enforced content quality checks require subtitle review."
                        ),
                    )
                    visited_statuses.append("awaiting_subtitle_review")
                    return visited_statuses

            review_document = mark_review_rendering(review_document)
            write_subtitle_review(review_document, review_path)
            write_subtitle_review_summary(
                review_document,
                subtitle_review_summary_path(job_dir),
            )

            source_snapshot = subtitle_review_source_path(job_dir, review_document)
            transcript_segments = _read_transcript_segments(
                source_snapshot if source_snapshot.exists() else transcript_output_path(job_dir)
            )
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
            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "post_render"),
            )
            previous_exports = list(db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all())
            previous_export_ids = {export.id for export in previous_exports}
            render_paths = storage_paths
            if is_rerender:
                rerender_staging_paths = _prepare_subtitle_rerender_staging(
                    storage_paths,
                    job.id,
                    review_document.render_revision,
                    attempt_id=rerender_attempt_id,
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
                asset_storage_paths=storage_paths,
                dependencies=deps,
                visited_statuses=visited_statuses,
            )
            post_render_gate: QualityGateDecision | None = None
            if effective_automation_mode is not None:
                gate_exports: Sequence[Any] = exports
                if rerender_staging_paths is not None:
                    gate_exports = _project_staged_exports_for_quality_gate(
                        exports,
                        staging_job_dir=rerender_staging_paths.job_outputs(job.id),
                        canonical_job_dir=storage_paths.job_outputs(job.id),
                    )
                try:
                    post_render_gate = evaluate_post_render_quality_gate(
                        job_id=job.id,
                        expected_export_count=(
                            len(selection.normal_clips) + len(selection.shorts)
                        ),
                        exports=gate_exports,
                        render_failures=[
                            *normal_result.failures,
                            *short_result.failures,
                        ],
                        mode=effective_automation_mode,
                        document=review_document,
                    )
                except Exception as exc:
                    post_render_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="post_render",
                        reason_code="post_render_gate_evaluation_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode=effective_automation_mode,
                    )
                post_render_gate_path = _try_write_quality_gate_decision(
                    post_render_gate,
                    quality_gate_decision_path(job_dir, "post_render"),
                )
                if (
                    effective_automation_mode == "auto"
                    and not is_rerender
                    and (
                        post_render_gate_path is None
                        or post_render_gate.route != "continue"
                    )
                ):
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    review_document = restore_review_after_render_failure(
                        review_document
                    )
                    write_subtitle_review(review_document, review_path)
                    write_subtitle_review_summary(
                        review_document,
                        subtitle_review_summary_path(job_dir),
                    )
                    _set_status(db, job, "awaiting_subtitle_review")
                    visited_statuses.append("awaiting_subtitle_review")
                    return visited_statuses
                if (
                    post_render_gate_path is None
                    and effective_automation_mode in {"guarded", "auto"}
                ):
                    raise PipelineExpectedError(
                        "quality_gate_record_failed",
                        "Enforced post-render quality decision could not be recorded.",
                    )
                if (
                    effective_automation_mode in {"guarded", "auto"}
                    and post_render_gate.route != "continue"
                ):
                    raise PipelineExpectedError(
                        "quality_gate_render_failed",
                        "Enforced quality gate rejected incomplete rendered output.",
                        details={
                            "qualityGateStage": "post_render",
                            "qualityGateOutcome": post_render_gate.outcome,
                            "qualityGateInputHash": post_render_gate.input_hash,
                        },
                    )
            if not exports:
                raise PipelineExpectedError(
                    "no_usable_output",
                    "Selected clips did not produce usable rendered output.",
                )
            if rerender_staging_paths is not None and (normal_result.failures or short_result.failures):
                raise PipelineExpectedError(
                    "subtitle_rerender_incomplete",
                    "Re-render did not complete for every existing clip. Previous outputs were kept.",
                )
            generate_export_thumbnails(
                exports=exports,
                selection=selection,
                input_path=input_path,
                job_output_dir=render_paths.job_outputs(job.id),
                normal_renderer=deps.normal_thumbnail_renderer,
                short_renderer=deps.short_thumbnail_renderer,
                character_style=settings.get("normalThumbnailStyle"),
                db=db, job=job, paths=storage_paths,
            )
            if rerender_staging_paths is not None:
                exports, _render_failures_path, rerender_promotion = _promote_subtitle_rerender(
                    db=db,
                    job=job,
                    previous_exports=previous_exports,
                    staged_exports=exports,
                    staged_render_failures_path=_render_failures_path,
                    staging_paths=rerender_staging_paths,
                    storage_paths=storage_paths,
                )

            audio_features_payload = _read_json_file(job_dir / "audio_features.json")
            audio_features = AudioFeatures.model_validate(audio_features_payload)
            normal_candidates = _read_model_list(job_dir / "normal_candidates.json", Candidate)
            short_candidates = _read_model_list(job_dir / "short_candidates.json", Candidate)
            scored_candidates = _read_model_list(job_dir / "scored_candidates.json", Candidate)
            candidate_generation_summary = _read_json_file(job_dir / "candidate_generation_summary.json")
            transcript_summary_path = job_dir / "transcript_summary.json"
            transcript_summary = _read_json_file(transcript_summary_path) if transcript_summary_path.is_file() else {}

            write_generation_summaries(
                job_dir,
                transcript_segments=transcript_segments,
                audio_features=audio_features,
                normal_candidates=normal_candidates,
                short_candidates=short_candidates,
                candidate_generation_summary=candidate_generation_summary,
                scored_candidates=scored_candidates,
                selection=selection,
                normal_result=normal_result,
                short_result=short_result,
                exports=exports,
                transcription_engine=str(transcript_summary.get("transcription_engine", "not_run")),
                used_fixture_transcript=bool(transcript_summary.get("used_fixture_transcript", False)),
                transcription_model=transcript_summary.get("transcription_model"),
                transcription_language=transcript_summary.get("transcription_language"),
                transcription_diagnostics=transcript_summary.get("transcription_runtime"),
            )

            if is_rerender:
                _assign_status(job, "packaging_zip")
            else:
                _set_status(db, job, "packaging_zip")
            visited_statuses.append("packaging_zip")
            review_document = mark_review_completed(review_document)
            write_subtitle_review(review_document, review_path)
            write_subtitle_review_summary(
                review_document,
                subtitle_review_summary_path(job_dir),
            )
            if rerender_staging_paths is not None:
                if rerender_promotion is None:
                    raise RuntimeError("subtitle rerender promotion is unavailable")
                _write_youtube_posting_artifacts_for_publication(
                    review_document.clips,
                    exports,
                    job_dir=job_dir,
                    staging_job_dir=rerender_staging_paths.job_outputs(job.id),
                    promotion=rerender_promotion,
                )
            else:
                _write_youtube_posting_artifacts_for_publication(
                    review_document.clips,
                    exports,
                    job_dir=job_dir,
                )
            zip_path = storage_paths.zip_path(job.id)
            if is_rerender:
                if rerender_promotion is None:
                    raise RuntimeError("subtitle rerender promotion is unavailable")
                pending_rerender_zip = job_dir / f".download_revision_{review_document.render_revision}.tmp.zip"
                pending_rerender_zip.unlink(missing_ok=True)
                _create_zip(
                    pending_rerender_zip,
                    exports,
                    metadata_files=_top_level_metadata_files(job_dir),
                )
                rerender_promotion.publish(pending_rerender_zip, zip_path)
                pending_rerender_zip = None
                _assign_status(job, "completed")
                record_completed_exports(db, job, storage_paths)
                db.commit()
                rerender_publication_committed = True
                rerender_promotion.finalize()
                if rerender_publication_was_unresolved:
                    clear_rerender_publication_unresolved(job_dir)
                else:
                    clear_rerender_publication_unresolved(
                        job_dir,
                        expected_attempt_id=rerender_attempt_id,
                    )
            else:
                _create_zip(
                    zip_path,
                    exports,
                    metadata_files=_top_level_metadata_files(job_dir),
                )

                _set_status(db, job, "completed")
            visited_statuses.append("completed")
            prune_job_previews_after_completion(db, job, storage_paths)
            enqueue_completed_job_harvest(db, job, storage_paths)
        except PipelineExpectedError as exc:
            if pending_rerender_zip is not None:
                pending_rerender_zip.unlink(missing_ok=True)
            if is_rerender and review_document is not None:
                rollback_succeeded = True
                if not rerender_publication_committed:
                    rollback_succeeded = _rollback_subtitle_rerender_publication(
                        db=db,
                        promotion=rerender_promotion,
                        error=exc,
                    )
                if rerender_staging_paths is not None and not rerender_publication_committed:
                    _discard_subtitle_rerender_staging(
                        db=db,
                        job_id=job.id,
                        previous_export_ids=previous_export_ids,
                        staging_paths=rerender_staging_paths,
                        remove_files=rollback_succeeded,
                    )
                if (
                    rollback_succeeded
                    and rerender_publication_marker_created
                    and rerender_attempt_id is not None
                ):
                    clear_rerender_publication_unresolved(
                        job_dir,
                        expected_attempt_id=rerender_attempt_id,
                    )
                invalidate_quality_gate_decisions(job_dir, ("post_render",))
                _restore_subtitle_rerender_for_retry(
                    db=db,
                    job=job,
                    review_document=review_document,
                    review_path=review_path,
                    code=(
                        exc.code
                        if rollback_succeeded
                        else "subtitle_rerender_rollback_failed"
                    ),
                    message=(
                        exc.message
                        if rollback_succeeded
                        else "Subtitle re-render rollback failed; recovery files were preserved."
                    ),
                )
            else:
                _fail_job(db, job_id, exc.code, exc.message, details=exc.details)
        except Exception as exc:
            if pending_rerender_zip is not None:
                pending_rerender_zip.unlink(missing_ok=True)
            if is_rerender and review_document is not None:
                rollback_succeeded = True
                if not rerender_publication_committed:
                    rollback_succeeded = _rollback_subtitle_rerender_publication(
                        db=db,
                        promotion=rerender_promotion,
                        error=exc,
                    )
                if rerender_staging_paths is not None and not rerender_publication_committed:
                    _discard_subtitle_rerender_staging(
                        db=db,
                        job_id=job.id,
                        previous_export_ids=previous_export_ids,
                        staging_paths=rerender_staging_paths,
                        remove_files=rollback_succeeded,
                    )
                if (
                    rollback_succeeded
                    and rerender_publication_marker_created
                    and rerender_attempt_id is not None
                ):
                    clear_rerender_publication_unresolved(
                        job_dir,
                        expected_attempt_id=rerender_attempt_id,
                    )
                invalidate_quality_gate_decisions(job_dir, ("post_render",))
                _restore_subtitle_rerender_for_retry(
                    db=db,
                    job=job,
                    review_document=review_document,
                    review_path=review_path,
                    code=(
                        "subtitle_review_render_failed"
                        if rollback_succeeded
                        else "subtitle_rerender_rollback_failed"
                    ),
                    message=(
                        str(exc)
                        if rollback_succeeded
                        else "Subtitle re-render rollback failed; recovery files were preserved."
                    ),
                )
            else:
                _fail_job(db, job_id, "subtitle_review_render_failed", str(exc))
            raise
        finally:
            if rerender_publication_lease is not None:
                rerender_publication_lease.release()

    return visited_statuses
