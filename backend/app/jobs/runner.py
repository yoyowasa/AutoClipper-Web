import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
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
    DEFAULT_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
    DEFAULT_TRANSCRIPTION_CHUNK_SECONDS,
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
from app.audio.volume_features import (
    AudioFeatures,
    audio_features_output_path,
    build_audio_features,
    compute_audio_features,
    write_audio_features,
)
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.boundary_refinement import refine_selected_candidates
from app.candidates.codex_initial_selection import (
    CodexInitialSelectionError,
    CodexInitialSelectionResult,
    codex_initial_selection_summary_output_path,
    request_codex_initial_selection,
    write_codex_initial_selection_summary,
)
from app.candidates.generate_normal_candidates import generate_normal_candidates_with_summary
from app.candidates.generate_short_candidates import generate_short_candidates_with_summary
from app.candidates.generate_heatmap_candidates import generate_heatmap_candidates_with_summary
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
    CandidateType,
    OpenAIScoreSource,
    merge_candidate_generation_summaries,
    write_candidates,
)
from app.candidates.select_candidates import (
    CandidateRejection,
    CandidateSelection,
    parse_selection_settings,
    select_candidates,
    write_selected_clips,
)
from app.candidates.title_fallback import titled_candidates
from app.config import get_settings
from app.db import SessionLocal
from app.ids import make_id
from app.jobs.clip_plan import (
    build_clip_plan,
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_approved,
    mark_clip_plan_awaiting_review,
    update_clip_plan_boundary,
    update_clip_plan_hook_scene,
    write_clip_plan,
)
from app.jobs.automation import (
    automation_manifest_path,
    build_automation_manifest,
    load_automation_manifest,
    write_automation_manifest,
)
from app.jobs.quality_gate import (
    QualityGateDecision,
    QualityGateMode,
    evaluate_content_quality_gate,
    evaluate_post_render_quality_gate,
    evaluate_selection_quality_gate,
    invalidate_quality_gate_decisions,
    quality_gate_decision_path,
    unknown_quality_gate_decision,
    write_quality_gate_decision,
)
from app.jobs.publication_state import (
    clear_rerender_publication_unresolved,
    mark_rerender_publication_unresolved,
    rerender_publication_is_unresolved,
    try_acquire_rerender_publication_lease,
)
from app.jobs.hook_scene import hook_scene_newly_exceeds_short_limit
from app.jobs.manual_workflow import (
    apply_manual_clip_metadata,
    build_manual_selection,
    is_manual_workflow,
    manual_edit_is_finalized,
    manual_subtitle_mode,
)
from app.candidates.short_diversity import (
    ShortDiversityResult,
    ShortDiversitySettings,
    select_diverse_shorts,
)
from app.jobs.summaries import write_generation_summaries
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP, SUCCESS_STATUSES
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    apply_reviewed_text,
    build_manual_subtitle_segments,
    build_subtitle_review,
    load_subtitle_review,
    mark_review_completed,
    mark_review_rendering,
    queue_review_render,
    reviewed_transcript_output_path,
    restore_review_after_render_failure,
    subtitle_review_output_path,
    subtitle_review_preview_path,
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
    subtitle_review_document_lock,
    subtitle_review_preview_url as exact_subtitle_review_preview_url,
    write_subtitle_review_preview_error,
)
from app.models import ExportItem, Job, Video, utc_now
from app.posting_metadata import write_youtube_posting_artifacts
from app.render.render_normal import NormalRenderBatchResult, render_normal_clip, render_selected_normal_candidates
from app.render.render_exact_review_preview import (
    ExactPreviewResult,
    build_live_subtitle_review_preview_spec,
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
    render_exact_subtitle_review_preview,
    subtitle_review_preview_spec_hash,
)
from app.render.render_manual_source_proxy import (
    manual_source_proxy_path,
    manual_source_proxy_url,
    render_manual_source_proxy,
)
from app.render.render_review_preview import render_review_preview
from app.render.render_short import ShortRenderBatchResult, render_selected_short_candidates, render_short_clip
from app.scoring.openai_score import OpenAICandidateScorer, score_candidate_batch
from app.scoring.clip_preferences import build_clip_selection_preferences
from app.scoring.heatmap import annotate_candidates_with_heatmap
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
from app.video.heatmap import HeatmapSegment, load_heatmap_for_video
from app.video.probe import VideoMetadata, probe_metadata
from app.video.scene_detect import SceneSegment, scene_output_path, scene_segments_from_boundaries, write_scene_segments
from app.video.scene_detect import detect_scenes as default_detect_scenes


SessionFactory = Callable[[], Session]
ProbeMetadata = Callable[[str | Path], VideoMetadata]
ExtractAudio = Callable[[str | Path, str | Path], Path]
TranscribeAudio = Callable[[str | Path], list[TranscriptSegment]]
TranscriptionEngineFactory = Callable[..., FasterWhisperTranscriptionEngine]
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
    transcription_engine_factory: TranscriptionEngineFactory = FasterWhisperTranscriptionEngine
    detect_scenes: DetectScenes = default_detect_scenes
    detect_silence: DetectSilence | None = None
    compute_audio_features: ComputeAudioFeatures = compute_audio_features
    detect_black_screen: DetectBlackScreen = detect_black_screen
    normal_renderer: Callable[..., Path] = render_normal_clip
    short_renderer: Callable[..., Any] = render_short_clip
    manual_source_proxy_renderer: Callable[..., Path] = render_manual_source_proxy
    subtitle_review_preview_renderer: Callable[..., Path] = render_review_preview
    subtitle_review_exact_preview_renderer: Callable[..., ExactPreviewResult] = render_exact_subtitle_review_preview
    openai_scorer: OpenAICandidateScorer | None = None
    transcript_corrector: OpenAITranscriptCorrector | None = None
    codex_initial_selector: Callable[..., Any] = request_codex_initial_selection


class PipelineExpectedError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


WHISPER_MODEL_SIZES = {"base", "small", "medium", "large-v3", "turbo"}
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


def _subtitle_correction_mode_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionMode") or settings.get("subtitle_correction_mode") or "off"
    normalized = str(value).strip().lower()
    return normalized if normalized in {"off", "openai"} else "off"


