from app.clip_allocation import is_ai_allocation, candidate_pool_counts
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.duration_rules import duration_search_settings
from sqlalchemy.orm import Session
from app.candidates.user_rejections import REJECTED_RANGES_SETTING, user_rejection_reason, near_previous_except_context_expansion
from app.audio.extract import extract_mono_wav
from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine,
    TranscriptSegment,
)
from app.audio.volume_features import (
    AudioFeatures,
    compute_audio_features,
)
from app.candidates.boundary_refinement import refine_selected_candidates
from app.candidates.codex_initial_selection import (
    request_codex_initial_selection,
)
from app.candidates.manual_ranges import (
    MANUAL_SELECTION_REASON,
)
from app.candidates.merge_boundaries import (
    Candidate,
)
from app.candidates.select_candidates import (
    CandidateRejection,
    CandidateSelection,
    partition_candidates_by_duration,
)
from app.candidates.title_fallback import titled_candidates
from app.jobs.clip_plan import (
    build_clip_plan,
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_awaiting_review,
    write_clip_plan,
)
from app.jobs.automation import (
    automation_manifest_path,
    load_automation_manifest,
)
from app.jobs.quality_gate import (
    QualityGateDecision,
    QualityGateMode,
    evaluate_selection_quality_gate,
    invalidate_quality_gate_decisions,
    quality_gate_decision_path,
    unknown_quality_gate_decision,
    write_quality_gate_decision,
)
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    subtitle_review_preview_path,
)
from app.jobs.title_hook_suggestions import (
    TitleHookSuggestionsDocument,
    generate_title_hook_suggestions_for_auto,
)
from app.models import Job, Video, utc_now
from app.candidates.used_ranges import (
    overlaps_used,
    used_ranges,
)
from app.source_clip_history import (
    SourceTimelineChanged,
    record_completed_exports,
    selection_history_settings,
)
from app.render.render_normal import render_normal_clip
from app.render.render_exact_review_preview import (
    ExactPreviewResult,
    render_exact_subtitle_review_preview,
)
from app.render.render_manual_source_proxy import (
    render_manual_source_proxy,
)
from app.render.render_review_preview import render_review_preview
from app.render.render_short import render_short_clip
from app.render.render_thumbnail import (
    ThumbnailRenderResult,
    render_normal_thumbnail,
    render_short_thumbnail,
)
from app.scoring.clip_preferences import build_clip_selection_preferences
from app.scoring.heatmap import annotate_candidates_with_heatmap
from app.scoring.rule_score import score_candidates
from app.storage.paths import StoragePaths
from app.video.black_screen import (
    BlackScreenSegment,
    detect_black_screen,
)
from app.video.heatmap import HeatmapSegment
from app.video.probe import VideoMetadata, probe_metadata
from app.video.scene_detect import SceneSegment
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
    normal_thumbnail_renderer: Callable[..., ThumbnailRenderResult] = render_normal_thumbnail
    short_thumbnail_renderer: Callable[..., ThumbnailRenderResult] = render_short_thumbnail
    manual_source_proxy_renderer: Callable[..., Path] = render_manual_source_proxy
    subtitle_review_preview_renderer: Callable[..., Path] = render_review_preview
    subtitle_review_exact_preview_renderer: Callable[..., ExactPreviewResult] = render_exact_subtitle_review_preview
    codex_initial_selector: Callable[..., Any] = request_codex_initial_selection
    auto_title_hook_generator: Callable[..., TitleHookSuggestionsDocument] = (
        generate_title_hook_suggestions_for_auto
    )

class PipelineExpectedError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

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
        "content_with_heatmap_reference"
        if interval_mode_applied
        else "manual_ranges"
        if requested and not automatic_output
        else "content_only"
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
    reference_unavailable = requested and automatic_output and not available
    if reference_unavailable:
        updated["interval_mode_unavailable_reason"] = summary.get("fallback_reason") or (
            "heatmap_has_no_positive_segments_in_video" if positive_segments > 0 else "heatmap_has_no_positive_segments"
        )
    return updated, False

def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)