def _subtitle_correction_model_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionModel") or settings.get("subtitle_correction_model") or "gpt-5.5"
    normalized = str(value).strip()
    return normalized or "gpt-5.5"


def _subtitle_correction_reasoning_effort_setting(settings: dict[str, Any]) -> str:
    value = settings.get("subtitleCorrectionReasoningEffort") or settings.get("subtitle_correction_reasoning_effort") or "default"
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


def _has_automatic_clip_output(settings: dict[str, Any]) -> bool:
    normal_automatic = _int_setting(settings, "normalClipCount", 2) > 0 and not settings.get("normalClipTimeRanges")
    short_automatic = _int_setting(settings, "shortCount", 3) > 0 and not settings.get("shortClipTimeRanges")
    return normal_automatic or short_automatic


def _heatmap_summary_for_selection_mode(
    summary: dict[str, object],
    segments: Sequence[HeatmapSegment],
    settings: dict[str, Any],
    *,
    video_duration: float,
) -> tuple[dict[str, object], bool]:
    requested = _bool_setting(settings, "heatmapIntervalMode", False)
    automatic_output = _has_automatic_clip_output(settings)
    positive_segments = sum(1 for segment in segments if segment.value > 0)
    usable_positive_segments = sum(
        1
        for segment in segments
        if segment.value > 0 and min(float(segment.end_time), video_duration) > max(float(segment.start_time), 0.0)
    )
    available = usable_positive_segments > 0
    interval_mode_applied = requested and automatic_output and available
    selection_behavior = (
        "heatmap_intervals" if interval_mode_applied else "manual_ranges" if requested and not automatic_output else "supporting_score"
    )
    updated = {
        **summary,
        "interval_mode_requested": requested,
        "interval_mode_applied": interval_mode_applied,
        "automatic_output_requested": automatic_output,
        "positive_segment_count": positive_segments,
        "usable_positive_segment_count": usable_positive_segments,
        "selection_behavior": selection_behavior,
    }
    should_fail = requested and automatic_output and not available
    if should_fail:
        updated["interval_mode_unavailable_reason"] = summary.get("fallback_reason") or (
            "heatmap_has_no_positive_segments_in_video" if positive_segments > 0 else "heatmap_has_no_positive_segments"
        )
    return updated, should_fail


def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _generate_candidates_for_reselection_mode(
    *,
    settings: dict[str, Any],
    transcript_segments: list[TranscriptSegment],
    scene_segments: list[SceneSegment],
    silence_segments: list[SilenceSegment],
    heatmap_segments: Sequence[HeatmapSegment],
    video_duration: float,
    heartbeat: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[Candidate], list[Candidate], dict[str, Any]]:
    normal_manual_ranges = manual_ranges_for_type(settings, "normal")
    short_manual_ranges = manual_ranges_for_type(settings, "short")
    heatmap_interval_mode = _bool_setting(settings, "heatmapIntervalMode", False)

    normal_generation_result = (
        build_manual_candidates(
            "normal",
            normal_manual_ranges,
            transcript_segments,
        )
        if normal_manual_ranges
        else generate_heatmap_candidates_with_summary(
            "normal",
            heatmap_segments=heatmap_segments,
            transcript_segments=transcript_segments,
            video_duration=video_duration,
            requested_count=_int_setting(settings, "normalClipCount", 2),
            settings=settings,
            heartbeat=heartbeat,
        )
        if heatmap_interval_mode
        else generate_normal_candidates_with_summary(
            transcript_segments,
            scene_segments,
            silence_segments,
            settings=settings,
            heartbeat=heartbeat,
        )
    )
    short_generation_result = (
        build_manual_candidates(
            "short",
            short_manual_ranges,
            transcript_segments,
        )
        if short_manual_ranges
        else generate_heatmap_candidates_with_summary(
            "short",
            heatmap_segments=heatmap_segments,
            transcript_segments=transcript_segments,
            video_duration=video_duration,
            requested_count=_int_setting(settings, "shortCount", 3),
            settings=settings,
            heartbeat=heartbeat,
        )
        if heatmap_interval_mode
        else generate_short_candidates_with_summary(
            transcript_segments,
            scene_segments,
            silence_segments,
            settings=settings,
            heartbeat=heartbeat,
        )
    )
    normal_candidates = annotate_candidates_with_heatmap(
        normal_generation_result.candidates,
        heatmap_segments,
    )
    short_candidates = annotate_candidates_with_heatmap(
        short_generation_result.candidates,
        heatmap_segments,
    )
    summary = merge_candidate_generation_summaries(
        [normal_generation_result.summary, short_generation_result.summary],
        video_duration=video_duration,
        transcript_segment_count=len(transcript_segments),
    )

    if heatmap_interval_mode:
        missing_candidate_types = [
            candidate_type
            for candidate_type, requested_count, manual_ranges, candidates in (
                (
                    "normal",
                    _int_setting(settings, "normalClipCount", 2),
                    normal_manual_ranges,
                    normal_candidates,
                ),
                (
                    "short",
                    _int_setting(settings, "shortCount", 3),
                    short_manual_ranges,
                    short_candidates,
                ),
            )
            if requested_count > 0 and not manual_ranges and not candidates
        ]
        if missing_candidate_types:
            raise PipelineExpectedError(
                "heatmap_interval_mode_no_candidates",
                "人気区間JSONから設定時間と字幕条件を満たす候補を生成できませんでした。",
                details={"candidateTypes": missing_candidate_types},
            )

    if not normal_candidates and not short_candidates:
        raise PipelineExpectedError(
            ("heatmap_interval_mode_no_candidates" if heatmap_interval_mode else "no_candidates_found"),
            (
                "人気区間JSONから設定時間と字幕条件を満たす候補を生成できませんでした。"
                if heatmap_interval_mode
                else "No clip candidates were found for the selected settings."
            ),
        )
    return normal_candidates, short_candidates, summary


def _openai_model_setting(settings: dict[str, Any]) -> str:
    value = settings.get("openaiModel") or settings.get("openai_model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "gpt-5.5"


def _openai_enabled(settings: dict[str, Any]) -> bool:
    return bool(settings.get("useOpenAIScoring") or settings.get("openaiScoring") or settings.get("enableOpenAIScoring"))


def _codex_initial_selection_enabled(
    settings: dict[str, Any],
    *,
    manual_workflow: bool,
    has_manual_ranges: bool,
) -> bool:
    provider = str(settings.get("initialSelectionProvider") or "legacy").strip().lower()
    return provider == "codex" and not manual_workflow and not has_manual_ranges


def _require_all_requested_heatmap_candidate_types(
    codex_selection: CandidateSelection | None,
) -> bool:
    return not (codex_selection is not None and codex_selection.selection_policy == "strict_quality")


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


def _assign_status(job: Job, status: str) -> None:
    job.status = status
    job.progress = PROGRESS_MAP[status]
    job.current_step = CURRENT_STEP_MAP[status]
    job.updated_at = utc_now()
    if status != "failed":
        job.error_code = None
        job.error_message = None


def _set_status(db: Session, job: Job, status: str) -> None:
    _assign_status(job, status)
    db.commit()
    db.refresh(job)


def _try_write_quality_gate_decision(
    document: QualityGateDecision,
    output_path: Path,
) -> Path | None:
    try:
        return write_quality_gate_decision(document, output_path)
    except OSError:
        return None


def _active_quality_gate_mode(
    job_dir: Path,
    settings: Mapping[str, Any],
) -> QualityGateMode | None:
    requested_mode = str(settings.get("automationMode") or "manual").strip()
    manifest_path = automation_manifest_path(job_dir)
    if manifest_path.is_file():
        try:
            effective_mode = load_automation_manifest(manifest_path).effective_mode
        except (OSError, ValueError):
            pass
        else:
            return effective_mode if effective_mode in {"shadow", "guarded"} else None
    return requested_mode if requested_mode in {"shadow", "guarded"} else None


def _evaluate_selection_quality_gate_for_mode(
    *,
    job_id: str,
    job_dir: Path,
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    settings: Mapping[str, Any],
    source_duration: float,
    mode: QualityGateMode,
) -> tuple[QualityGateDecision, Path | None]:
    invalidate_quality_gate_decisions(
        job_dir,
        ("selection", "content", "post_render"),
    )
    try:
        decision = evaluate_selection_quality_gate(
            job_id=job_id,
            selection=selection,
            transcript_segments=transcript_segments,
            settings=settings,
            source_duration=source_duration,
            mode=mode,
        )
    except Exception as exc:
        decision = unknown_quality_gate_decision(
            job_id=job_id,
            stage="selection",
            reason_code="selection_gate_evaluation_failed",
            evidence={"errorType": exc.__class__.__name__},
            mode=mode,
        )
    decision_path = _try_write_quality_gate_decision(
        decision,
        quality_gate_decision_path(job_dir, "selection"),
    )
    if decision_path is None and mode == "guarded":
        decision = unknown_quality_gate_decision(
            job_id=job_id,
            stage="selection",
            reason_code="selection_gate_record_unavailable",
            mode=mode,
        )
    return decision, decision_path


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
    job.current_step = f"切り抜き予定の確認動画を準備中 ({bounded_completed}/{total})"
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


def _normalized_segment_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold(), flags=re.UNICODE)


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
    summary["candidates_sent_preselection"] = preselection_candidates_sent if preselection_candidates_sent is not None else candidates_sent
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
        key=lambda cluster: _candidate_rank_value(grouped[cluster][0]) if grouped[cluster] else (0.0, 0.0, 0.0, 0, 0.0),
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
            candidate for candidate in _openai_cluster_diverse_order(hard_gate_passed, candidate_limit) if candidate.id not in selected_ids
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
        return ScoringResult(candidates=[candidate.model_copy(update={"final_score": candidate.rule_score}) for candidate in rule_scored])

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

    failed_candidates = [candidate for candidate in openai_scored if "openai_scoring_failed" in candidate.risk_flags]
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
            "selected_above_threshold_count": sum(1 for candidate in selected if candidate.below_quality_threshold is False),
            "selected_below_threshold_backfill_count": sum(1 for candidate in selected if candidate.below_quality_threshold is True),
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
    heatmap_segments: Sequence[HeatmapSegment] = (),
) -> tuple[CandidateSelection, list[Candidate]]:
    def refine_unlocked(candidates: Sequence[Candidate]) -> list[Candidate]:
        unlocked = [candidate for candidate in candidates if candidate.selection_reason != MANUAL_SELECTION_REASON]
        refined = refine_selected_candidates(
            unlocked,
            transcript_segments=transcript_segments,
            silence_segments=silence_segments,
            scene_segments=scene_segments,
            settings=settings,
            timeline_duration=timeline_duration,
        )
        if heatmap_segments:
            refined = annotate_candidates_with_heatmap(refined, heatmap_segments)
        replacements = {candidate.id: candidate for candidate in refined}
        return [replacements.get(candidate.id, candidate) for candidate in candidates]

    normal_clips = refine_unlocked(selection.normal_clips)
    shorts = refine_unlocked(selection.shorts)
    replacements = {candidate.id: candidate for candidate in [*normal_clips, *shorts]}
    return (
        selection.model_copy(update={"normal_clips": normal_clips, "shorts": shorts}),
        _replace_scored_candidates(scored_candidates, replacements),
    )