def _codex_initial_selection_enabled(
    settings: dict[str, Any],
    *,
    manual_workflow: bool,
    has_manual_ranges: bool,
) -> bool:
    provider = str(settings.get("initialSelectionProvider") or "legacy").strip().lower()
    return (provider == "codex" and not manual_workflow
            and (not has_manual_ranges or is_ai_allocation(settings))
            and (not is_ai_allocation(settings) or any(candidate_pool_counts(settings))))

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
    if status == "completed":
        record_completed_exports(db, job)
    db.commit()
    db.refresh(job)

def _settings_with_source_history(
    db: Session, job: Job, video: Video, paths: StoragePaths
) -> dict[str, Any]:
    try:
        settings, summary = selection_history_settings(db, job, video, paths)
    except SourceTimelineChanged as exc:
        raise PipelineExpectedError("source_history_timeline_changed", str(exc)) from exc
    _write_json(paths.job_outputs(job.id) / "source_clip_history_summary.json", summary)
    return duration_search_settings(settings)

def _unused_candidates(candidates: Sequence[Candidate], settings: dict[str, Any]) -> list[Candidate]:
    ranges = used_ranges(settings)
    return [
        candidate for candidate in candidates
        if candidate.selection_reason == MANUAL_SELECTION_REASON
        or user_rejection_reason(candidate.start, candidate.end, candidate.type, settings) is not None
        or (not overlaps_used(candidate.start, candidate.end, ranges)
            and not overlaps_used(candidate.start, candidate.end, settings.get('_allocationKeptRanges', {}).get(candidate.type, []))
             and not (is_ai_allocation(settings) and overlaps_used(candidate.start, candidate.end, [
                 (r['startSeconds'], r['endSeconds']) for r in settings.get(
                     'normalClipTimeRanges' if candidate.type == 'normal' else 'shortClipTimeRanges', [])])))
    ]

def _is_repeated_normal_proposal(candidate: Candidate, settings: dict[str, Any]) -> bool:
    return (
        candidate.type == "normal"
        and candidate.selection_reason != MANUAL_SELECTION_REASON
        and not _bool_setting(settings, "excludePreviousSelection", False)
        and user_rejection_reason(candidate.start, candidate.end, candidate.type, settings) is None
        and near_previous_except_context_expansion(candidate.start, candidate.end, candidate.type, settings)
    )

def _filter_user_rejections(
    selection: CandidateSelection, candidates: Sequence[Candidate], settings: dict[str, Any],
) -> tuple[CandidateSelection, list[Candidate]]:
    if not settings.get(REJECTED_RANGES_SETTING):
        return selection, list(candidates)
    rejected = [CandidateRejection(candidateId=candidate.id, type=candidate.type, reasons=[reason])
                for candidate in candidates
                if (reason := user_rejection_reason(candidate.start, candidate.end, candidate.type, settings))
                and not (candidate.selection_reason == MANUAL_SELECTION_REASON
                         and reason in {"rejected_by_user_other", "rejected_by_user_unspecified"})]
    rejected_ids = {item.candidate_id for item in rejected}
    normal = [candidate for candidate in selection.normal_clips if candidate.id not in rejected_ids]
    shorts = [candidate for candidate in selection.shorts if candidate.id not in rejected_ids]
    return selection.model_copy(update={
        "normal_clips": normal, "shorts": shorts,
        "rejected_candidates": [*selection.rejected_candidates, *rejected],
        "unfilled_requested_counts": {
            "normal": max(0, selection.requested_normal_count - len(normal)),
            "short": max(0, selection.requested_short_count - len(shorts)),
        },
    }), [candidate for candidate in candidates if candidate.id not in rejected_ids]


def _filter_selection_history(
    selection: CandidateSelection, candidates: list[Candidate], settings: dict[str, Any]
) -> tuple[CandidateSelection, list[Candidate]]:
    if not used_ranges(settings) and not settings.get('_allocationKeptRanges') and not (
        is_ai_allocation(settings) and (settings.get('normalClipTimeRanges') or settings.get('shortClipTimeRanges'))
    ):
        return selection, candidates
    kept = _unused_candidates(candidates, settings)
    kept_ids = {candidate.id for candidate in kept}
    normal = _unused_candidates(selection.normal_clips, settings)
    shorts = _unused_candidates(selection.shorts, settings)
    rejected = [
        CandidateRejection(candidateId=candidate.id, type=candidate.type, reasons=["previous_source_usage"])
        for candidate in candidates if candidate.id not in kept_ids
    ]
    return selection.model_copy(update={
        "normal_clips": normal,
        "shorts": shorts,
        "rejected_candidates": [*selection.rejected_candidates, *rejected],
        "unfilled_requested_counts": {
            "normal": max(0, selection.requested_normal_count - len(normal)),
            "short": max(0, selection.requested_short_count - len(shorts)),
        },
    }), kept

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
            return effective_mode if effective_mode in {"shadow", "guarded", "auto"} else None
    return requested_mode if requested_mode in {"shadow", "guarded", "auto"} else None

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
    if decision_path is None and mode in {"guarded", "auto"}:
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

def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path

def _transcript_text(segments: Sequence[TranscriptSegment]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

def _replace_scored_candidates(
    candidates: Sequence[Candidate],
    replacements: dict[str, Candidate],
) -> list[Candidate]:
    return [replacements.get(candidate.id, candidate) for candidate in candidates]

def _score_local_candidates(
    candidates: Sequence[Candidate], settings: dict[str, Any],
    audio_features: AudioFeatures, silence_segments: Sequence[SilenceSegment],
    transcript_segments: Sequence[TranscriptSegment] = (),
) -> list[Candidate]:
    scored = score_candidates(
        candidates, audio_features=audio_features, silence_segments=silence_segments,
        selection_preferences=build_clip_selection_preferences(settings),
        transcript_segments=transcript_segments,
    )
    return [candidate.model_copy(update={"final_score": candidate.rule_score}) for candidate in scored]

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
    selection, scored_candidates = _filter_user_rejections(selection, scored_candidates, settings)
    scored_candidates, duration_rejections = partition_candidates_by_duration(scored_candidates, settings)
    valid_ids = {candidate.id for candidate in scored_candidates}
    selection = selection.model_copy(update={
        "normal_clips": [candidate for candidate in selection.normal_clips if candidate.id in valid_ids],
        "shorts": [candidate for candidate in selection.shorts if candidate.id in valid_ids],
        "rejected_candidates": [*selection.rejected_candidates, *duration_rejections],
    })
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
    selection, candidates = _filter_user_rejections(
        selection.model_copy(update={"normal_clips": normal_clips, "shorts": shorts}),
        _replace_scored_candidates(scored_candidates, replacements), settings,
    )
    selection, candidates = _filter_selection_history(selection, candidates, settings)
    candidates, duration_rejections = partition_candidates_by_duration(candidates, settings)
    valid_ids = {candidate.id for candidate in candidates}
    normals = [candidate for candidate in selection.normal_clips if candidate.id in valid_ids]
    shorts = [candidate for candidate in selection.shorts if candidate.id in valid_ids]
    return selection.model_copy(update={
        "normal_clips": normals, "shorts": shorts,
        "rejected_candidates": [*selection.rejected_candidates, *duration_rejections],
        "unfilled_requested_counts": {
            "normal": max(0, selection.requested_normal_count - len(normals)),
            "short": max(0, selection.requested_short_count - len(shorts)),
        },
    }), candidates

def _read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _read_transcript_segments(path: Path) -> list[TranscriptSegment]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = _read_json_file(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a list in {path.name}")
    return [TranscriptSegment.model_validate(item) for item in payload]

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
    kept_plan: Any = None,
) -> Path:
    selected = [*selection.normal_clips, *selection.shorts]
    if not selected:
        if settings.get("_reselectionExcludedRanges"):
            raise PipelineExpectedError(
                "reselection_no_alternatives",
                "これまでの候補以外に条件を満たす場面が見つかりませんでした。前の候補を保持しています。狙う場面や長さを変えるか、候補を避ける設定をOFFにしてください。",
            )
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
    if kept_plan is not None:
        kept_ids = set(settings.get("keptClipIds", []))
        kept_by_id = {clip.id: clip for clip in kept_plan.clips if clip.id in kept_ids}
        document.clips = [kept_by_id[clip.id].model_copy(deep=True) if clip.id in kept_by_id else clip
                          for clip in document.clips]
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