def _codex_selection_with_diverse_refined_shorts(
    result: CodexInitialSelectionResult,
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    settings: dict[str, Any],
    timeline_duration: float,
    heatmap_segments: Sequence[HeatmapSegment] = (),
) -> tuple[CandidateSelection, list[Candidate], ShortDiversityResult]:
    def rank_key(candidate: Candidate) -> tuple[float, str]:
        score = candidate.final_score
        if score is None:
            score = candidate.ai_score
        return (-(score if score is not None else 0.0), candidate.id)

    candidate_pool = list(result.candidates)
    short_pool = sorted(
        (candidate for candidate in candidate_pool if candidate.type == "short"),
        key=rank_key,
    )
    pool_selection = result.selection.model_copy(update={"shorts": short_pool})
    refined_pool_selection, refined_candidates = _selection_with_refined_boundaries(
        pool_selection,
        candidate_pool,
        transcript_segments=transcript_segments,
        silence_segments=silence_segments,
        scene_segments=scene_segments,
        settings=settings,
        timeline_duration=timeline_duration,
        heatmap_segments=heatmap_segments,
    )

    cross_type_rejections: list[CandidateRejection] = []
    eligible_shorts: list[Candidate] = []
    parsed_settings = parse_selection_settings(settings)
    for candidate in refined_pool_selection.shorts:
        conflicting_normal = next(
            (
                normal
                for normal in refined_pool_selection.normal_clips
                if parsed_settings.cross_type_overlap_dedupe and time_overlap_ratio(candidate, normal) >= parsed_settings.max_overlap_ratio
            ),
            None,
        )
        if conflicting_normal is None:
            eligible_shorts.append(candidate)
            continue
        cross_type_rejections.append(
            CandidateRejection(
                candidateId=candidate.id,
                type="short",
                reasons=["post_refinement_cross_type_overlap"],
                details={"overlapWith": conflicting_normal.id},
            )
        )

    diversity = select_diverse_shorts(
        eligible_shorts,
        requested_count=result.selection.requested_short_count,
        settings=ShortDiversitySettings(
            enforce_heatmap_segment_uniqueness=_bool_setting(
                settings,
                "heatmapIntervalMode",
                False,
            )
        ),
    )
    diversity_rejections = [
        CandidateRejection(
            candidateId=rejection.candidate_id,
            type="short",
            reasons=[f"post_refinement_{reason}" for reason in rejection.reasons],
            details={
                "duplicateOf": rejection.duplicate_of,
                "overlapSeconds": rejection.overlap_seconds,
                "parentOverlapRatio": rejection.parent_overlap_ratio,
                "textSimilarity": rejection.text_similarity,
                "evidenceSimilarity": rejection.evidence_similarity,
            },
        )
        for rejection in diversity.rejected
    ]
    normal_unfilled = max(
        0,
        result.selection.requested_normal_count - len(refined_pool_selection.normal_clips),
    )
    short_unfilled = diversity.unfilled_count
    unfilled_reason_counts: dict[str, dict[str, int]] = {}
    if normal_unfilled:
        unfilled_reason_counts["normal"] = {"insufficient_codex_candidates": normal_unfilled}
    if short_unfilled:
        unfilled_reason_counts["short"] = {
            "insufficient_distinct_moments": short_unfilled,
            "post_refinement_duplicate": len(diversity.rejected),
            "post_refinement_cross_type_overlap": len(cross_type_rejections),
        }

    final_selection = refined_pool_selection.model_copy(
        update={
            "shorts": list(diversity.selected),
            "rejected_candidates": [
                *refined_pool_selection.rejected_candidates,
                *cross_type_rejections,
                *diversity_rejections,
            ],
            "cross_type_overlap_rejected_count": len(cross_type_rejections),
            "unfilled_requested_counts": {
                "normal": normal_unfilled,
                "short": short_unfilled,
            },
            "unfilled_reason_counts": unfilled_reason_counts,
        }
    )
    return final_selection, refined_candidates, diversity


def _automatic_selection_with_diverse_refined_shorts(
    scored_candidates: Sequence[Candidate],
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    settings: dict[str, Any],
    timeline_duration: float,
    audio_features: AudioFeatures,
    heatmap_segments: Sequence[HeatmapSegment] = (),
) -> tuple[CandidateSelection, list[Candidate], ShortDiversityResult]:
    """境界補正後の自動候補だけを再選定し、ショートの重複をhard除外する。"""

    automatic_candidates = [
        candidate
        for candidate in scored_candidates
        if candidate.selection_reason != MANUAL_SELECTION_REASON
    ]
    pool_selection = CandidateSelection(
        normalClips=[
            candidate for candidate in automatic_candidates if candidate.type == "normal"
        ],
        shorts=[
            candidate for candidate in automatic_candidates if candidate.type == "short"
        ],
    )
    _, refined_candidates = _selection_with_refined_boundaries(
        pool_selection,
        automatic_candidates,
        transcript_segments=transcript_segments,
        silence_segments=silence_segments,
        scene_segments=scene_segments,
        settings=settings,
        timeline_duration=timeline_duration,
        heatmap_segments=heatmap_segments,
    )

    parsed_settings = parse_selection_settings(settings)
    diversity_settings = ShortDiversitySettings(
        enforce_heatmap_segment_uniqueness=_bool_setting(
            settings,
            "heatmapIntervalMode",
            False,
        )
    )
    excluded_short_ids: set[str] = set()
    diversity_rejections = []

    while True:
        selectable_candidates = [
            candidate
            for candidate in refined_candidates
            if candidate.type != "short" or candidate.id not in excluded_short_ids
        ]
        selection = select_candidates(
            selectable_candidates,
            settings=settings,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        diversity = select_diverse_shorts(
            selection.shorts,
            requested_count=parsed_settings.short_count,
            settings=diversity_settings,
        )
        new_rejections = [
            rejection
            for rejection in diversity.rejected
            if rejection.candidate_id not in excluded_short_ids
        ]
        if not new_rejections:
            break
        diversity_rejections.extend(new_rejections)
        excluded_short_ids.update(
            rejection.candidate_id for rejection in new_rejections
        )

    translated_rejections = [
        CandidateRejection(
            candidateId=rejection.candidate_id,
            type="short",
            reasons=[f"post_refinement_{reason}" for reason in rejection.reasons],
            details={
                "duplicateOf": rejection.duplicate_of,
                "overlapSeconds": rejection.overlap_seconds,
                "parentOverlapRatio": rejection.parent_overlap_ratio,
                "textSimilarity": rejection.text_similarity,
                "evidenceSimilarity": rejection.evidence_similarity,
            },
        )
        for rejection in diversity_rejections
    ]
    short_unfilled = max(
        0,
        parsed_settings.short_count - len(diversity.selected),
    )
    unfilled_requested_counts = dict(selection.unfilled_requested_counts)
    unfilled_requested_counts["short"] = short_unfilled
    unfilled_reason_counts = {
        candidate_type: dict(counts)
        for candidate_type, counts in selection.unfilled_reason_counts.items()
    }
    if short_unfilled:
        short_reasons = unfilled_reason_counts.setdefault("short", {})
        short_reasons["post_refinement_duplicate"] = len(diversity_rejections)
        short_reasons["insufficient_distinct_moments"] = short_unfilled

    final_selection = selection.model_copy(
        update={
            "shorts": list(diversity.selected),
            "rejected_candidates": [
                *selection.rejected_candidates,
                *translated_rejections,
            ],
            "unfilled_requested_counts": unfilled_requested_counts,
            "unfilled_reason_counts": unfilled_reason_counts,
        }
    )
    aggregate_diversity = ShortDiversityResult(
        selected=tuple(diversity.selected),
        rejected=tuple(diversity_rejections),
        requested_count=parsed_settings.short_count,
    )
    return final_selection, refined_candidates, aggregate_diversity


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
    not_scored_due_to_limit = needs_scoring[len(finalists) :]
    fallback_enabled = _bool_setting(settings, "openaiFallbackToRuleScore", True)
    replacements: dict[str, Candidate] = {
        candidate.id: _candidate_not_scored(candidate, "finalist_scoring_limit") for candidate in not_scored_due_to_limit
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

    failed_finalists = [candidate for candidate in finalist_scored if "openai_scoring_failed" in candidate.risk_flags]
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
        candidate_id: _candidate_with_final_quality_metadata(candidate, settings) for candidate_id, candidate in replacements.items()
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
        short_top_banner_enabled=bool(settings.get("shortTopBannerEnabled", False)),
        short_bottom_banner_enabled=bool(settings.get("shortBottomBannerEnabled", False)),
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
        for value in (export.video_path, export.subtitle_path, export.metadata_path):
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


def _project_staged_exports_for_quality_gate(
    staged_exports: Sequence[ExportItem],
    *,
    staging_job_dir: Path,
    canonical_job_dir: Path,
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    resolved_staging_dir = staging_job_dir.resolve()
    for export in staged_exports:
        source_path = Path(export.video_path)
        relative_path = source_path.resolve().relative_to(resolved_staging_dir)
        projected.append(
            {
                "id": export.id,
                "candidateId": export.candidate_id,
                "type": export.type,
                "videoPath": str(canonical_job_dir / relative_path),
            }
        )
    return projected


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
) -> tuple[list[ExportItem], Path, _SubtitleRerenderPromotion]:
    staging_job_dir = staging_paths.job_outputs(job.id)
    canonical_job_dir = storage_paths.job_outputs(job.id)
    promotion = _SubtitleRerenderPromotion(
        staging_root=staging_paths.root,
        canonical_job_dir=canonical_job_dir,
        changes=[],
    )

    try:
        for export in staged_exports:
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
            export.metadata_path = _promote_staged_export_file(
                export.metadata_path,
                staging_job_dir=staging_job_dir,
                canonical_job_dir=canonical_job_dir,
                promotion=promotion,
            )
            _rewrite_export_metadata_paths(export)

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


def _cleanup_stale_clip_plan_previews(
    preview_dir: Path,
    current_preview_paths: set[Path],
) -> None:
    try:
        if not preview_dir.is_dir():
            return
        stale_candidates = list(preview_dir.glob("*.mp4"))
    except OSError:
        return

    for stale_path in stale_candidates:
        try:
            if stale_path.resolve() not in current_preview_paths:
                stale_path.unlink(missing_ok=True)
        except OSError:
            continue


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
            "no_usable_selection",
            "Pipeline completed analysis but selection produced no usable clips.",
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
                (f"Could not prepare clip plan preview for clip {preview_index}/{total}: {exc}"),
            ) from exc
        available_clip_ids.append(candidate.id)
        _set_clip_plan_preview_progress(
            db,
            job,
            completed=preview_index,
            total=total,
        )

    document = mark_clip_plan_awaiting_review(
        document,
        preview_clip_ids=available_clip_ids,
    )
    write_clip_plan(document, output_path)
    _set_status(db, job, "awaiting_clip_review")
    preview_dir = subtitle_review_preview_path(job_dir, "placeholder").parent
    _cleanup_stale_clip_plan_previews(preview_dir, current_preview_paths)
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
    heatmap_segments: list[HeatmapSegment] = []
    normal_candidates: list[Candidate] = []
    short_candidates: list[Candidate] = []
    candidate_generation_summary: dict[str, Any] | None = None
    scored_candidates: list[Candidate] = []
    selection: CandidateSelection | None = None
    openai_scoring_summary: dict[str, Any] | None = None
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

        settings = dict(job.settings_json or {})
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
                heatmap_summary, heatmap_mode_unavailable = _heatmap_summary_for_selection_mode(
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
                if heatmap_mode_unavailable:
                    raise PipelineExpectedError(
                        "heatmap_interval_mode_unavailable",
                        "JSON区間モードには有効な人気区間JSONが必要です。",
                        details=heatmap_summary,
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
                        len(correction_target_indices) if correction_target_indices is not None else len(transcript_segments)
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
                        target_segments_completed=(0 if correction_result.summary.get("fallback_used") else final_target_total),
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
                        heatmap_segments=heatmap_segments,
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
                            "strategy": "codex_initial_selection",
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
                    if manual_workflow or normal_manual_ranges
                    else generate_heatmap_candidates_with_summary(
                        "normal",
                        heatmap_segments=heatmap_segments,
                        transcript_segments=transcript_segments,
                        video_duration=duration,
                        requested_count=_int_setting(settings, "normalClipCount", 2),
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                    if heatmap_interval_mode
                    else generate_normal_candidates_with_summary(
                        transcript_segments,
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
                        heatmap_segments,
                    )
                )
                short_generation_result = (
                    CandidateGenerationResult(
                        candidates=codex_short_candidates,
                        summary={
                            "type": "short",
                            "strategy": "codex_initial_selection",
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
                    if manual_workflow or short_manual_ranges
                    else generate_heatmap_candidates_with_summary(
                        "short",
                        heatmap_segments=heatmap_segments,
                        transcript_segments=transcript_segments,
                        video_duration=duration,
                        requested_count=_int_setting(settings, "shortCount", 3),
                        settings=settings,
                        heartbeat=candidate_generation_heartbeat,
                    )
                    if heatmap_interval_mode
                    else generate_short_candidates_with_summary(
                        transcript_segments,
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
                        heatmap_segments,
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
            if manual_workflow:
                normal_candidates = apply_manual_clip_metadata(
                    normal_candidates,
                    settings,
                )
                short_candidates = apply_manual_clip_metadata(
                    short_candidates,
                    settings,
                )
            codex_selection = codex_initial_selection_result.selection if codex_initial_selection_result is not None else None
            if heatmap_interval_mode and _require_all_requested_heatmap_candidate_types(codex_selection):
                missing_candidate_types = [
                    candidate_type
                    for candidate_type, requested_count, manual_ranges, candidates in (
                        (
                            "normal",
                            _int_setting(settings, "normalClipCount", 2),
                            normal_manual_ranges,
                            normal_candidates,
                        ),
                        (
                            "short",
                            _int_setting(settings, "shortCount", 3),
                            short_manual_ranges,
                            short_candidates,
                        ),
                    )
                    if requested_count > 0 and not manual_ranges and not candidates
                ]
                if missing_candidate_types:
                    raise PipelineExpectedError(
                        "heatmap_interval_mode_no_candidates",
                        "人気区間JSONから設定時間と字幕条件を満たす候補を生成できませんでした。",
                        details={"candidateTypes": missing_candidate_types},
                    )
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
                    ("heatmap_interval_mode_no_candidates" if heatmap_interval_mode else "no_candidates_found"),
                    (
                        "人気区間JSONから設定時間と字幕条件を満たす候補を生成できませんでした。"
                        if heatmap_interval_mode
                        else "No clip candidates were found for the selected settings."
                    ),
                )

            manual_candidates = [
                *(normal_candidates if normal_manual_ranges else []),
                *(short_candidates if short_manual_ranges else []),
            ]
            automatic_candidates = [
                *(normal_candidates if not normal_manual_ranges else []),
                *(short_candidates if not short_manual_ranges else []),
            ]
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
                    heatmap_segments=heatmap_segments,
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
                automatic_selection, automatic_scored, openai_scoring_summary = _ensure_selected_candidates_openai_scored(
                    automatic_selection,
                    scoring_result.candidates,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    visual_quality=visual_quality,
                    scorer=scoring_result.openai_scorer,
                    openai_summary=openai_scoring_summary,
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
                        heatmap_segments=heatmap_segments,
                    )
                )
                scored_candidates = [*automatic_scored, *manual_candidates]
                selection = merge_manual_candidates_into_selection(
                    automatic_selection,
                    settings=settings,
                    manual_normal_candidates=(normal_candidates if normal_manual_ranges else []),
                    manual_short_candidates=(short_candidates if short_manual_ranges else []),
                )
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
            if automation_mode in {"shadow", "guarded"}:
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
                automation_mode == "guarded"
                and selection_gate is not None
                and selection_gate.route != "continue"
            )
            manual_clip_plan_review = bool(
                automation_mode != "guarded"
                and bool(settings.get("requireClipPlanReview", False))
                and bool(settings.get("requireSubtitleReview", False))
                and bool(settings.get("burnSubtitles", True))
            )
            if guarded_selection_needs_review or manual_clip_plan_review:
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

                if automation_mode in {"shadow", "guarded"}:
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
                    elif automation_mode == "guarded":
                        content_gate = unknown_quality_gate_decision(
                            job_id=job.id,
                            stage="content",
                            reason_code="content_gate_record_unavailable",
                            mode=automation_mode,
                        )

                summary_files = write_summaries()
                metadata_files.extend(path for path in summary_files if path not in metadata_files)
                guarded_content_auto_passed = bool(
                    automation_mode == "guarded"
                    and content_gate is not None
                    and content_gate.route == "continue"
                )
                if subtitle_review_requested and not guarded_content_auto_passed:
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
            if automation_mode in {"shadow", "guarded"}:
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
                elif automation_mode == "guarded":
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    raise PipelineExpectedError(
                        "quality_gate_record_failed",
                        "Guarded post-render quality decision could not be recorded.",
                    )
                if automation_mode == "guarded" and post_render_gate.route != "continue":
                    _discard_unpublished_exports(
                        db,
                        exports,
                        job_dir=job_dir,
                    )
                    raise PipelineExpectedError(
                        "quality_gate_render_failed",
                        "Guarded quality gate rejected incomplete rendered output.",
                        details={
                            "qualityGateStage": "post_render",
                            "qualityGateOutcome": post_render_gate.outcome,
                            "qualityGateInputHash": post_render_gate.input_hash,
                        },
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
                invalidate_quality_gate_decisions(job_dir, ("content",))
                try:
                    content_gate = evaluate_content_quality_gate(
                        job_id=job.id,
                        document=review_document,
                        settings=settings,
                        mode="guarded",
                    )
                except Exception as exc:
                    content_gate = unknown_quality_gate_decision(
                        job_id=job.id,
                        stage="content",
                        reason_code="content_gate_evaluation_failed",
                        evidence={"errorType": exc.__class__.__name__},
                        mode="guarded",
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
    overlapping = [(index, segment) for index, segment in enumerate(transcript_segments) if segment.end > start and segment.start < end]
    transcript_text = _transcript_text([segment for _, segment in overlapping])
    recommended_start = candidate.clip_plan_recommended_start if candidate.clip_plan_recommended_start is not None else candidate.start
    recommended_end = candidate.clip_plan_recommended_end if candidate.clip_plan_recommended_end is not None else candidate.end
    updated = candidate.model_dump()
    updated.update(
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "transcript_text": transcript_text,
            "segment_start_index": overlapping[0][0] if overlapping else None,
            "segment_end_index": overlapping[-1][0] + 1 if overlapping else None,
            "transcript_char_count": sum(len(segment.text.strip()) for _, segment in overlapping),
            "speech_seconds": round(
                sum(
                    max(
                        0.0,
                        min(float(segment.end), end) - max(float(segment.start), start),
                    )
                    for _, segment in overlapping
                    if segment.text.strip()
                ),
                3,
            ),
            "clip_plan_recommended_start": recommended_start,
            "clip_plan_recommended_end": recommended_end,
            "clip_plan_boundary_adjusted": not (abs(start - recommended_start) < 0.001 and abs(end - recommended_end) < 0.001),
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
        selected_payload = selected_path.read_bytes() if selected_path.is_file() else None
        preview_payload = preview_path.read_bytes() if preview_path.is_file() else None
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(_read_json_file(selected_path))
            transcript_segments = _read_transcript_segments(transcript_output_path(job_dir))
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

            source_duration = float(video.duration or document.source_duration or max((clip.end for clip in document.clips), default=0.0))
            if start < 0 or end <= start or end > source_duration + 0.001:
                raise ValueError("requested clip boundary is outside the source video")

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
            target_collection = selection.normal_clips if updated_candidate.type == "normal" else selection.shorts
            target_index = next(index for index, item in enumerate(target_collection) if item.id == clip_id)
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
            available_clip_ids = [clip.id for clip in document.clips if subtitle_review_preview_path(job_dir, clip.id).is_file()]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )
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
        selected_payload = selected_path.read_bytes() if selected_path.is_file() else None
        preview_payload = preview_path.read_bytes() if preview_path.is_file() else None
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(_read_json_file(selected_path))
            planned_clip = next(
                (clip for clip in document.clips if clip.id == clip_id),
                None,
            )
            if planned_clip is None:
                raise ValueError(f"clip plan item not found: {clip_id}")
            target_candidates = selection.shorts if planned_clip.type == "short" else selection.normal_clips
            candidate = next(
                (item for item in target_candidates if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected clip not found: {clip_id}")
            if (start is None) != (end is None):
                raise ValueError("hook scene requires both start and end")
            if start is not None and end is not None:
                hook_duration = end - start
                if not 0.5 <= hook_duration <= 3.0:
                    raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
                if start < candidate.start - 0.001 or end > candidate.end + 0.001:
                    raise ValueError("hook scene must stay within the selected clip")
                short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
                if candidate.type == "short" and hook_scene_newly_exceeds_short_limit(
                    clip_duration=candidate.duration,
                    hook_duration=hook_duration,
                    short_max_duration=short_max_duration,
                ):
                    raise ValueError("hook scene would exceed the configured short maximum duration")

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
            target_index = next(index for index, item in enumerate(target_candidates) if item.id == clip_id)
            target_candidates[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)

            update_clip_plan_hook_scene(
                document,
                clip_id,
                start=start,
                end=end,
            )
            available_clip_ids = [clip.id for clip in document.clips if subtitle_review_preview_path(job_dir, clip.id).is_file()]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )
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
                current_step=("冒頭フック映像の更新に失敗しました。時間を確認して再試行してください"),
            )
            raise

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
        if exact_subtitle_review_preview_is_ready(
            artifacts,
            spec_hash,
        ) and live_subtitle_review_preview_is_ready(live_artifacts, live_hash):
            return ["ready"]

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
    return ["ready"]


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
        previous_plan = load_clip_plan(previous_plan_path) if previous_plan_path.is_file() else None
        previous_artifact_paths = [
            job_dir / "normal_candidates.json",
            job_dir / "short_candidates.json",
            job_dir / "candidates.json",
            job_dir / "candidate_generation_summary.json",
            job_dir / "selected_clips.json",
            job_dir / "scored_candidates.json",
            job_dir / "openai_scoring_summary.json",
            job_dir / "candidate_summary.json",
            job_dir / "rejection_summary.json",
            job_dir / "selected_clips_summary.json",
            job_dir / "heatmap_validation_summary.json",
            quality_gate_decision_path(job_dir, "selection"),
            quality_gate_decision_path(job_dir, "content"),
            quality_gate_decision_path(job_dir, "post_render"),
        ]
        previous_artifacts = {path: path.read_bytes() if path.is_file() else None for path in previous_artifact_paths}

        try:
            _set_status(db, job, "reselecting_clips")
            visited_statuses.append("reselecting_clips")
            transcript_segments = _read_transcript_segments(transcript_output_path(job_dir))
            audio_features = AudioFeatures.model_validate(_read_json_file(job_dir / "audio_features.json"))
            silence_segments = [SilenceSegment.model_validate(item) for item in _read_json_file(job_dir / "silence_segments.json")]
            scene_segments = [SceneSegment.model_validate(item) for item in _read_json_file(job_dir / "scene_segments.json")]
            visual_quality = VisualQuality.model_validate(_read_json_file(job_dir / "visual_quality.json"))
            heatmap_result = load_heatmap_for_video(
                input_path,
                original_filename=video.original_filename,
                actual_duration=float(video.duration or visual_quality.duration),
                max_sidecar_size_bytes=get_settings().max_heatmap_sidecar_size_bytes,
                sidecar_path=storage_paths.resolve_video_heatmap(
                    video.id,
                    video.stored_path,
                ),
            )
            heatmap_summary, heatmap_mode_unavailable = _heatmap_summary_for_selection_mode(
                heatmap_result.summary,
                heatmap_result.segments,
                settings,
                video_duration=float(video.duration or visual_quality.duration),
            )
            _write_json(
                job_dir / "heatmap_validation_summary.json",
                heatmap_summary,
            )
            if heatmap_mode_unavailable:
                raise PipelineExpectedError(
                    "heatmap_interval_mode_unavailable",
                    "JSON区間モードには有効な人気区間JSONが必要です。",
                    details=heatmap_summary,
                )
            normal_manual_ranges = manual_ranges_for_type(settings, "normal")
            short_manual_ranges = manual_ranges_for_type(settings, "short")
            automatic_settings = automatic_selection_settings(
                settings,
                manual_normal=bool(normal_manual_ranges),
                manual_short=bool(short_manual_ranges),
            )
            previous_settings = dict(previous_plan.settings) if previous_plan is not None else {}
            previous_heatmap_interval_mode = _bool_setting(
                previous_settings,
                "heatmapIntervalMode",
                False,
            )
            heatmap_interval_mode = _bool_setting(
                settings,
                "heatmapIntervalMode",
                False,
            )
            heatmap_interval_mode_changed = heatmap_interval_mode != previous_heatmap_interval_mode

            if heatmap_interval_mode_changed:
                candidate_generation_summary_path = job_dir / "candidate_generation_summary.json"

                def candidate_generation_heartbeat(summary: dict[str, Any]) -> None:
                    _write_json(candidate_generation_summary_path, summary)
                    _heartbeat_job(db, job)

                try:
                    (
                        normal_candidates,
                        short_candidates,
                        candidate_generation_summary,
                    ) = _generate_candidates_for_reselection_mode(
                        settings=settings,
                        transcript_segments=transcript_segments,
                        scene_segments=scene_segments,
                        silence_segments=silence_segments,
                        heatmap_segments=heatmap_result.segments,
                        video_duration=float(video.duration or visual_quality.duration),
                        heartbeat=candidate_generation_heartbeat,
                    )
                except CandidateGenerationMemoryLimitError as exc:
                    _write_json(candidate_generation_summary_path, exc.summary)
                    raise PipelineExpectedError(
                        "candidate_generation_memory_limit",
                        "Candidate generation exceeded the configured memory limit.",
                        details=exc.summary,
                    ) from exc
                except PipelineExpectedError:
                    raise
                except Exception as exc:
                    raise PipelineExpectedError(
                        "candidate_generation_failed",
                        f"Could not generate clip candidates: {exc}",
                    ) from exc

                write_candidates(
                    normal_candidates,
                    job_dir / "normal_candidates.json",
                )
                write_candidates(
                    short_candidates,
                    job_dir / "short_candidates.json",
                )
                write_candidates(
                    [*normal_candidates, *short_candidates],
                    job_dir / "candidates.json",
                )
                _write_json(
                    candidate_generation_summary_path,
                    candidate_generation_summary,
                )
            else:
                base_candidates = _read_model_list(
                    job_dir / "candidates.json",
                    Candidate,
                )
                if not base_candidates:
                    raise PipelineExpectedError(
                        "clip_plan_candidates_missing",
                        "Saved clip candidates are unavailable for reselection.",
                    )
                normal_candidates = (
                    build_manual_candidates(
                        "normal",
                        normal_manual_ranges,
                        transcript_segments,
                    ).candidates
                    if normal_manual_ranges
                    else [candidate for candidate in base_candidates if candidate.type == "normal"]
                )
                short_candidates = (
                    build_manual_candidates(
                        "short",
                        short_manual_ranges,
                        transcript_segments,
                    ).candidates
                    if short_manual_ranges
                    else [candidate for candidate in base_candidates if candidate.type == "short"]
                )
                normal_candidates = annotate_candidates_with_heatmap(
                    normal_candidates,
                    heatmap_result.segments,
                )
                short_candidates = annotate_candidates_with_heatmap(
                    short_candidates,
                    heatmap_result.segments,
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
            automatic_selection, automatic_scored, openai_scoring_summary = _ensure_selected_candidates_openai_scored(
                automatic_selection,
                scoring_result.candidates,
                settings=automatic_settings,
                audio_features=audio_features,
                visual_quality=visual_quality,
                scorer=scoring_result.openai_scorer,
                openai_summary=scoring_result.openai_summary,
            )
            automatic_selection, automatic_scored, _ = (
                _automatic_selection_with_diverse_refined_shorts(
                    automatic_scored,
                    transcript_segments=transcript_segments,
                    silence_segments=silence_segments,
                    scene_segments=scene_segments,
                    settings=automatic_settings,
                    timeline_duration=float(video.duration or visual_quality.duration),
                    audio_features=audio_features,
                    heatmap_segments=heatmap_result.segments,
                )
            )
            scored_candidates = [*automatic_scored, *manual_candidates]
            selection = merge_manual_candidates_into_selection(
                automatic_selection,
                settings=settings,
                manual_normal_candidates=(normal_candidates if normal_manual_ranges else []),
                manual_short_candidates=(short_candidates if short_manual_ranges else []),
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
            quality_gate_mode = _active_quality_gate_mode(job_dir, settings)
            if quality_gate_mode is None:
                invalidate_quality_gate_decisions(
                    job_dir,
                    ("selection", "content", "post_render"),
                )
            else:
                _evaluate_selection_quality_gate_for_mode(
                    job_id=job.id,
                    job_dir=job_dir,
                    selection=selection,
                    transcript_segments=transcript_segments,
                    settings=settings,
                    source_duration=float(
                        video.duration or visual_quality.duration
                    ),
                    mode=quality_gate_mode,
                )

            openai_summary_path = job_dir / "openai_scoring_summary.json"
            if openai_scoring_summary is None:
                openai_summary_path.unlink(missing_ok=True)
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
                openai_scoring_summary=openai_scoring_summary,
                transcription_engine=str(transcript_summary.get("transcription_engine", "not_run")),
                used_fixture_transcript=bool(transcript_summary.get("used_fixture_transcript", False)),
                transcription_model=transcript_summary.get("transcription_model"),
                transcription_language=transcript_summary.get("transcription_language"),
                transcription_diagnostics=transcript_summary.get("transcription_runtime"),
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
            visited_statuses.extend(["preparing_clip_review", "awaiting_clip_review"])
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
                try:
                    content_gate = evaluate_content_quality_gate(
                        job_id=job.id,
                        document=review_document,
                        settings=settings,
                        mode=effective_automation_mode,
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
                guarded_content_blocked = (
                    effective_automation_mode == "guarded"
                    and (
                        content_gate_path is None
                        or content_gate.route != "continue"
                    )
                )
                if guarded_content_blocked:
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
                            "Guarded content quality decision could not be recorded."
                            if content_gate_path is None
                            else "Guarded content quality checks require subtitle review."
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
                    post_render_gate_path is None
                    and effective_automation_mode == "guarded"
                ):
                    raise PipelineExpectedError(
                        "quality_gate_record_failed",
                        "Guarded post-render quality decision could not be recorded.",
                    )
                if (
                    effective_automation_mode == "guarded"
                    and post_render_gate.route != "continue"
                ):
                    raise PipelineExpectedError(
                        "quality_gate_render_failed",
                        "Guarded quality gate rejected incomplete rendered output.",
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
            openai_summary_path = job_dir / "openai_scoring_summary.json"
            openai_scoring_summary = _read_json_file(openai_summary_path) if openai_summary_path.is_file() else None
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
            write_youtube_posting_artifacts(review_document.clips, job_dir)
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
