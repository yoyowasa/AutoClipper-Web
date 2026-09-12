import hashlib
import json
import mimetypes
from app.short_banners import banner_asset_path, resolve_banner_path
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audio.openai_transcript_correction import TRANSCRIPT_CORRECTION_PROGRESS_FILENAME
from app.audio.transcribe_faster_whisper import (
    TranscriptSegment,
    transcript_output_path,
    write_transcript_segments,
)
from app.audio.transcript_postprocess import repair_known_transcript_artifact_segments
from app.candidates.merge_boundaries import Candidate, write_candidates
from app.candidates.select_candidates import (
    CandidateSelection,
    convert_selected_clip_to_normal,
    write_selected_clips,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.ids import make_id
from app.jobs.automation import (
    AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING,
    automation_manifest_path,
    load_automation_manifest,
)
from app.jobs.quality_gate import (
    QualityGateDecision,
    QualityGateMode,
    QualityGateStage,
    evaluate_content_quality_gate,
    invalidate_quality_gate_decisions,
    load_quality_gate_decision,
    quality_gate_decision_path,
    unknown_quality_gate_decision,
    write_quality_gate_decision,
)
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.clip_plan import (
    ClipPlanClip,
    ClipPlanDocument,
    clip_plan_output_path,
    convert_clip_plan_clip_to_normal,
    load_clip_plan,
    mark_clip_plan_approved,
    update_clip_plan_boundary,
    update_clip_plan_hook_scene as update_clip_plan_hook_scene_document,
    write_clip_plan,
)
from app.jobs.hook_scene import hook_scene_newly_exceeds_short_limit
from app.jobs.manual_workflow import (
    is_manual_workflow,
    manual_plan_settings,
    touch_manual_document,
    validate_manual_clip_counts,
)
from app.jobs.reedit_upload import (
    UploadSizeLimitExceeded,
    fingerprint_stream,
    matching_exports,
)
from app.jobs.queue import (
    ClipPlanBoundaryUpdateEnqueue,
    ClipPlanHookSceneUpdateEnqueue,
    ClipPlanReselectionEnqueue,
    JobEnqueue,
    RenderEnqueue,
    RetryJobEnqueue,
    SubtitleReviewHookSceneUpdateEnqueue,
    SubtitleReviewPreviewEnqueue,
    TitleHookSuggestionsEnqueue,
    get_enqueue_clip_plan_boundary_update,
    get_enqueue_clip_plan_hook_scene_update,
    get_enqueue_clip_plan_reselection,
    get_enqueue_job,
    get_enqueue_render_job,
    get_enqueue_retry_job,
    get_enqueue_subtitle_review_hook_scene_update,
    get_enqueue_subtitle_review_preview,
    get_enqueue_title_hook_suggestions,
)
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    apply_reviewed_clip_content,
    build_subtitle_review,
    confirm_review_clip,
    convert_review_clip_to_short,
    load_subtitle_review,
    queue_auto_review_render,
    queue_review_render,
    refresh_review_render_contract,
    reopen_completed_review,
    subtitle_review_output_path,
    subtitle_review_preview_path,
    subtitle_review_summary_path,
    update_review_clip_content,
    update_review_clip_framing,
    update_review_hook_scene,
    update_review_render_settings,
    update_review_segment,
    write_subtitle_review,
    write_subtitle_review_summary,
)
from app.jobs.subtitle_review_preview import (
    current_subtitle_review_preview_spec,
    exact_subtitle_review_preview_is_ready,
    exact_subtitle_review_preview_error_path,
    live_subtitle_review_preview_is_ready,
    refresh_subtitle_review_preview_states,
    subtitle_review_document_lock,
)
from app.jobs.title_hook_suggestions import (
    TitleHookDraftSegment,
    TitleHookSuggestionsDocument,
    build_title_hook_suggestion_input,
    failed_title_hook_suggestions,
    load_title_hook_suggestion_input,
    load_title_hook_suggestions,
    queued_title_hook_suggestions,
    title_hook_suggestion_input_path,
    title_hook_suggestions_path,
    write_title_hook_suggestion_input,
    write_title_hook_suggestions,
)
from app.posting_metadata import (
    build_post_metadata_revision_hash,
    build_youtube_posting_copy,
)
from app.models import ExportItem, Job, Video
from app.models import utc_now
from app.render.render_exact_review_preview import (
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
)
from app.render.render_manual_source_proxy import manual_source_proxy_path
from app.render.render_short import (
    DEFAULT_SHORT_BOTTOM_BANNER_PATH,
    DEFAULT_SHORT_TOP_BANNER_PATH,
)
from app.schemas import (
    ClipPlanActionResponse,
    ClipPlanBoundaryUpdateRequest,
    ClipPlanHookSceneUpdateRequest,
    ClipPlanReselectionRequest,
    ClipPlanTypeUpdateRequest,
    CompletedVideoReeditResponse,
    JobAuditSummary,
    JobCreateRequest,
    JobCreateResponse,
    JobError,
    JobResultsResponse,
    JobSettings,
    JobStatusResponse,
    ManualClipCreateRequest,
    ManualClipUpdateRequest,
    ResultExportItem,
    ShortLayout,
    ShortOverlayTitleMode,
    SubtitleReviewFinalizeResponse,
    SubtitleReviewClipApplyRequest,
    SubtitleReviewClipContentUpdateRequest,
    SubtitleReviewClipFramingUpdateRequest,
    SubtitleReviewConvertToShortRequest,
    SubtitleReviewSettingsUpdateRequest,
    SubtitleReviewSegmentUpdateRequest,
    TitleHookSuggestionRequest,
)
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.heatmap import HeatmapSidecarError, parse_heatmap_sidecar


router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL_STATUSES = {"completed", "failed"}
NON_WORKER_STATUSES = {
    "uploaded",
    "queued",
    "awaiting_manual_edit",
    "awaiting_clip_review",
    "awaiting_subtitle_review",
}
DEFAULT_STALE_WORKER_SECONDS = 1800
RETRY_ENQUEUE_PENDING_STEP = "再処理を開始待ち"
NO_USABLE_SELECTION_ERROR_CODE = "no_usable_selection"
NO_USABLE_SELECTION_RETRY_EXHAUSTED_ERROR_CODE = "no_usable_selection_retry_exhausted"
LEGACY_NO_USABLE_OUTPUT_ERROR_CODE = "no_usable_output"
RETRY_SOURCE_SETTING_KEY = "retryOf"


def _validated_persisted_job_settings(
    settings: dict[str, Any] | None,
) -> JobSettings:
    payload = dict(settings or {})
    payload.setdefault("shortTopBannerEnabled", False)
    payload.setdefault("shortBottomBannerEnabled", False)
    payload.setdefault("shortSubtitleYPercent", None)
    return JobSettings.model_validate(payload)


def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


def _get_subtitle_review_or_404(job_id: str, paths: StoragePaths) -> SubtitleReviewDocument:
    review_path = subtitle_review_output_path(paths.job_outputs(job_id))
    if not review_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subtitle review not found")
    try:
        return load_subtitle_review(review_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="subtitle review artifact is invalid",
        ) from exc


def _get_title_hook_suggestions_or_404(
    job_id: str,
    clip_id: str,
    paths: StoragePaths,
) -> TitleHookSuggestionsDocument:
    artifact_path = title_hook_suggestions_path(paths.job_outputs(job_id), clip_id)
    if not artifact_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="title/hook suggestions not found",
        )
    try:
        return load_title_hook_suggestions(artifact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="title/hook suggestions artifact is invalid",
        ) from exc


def _get_clip_plan_or_404(
    job_id: str,
    paths: StoragePaths,
) -> ClipPlanDocument:
    plan_path = clip_plan_output_path(paths.job_outputs(job_id))
    if not plan_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan not found",
        )
    try:
        return load_clip_plan(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="clip plan artifact is invalid",
        ) from exc


def _get_manual_edit_context(
    db: Session,
    job_id: str,
    paths: StoragePaths,
) -> tuple[Job, Video, ClipPlanDocument]:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_manual_edit" or not is_manual_workflow(
        dict(job.settings_json or {})
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manual clip plan is not editable",
        )
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="video not found",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.state != "manual_editing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manual clip plan is not editable",
        )
    return job, video, document


def _validate_manual_clip_range(
    video: Video,
    document: ClipPlanDocument,
    *,
    start: float,
    end: float,
) -> None:
    if end <= start or end - start < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="manual clip duration must be at least 1 second",
        )
    source_duration = float(video.duration or document.source_duration or 0)
    if source_duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video duration is unavailable",
        )
    if end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )

def _write_subtitle_review_unlocked(
    document: SubtitleReviewDocument,
    paths: StoragePaths,
) -> None:
    output_dir = paths.job_outputs(document.job_id)
    invalidate_quality_gate_decisions(output_dir, ("content", "post_render"))
    write_subtitle_review(document, subtitle_review_output_path(output_dir))
    write_subtitle_review_summary(document, subtitle_review_summary_path(output_dir))


def _persist_subtitle_review(document: SubtitleReviewDocument, paths: StoragePaths) -> None:
    output_dir = paths.job_outputs(document.job_id)
    with subtitle_review_document_lock(output_dir):
        _write_subtitle_review_unlocked(document, paths)


def _refresh_subtitle_review_previews_unlocked(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_ids: set[str] | None = None,
) -> tuple[SubtitleReviewDocument, list[tuple[str, str]]]:
    document, queued, changed = refresh_subtitle_review_preview_states(
        job=job,
        video=video,
        document=document,
        paths=paths,
        clip_ids=clip_ids,
    )
    if changed:
        _write_subtitle_review_unlocked(document, paths)
    return document, queued


def _enqueue_subtitle_review_previews(
    *,
    job_id: str,
    document: SubtitleReviewDocument,
    queued: list[tuple[str, str]],
    paths: StoragePaths,
    enqueue_preview: SubtitleReviewPreviewEnqueue,
) -> SubtitleReviewDocument:
    enqueue_failures: list[tuple[str, str]] = []
    for clip_id, spec_hash in queued:
        try:
            enqueue_preview(job_id, clip_id, spec_hash)
        except Exception:
            enqueue_failures.append((clip_id, spec_hash))
    if not enqueue_failures:
        return document

    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        latest = _get_subtitle_review_or_404(job_id, paths)
        changed = False
        for clip_id, spec_hash in enqueue_failures:
            clip = next((item for item in latest.clips if item.id == clip_id), None)
            if clip is None or clip.preview_spec_hash != spec_hash:
                continue
            clip.preview_state = "failed"
            clip.preview_video_url = None
            clip.preview_error = "could not queue preview rendering"
            clip.confirmed = False
            changed = True
        if changed:
            latest.confirmed_clip_count = sum(1 for clip in latest.clips if clip.confirmed)
            _write_subtitle_review_unlocked(latest, paths)
        return latest


def _legacy_subtitle_review_preview_is_available(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _hydrate_legacy_subtitle_review_preview_urls(
    document: SubtitleReviewDocument,
    paths: StoragePaths,
) -> SubtitleReviewDocument:
    hydrated = document.model_copy(deep=True)
    output_dir = paths.job_outputs(document.job_id)
    for clip in hydrated.clips:
        if clip.preview_spec_hash is not None:
            continue
        legacy_path = subtitle_review_preview_path(output_dir, clip.id)
        if not _legacy_subtitle_review_preview_is_available(legacy_path):
            continue
        clip.preview_state = "ready"
        clip.preview_video_url = f"/api/jobs/{document.job_id}/subtitle-review/clips/{clip.id}/preview-video"
        clip.preview_error = None
    return hydrated


def _short_overlay_title_mode(settings: dict[str, Any]) -> ShortOverlayTitleMode:
    value = settings.get("shortOverlayTitleMode", "auto")
    if value == "auto":
        return "auto"
    if value == "always":
        return "always"
    if value == "high_quality_only":
        return "high_quality_only"
    if value == "never":
        return "never"
    return "auto"


def _short_layout(settings: dict[str, Any]) -> ShortLayout:
    value = settings.get("shortLayout", "auto")
    if value == "face_tracking_crop":
        return "face_tracking_crop"
    if value == "center_crop":
        return "center_crop"
    if value == "blur_background":
        return "blur_background"
    return "auto"


def _hydrate_subtitle_review_render_settings(
    document: SubtitleReviewDocument,
    job: Job,
    video: Video,
) -> tuple[SubtitleReviewDocument, bool]:
    settings = dict(job.settings_json or {})
    render_mode = str(settings.get("mode", "high_quality"))
    short_overlay_title_mode = _short_overlay_title_mode(settings)
    short_layout = _short_layout(settings)
    short_top_banner_enabled = bool(settings.get("shortTopBannerEnabled", False))
    short_bottom_banner_enabled = bool(settings.get("shortBottomBannerEnabled", False))
    policy_changed = (
        document.short_overlay_title_mode != short_overlay_title_mode
        or document.short_layout != short_layout
        or document.short_top_banner_enabled != short_top_banner_enabled
        or document.short_bottom_banner_enabled != short_bottom_banner_enabled
    )
    document.short_overlay_title_mode = short_overlay_title_mode
    document.short_layout = short_layout
    document.short_top_banner_enabled = short_top_banner_enabled
    document.short_bottom_banner_enabled = short_bottom_banner_enabled
    document, contract_changed = refresh_review_render_contract(
        document,
        render_mode=render_mode,
        render_settings=settings,
        source_width=video.width,
        source_height=video.height,
    )
    return document, policy_changed or contract_changed


def _reedit_artifacts_available(
    job_id: str,
    video: Video,
    paths: StoragePaths,
) -> bool:
    output_dir = paths.job_outputs(job_id)
    required_artifacts = (
        subtitle_review_output_path(output_dir),
        output_dir / "selected_clips.json",
        output_dir / "transcript_segments.json",
    )
    return all(path.is_file() for path in required_artifacts) and paths.resolve_stored_file(video.stored_path).is_file()


def _can_reopen_subtitle_review(
    job: Job,
    video: Video,
    paths: StoragePaths,
) -> bool:
    return job.status == "completed" and _reedit_artifacts_available(job.id, video, paths)


def _reopen_job_subtitle_review(
    job: Job,
    video: Video,
    paths: StoragePaths,
) -> SubtitleReviewDocument:
    output_dir = paths.job_outputs(job.id)
    with subtitle_review_document_lock(output_dir):
        document = _get_subtitle_review_or_404(job.id, paths)
        document.short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
        document, _settings_changed = _hydrate_subtitle_review_render_settings(
            document,
            job,
            video,
        )
        if job.status == "awaiting_subtitle_review" and document.state == "awaiting_review":
            if not _reedit_artifacts_available(job.id, video, paths):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="source artifacts are unavailable",
                )
            _write_subtitle_review_unlocked(document, paths)
            return document
        if not _can_reopen_subtitle_review(job, video, paths):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("completed job cannot be reopened because source artifacts are unavailable"),
            )
        try:
            document = reopen_completed_review(document)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        _write_subtitle_review_unlocked(document, paths)
        job.status = "awaiting_subtitle_review"
        job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
        job.error_code = None
        job.error_message = None
        job.updated_at = utc_now()
        return document


def _selected_clips_by_candidate(output_dir: Path) -> dict[str, dict[str, Any]]:
    selected = _read_json_if_exists(output_dir / "selected_clips.json")
    if not isinstance(selected, dict):
        return {}

    by_candidate: dict[str, dict[str, Any]] = {}
    for key in ("normalClips", "shorts"):
        values = selected.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("id") or item.get("candidate_id")
            if isinstance(candidate_id, str) and candidate_id:
                by_candidate[candidate_id] = item
    return by_candidate


def _export_is_published(
    export: ExportItem,
    output_dir: Path,
    paths: StoragePaths,
) -> bool:
    try:
        paths.resolve_stored_file(export.video_path).resolve(strict=False).relative_to(
            output_dir.resolve(strict=False)
        )
    except (OSError, ValueError):
        return False
    return True


def _job_publication_unresolved(job: Job, paths: StoragePaths) -> bool:
    return job.status in {
        "rendering_normal_clips",
        "rendering_shorts",
        "packaging_zip",
    } or job.error_code in {
        "subtitle_rerender_rollback_failed",
        "worker_terminated_unexpectedly",
    } or rerender_publication_is_unresolved(paths.job_outputs(job.id))


def _read_export_metadata(export: ExportItem, paths: StoragePaths) -> dict[str, Any]:
    if not export.metadata_path:
        return {}
    metadata = _read_json_if_exists(paths.resolve_stored_file(export.metadata_path))
    return metadata if isinstance(metadata, dict) else {}


def _audit_report(output_dir: Path) -> dict[str, Any] | None:
    report = _read_json_if_exists(output_dir / "audit" / "output_audit_report.json")
    return report if isinstance(report, dict) else None


def _audit_clips_by_candidate(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    clips = report.get("clips") if isinstance(report, dict) else None
    if not isinstance(clips, list):
        return {}
    by_candidate: dict[str, dict[str, Any]] = {}
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        candidate_id = clip.get("id") or clip.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id:
            by_candidate[candidate_id] = clip
    return by_candidate


def _audit_summary(report: dict[str, Any] | None) -> JobAuditSummary | None:
    if not isinstance(report, dict):
        return None
    summary = report.get("aggregate_summary")
    if not isinstance(summary, dict):
        return None
    warnings_by_type = summary.get("warnings_by_type")
    if not isinstance(warnings_by_type, dict):
        warnings_by_type = {}
    normalized_warnings: dict[str, dict[str, int]] = {}
    warning_counts: dict[str, int] = {}
    for clip_type, counts in warnings_by_type.items():
        if not isinstance(counts, dict):
            continue
        typed_counts: dict[str, int] = {}
        for warning, count in counts.items():
            try:
                parsed_count = int(count)
            except (TypeError, ValueError):
                continue
            warning_name = str(warning)
            typed_counts[warning_name] = parsed_count
            warning_counts[warning_name] = warning_counts.get(warning_name, 0) + parsed_count
        normalized_warnings[str(clip_type)] = typed_counts

    return JobAuditSummary(
        generatedNormalCount=summary.get("generated_normal_count"),
        generatedShortCount=summary.get("generated_short_count"),
        clipsRequiringHumanVisualInspectionCount=summary.get("clips_requiring_human_visual_inspection_count"),
        warningsByType=normalized_warnings,
        warningCounts=warning_counts,
    )


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_item(
    export: ExportItem,
    *,
    selected: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    audit_clip: dict[str, Any] | None = None,
) -> ResultExportItem:
    selected = selected or {}
    metadata = metadata or {}
    audit_clip = audit_clip or {}
    url = f"/api/exports/{export.id}/download"
    metadata_url = f"/api/exports/{export.id}/metadata" if export.metadata_path else None
    subtitle_url = f"/api/exports/{export.id}/subtitle" if export.subtitle_path else None
    thumbnail_status_value = metadata.get("thumbnail_status")
    thumbnail_status = (
        thumbnail_status_value
        if thumbnail_status_value in {"not_generated", "generating", "ready", "failed"}
        else "not_generated"
    )
    thumbnail_path_value = metadata.get("thumbnail_path")
    thumbnail_ready = thumbnail_status in {"ready", "generating"} and isinstance(
        thumbnail_path_value,
        str,
    )
    try:
        thumbnail_render_revision = max(
            0,
            int(metadata.get("thumbnail_render_revision", 0)),
        )
    except (TypeError, ValueError):
        thumbnail_render_revision = 0
    thumbnail_revision_query = f"?revision={thumbnail_render_revision}"
    thumbnail_url = (
        f"/api/exports/{export.id}/thumbnail{thumbnail_revision_query}"
        if thumbnail_ready
        else None
    )
    thumbnail_download_url = (
        f"/api/exports/{export.id}/thumbnail/download{thumbnail_revision_query}"
        if thumbnail_ready
        else None
    )
    thumbnail_filename_value = metadata.get("thumbnail_filename")
    thumbnail_filename = (
        thumbnail_filename_value
        if isinstance(thumbnail_filename_value, str) and thumbnail_filename_value
        else (
            Path(thumbnail_path_value).name
            if isinstance(thumbnail_path_value, str) and thumbnail_path_value
            else None
        )
    )
    score = _number_or_none(_first_value(selected.get("score"), selected.get("final_score"), metadata.get("score"), export.score))
    final_score = _number_or_none(_first_value(selected.get("final_score"), selected.get("score"), audit_clip.get("final_score"), score))
    resolution = audit_clip.get("resolution") if isinstance(audit_clip.get("resolution"), dict) else None
    if resolution is None and (metadata.get("width") is not None or metadata.get("height") is not None):
        resolution = {"width": metadata.get("width"), "height": metadata.get("height")}
    return ResultExportItem(
        id=export.id,
        type=export.type,
        candidateId=export.candidate_id,
        title=export.title,
        titleSource=_first_value(
            metadata.get("title_source"),
            selected.get("title_source"),
            audit_clip.get("title_source"),
        ),
        titleCandidates=_first_value(
            metadata.get("title_candidates"),
            selected.get("title_candidates"),
            [],
        ),
        recommendedTitleId=_first_value(
            metadata.get("recommended_title_id"),
            selected.get("recommended_title_id"),
        ),
        selectedTitleId=_first_value(
            metadata.get("selected_title_id"),
            selected.get("selected_title_id"),
        ),
        youtubeDescription=str(
            _first_value(
                metadata.get("youtube_description"),
                selected.get("youtube_description"),
                "",
            )
        ),
        youtubeHashtags=_first_value(
            metadata.get("youtube_hashtags"),
            selected.get("youtube_hashtags"),
            [],
        ),
        youtubeTags=_first_value(
            metadata.get("youtube_tags"),
            selected.get("youtube_tags"),
            [],
        ),
        descriptionEvidenceSegmentIds=_first_value(
            metadata.get("description_evidence_segment_ids"),
            selected.get("description_evidence_segment_ids"),
            [],
        ),
        postMetadataSource=_first_value(
            metadata.get("post_metadata_source"),
            selected.get("post_metadata_source"),
        ),
        duration=export.duration,
        score=score if score is not None else export.score,
        finalScore=final_score,
        ruleScore=_number_or_none(_first_value(selected.get("rule_score"), audit_clip.get("rule_score"))),
        aiScore=_number_or_none(_first_value(selected.get("ai_score"), audit_clip.get("ai_score"))),
        selectionReason=_first_value(selected.get("selection_reason"), audit_clip.get("selection_reason")),
        belowQualityThreshold=_first_value(selected.get("below_quality_threshold"), audit_clip.get("below_quality_threshold")),
        qualityWarning=_first_value(selected.get("quality_warning"), audit_clip.get("quality_warning")),
        openaiScoreSource=_first_value(selected.get("openai_score_source"), audit_clip.get("openai_score_source")),
        boundaryRefined=_first_value(
            metadata.get("boundary_refined"),
            selected.get("boundary_refined"),
            audit_clip.get("boundary_refined"),
        ),
        overlayTitleExpected=_first_value(
            metadata.get("overlay_title_expected"),
            selected.get("overlay_title_expected"),
            audit_clip.get("overlay_title_expected"),
        ),
        overlayTitleRendered=_first_value(
            metadata.get("overlay_title_rendered"),
            selected.get("overlay_title_rendered"),
            audit_clip.get("overlay_title_rendered"),
        ),
        start=_number_or_none(_first_value(metadata.get("start"), selected.get("start"), audit_clip.get("selected_start"))),
        end=_number_or_none(_first_value(metadata.get("end"), selected.get("end"), audit_clip.get("selected_end"))),
        originalStart=_number_or_none(
            _first_value(metadata.get("original_start"), selected.get("original_start"), audit_clip.get("original_start"))
        ),
        originalEnd=_number_or_none(
            _first_value(metadata.get("original_end"), selected.get("original_end"), audit_clip.get("original_end"))
        ),
        refinedStart=_number_or_none(
            _first_value(metadata.get("refined_start"), selected.get("refined_start"), audit_clip.get("refined_start"))
        ),
        refinedEnd=_number_or_none(_first_value(metadata.get("refined_end"), selected.get("refined_end"), audit_clip.get("refined_end"))),
        resolution=resolution,
        auditWarnings=audit_clip.get("warnings") if isinstance(audit_clip.get("warnings"), list) else [],
        subtitlePath=_first_value(metadata.get("subtitle_path"), export.subtitle_path),
        subtitleUrl=subtitle_url,
        metadataPath=export.metadata_path,
        metadataUrl=metadata_url,
        videoUrl=url,
        downloadUrl=url,
        thumbnailUrl=thumbnail_url,
        thumbnailDownloadUrl=thumbnail_download_url,
        thumbnailStatus=thumbnail_status,
        thumbnailFilename=thumbnail_filename,
        thumbnailFrameSeconds=_number_or_none(
            _first_value(
                metadata.get("thumbnail_frame_seconds"),
                selected.get("thumbnail_frame_seconds"),
            )
        ),
        thumbnailSubjectAnchorX=_number_or_none(
            _first_value(metadata.get("thumbnail_subject_anchor_x"), 1.0)
        ),
        thumbnailRenderRevision=thumbnail_render_revision,
    )


def _read_json_if_exists(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_payload(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


_SHORT_CONVERSION_ARTIFACT_FILENAMES = (
    "normal_candidates.json",
    "short_candidates.json",
    "candidates.json",
    "scored_candidates.json",
    "selected_clips.json",
    "candidate_generation_summary.json",
    "subtitle_review.json",
    "subtitle_review_summary.json",
)


def _snapshot_short_conversion_artifacts(output_dir: Path) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for filename in _SHORT_CONVERSION_ARTIFACT_FILENAMES:
        path = output_dir / filename
        snapshot[path] = path.read_bytes() if path.is_file() else None
    return snapshot


def _restore_short_conversion_artifacts(snapshot: dict[Path, bytes | None]) -> None:
    for path, payload in snapshot.items():
        if payload is None:
            path.unlink(missing_ok=True)
            continue
        temporary_path = path.with_suffix(f"{path.suffix}.rollback")
        temporary_path.write_bytes(payload)
        temporary_path.replace(path)


def _reedit_transcript_segments(
    output_dir: Path,
    document: SubtitleReviewDocument,
) -> list[TranscriptSegment]:
    payload = _read_json_if_exists(transcript_output_path(output_dir))
    if isinstance(payload, list) and payload:
        try:
            transcript_segments = [TranscriptSegment.model_validate(item) for item in payload]
            reviewed_text = {segment.index: segment.text for segment in document.segments}
            return [
                segment.model_copy(update={"text": reviewed_text.get(index, segment.text)})
                for index, segment in enumerate(transcript_segments)
            ]
        except ValueError:
            pass
    return [
        TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=segment.text,
            confidence=segment.confidence,
        )
        for segment in sorted(document.segments, key=lambda item: item.index)
    ]


def _reedit_candidate(
    output_dir: Path,
    document: SubtitleReviewDocument,
    clip_id: str,
) -> tuple[Candidate, CandidateSelection]:
    selection_payload = _read_json_if_exists(output_dir / "selected_clips.json")
    try:
        selection = CandidateSelection.model_validate(selection_payload or {})
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="selected clip data is unavailable",
        ) from exc
    selection = apply_reviewed_clip_content(selection, document)
    candidates = [*selection.normal_clips, *selection.shorts]
    candidate = next((item for item in candidates if item.id == clip_id), None)
    if candidate is not None:
        return candidate, selection

    review_clip = next((item for item in document.clips if item.id == clip_id), None)
    if review_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="completed clip not found",
        )
    transcript_text = " ".join(
        segment.text.strip()
        for segment in document.segments
        if clip_id in segment.affected_clip_ids and segment.text.strip()
    )
    candidate = Candidate(
        id=review_clip.id,
        type=review_clip.type,
        start=review_clip.start,
        end=review_clip.end,
        duration=review_clip.duration,
        transcript_text=transcript_text,
        title=review_clip.publication_title or review_clip.title,
        overlay_title=review_clip.title,
        hook_text=review_clip.hook_text or None,
        hook_duration_seconds=review_clip.hook_duration_seconds,
        hook_scene_start=review_clip.hook_scene_start,
        hook_scene_end=review_clip.hook_scene_end,
        title_candidates=review_clip.title_candidates,
        recommended_title_id=review_clip.recommended_title_id,
        selected_title_id=review_clip.selected_title_id,
        youtube_description=review_clip.youtube_description or None,
        youtube_hashtags=review_clip.youtube_hashtags,
        youtube_tags=review_clip.youtube_tags,
        description_evidence_segment_ids=review_clip.description_evidence_segment_ids,
        post_metadata_source=review_clip.post_metadata_source,
        post_metadata_revision_hash=review_clip.post_metadata_revision_hash,
        title_style=review_clip.title_style,
        hook_style=review_clip.hook_style,
        subtitle_style=review_clip.subtitle_style,
        subtitle_styles=review_clip.subtitle_styles,
        framing_offset_x=review_clip.framing_offset_x,
        framing_offset_y=review_clip.framing_offset_y,
        framing_zoom=review_clip.framing_zoom,
        selection_reason="completed_clip_reedit",
        original_start=review_clip.start,
        original_end=review_clip.end,
    )
    return candidate, selection


def _isolated_reedit_selection(candidate: Candidate) -> CandidateSelection:
    normal_clips = [candidate] if candidate.type == "normal" else []
    shorts = [candidate] if candidate.type == "short" else []
    return CandidateSelection(
        normalClips=normal_clips,
        shorts=shorts,
        selectionPolicy="fill_requested",
        requestedNormalCount=len(normal_clips),
        requestedShortCount=len(shorts),
        hardGatePassedCount=1,
        normalHardGatePassedCount=len(normal_clips),
        shortHardGatePassedCount=len(shorts),
        selectedAboveThresholdCount=1,
        selectedClusters={"normal": [], "short": []},
        unfilledRequestedCounts={"normal": 0, "short": 0},
    )


def _isolated_reedit_source_state_is_supported(
    job: Job,
    document: SubtitleReviewDocument,
) -> bool:
    if (job.status, document.state) == ("completed", "completed"):
        return True
    return (
        (job.status, document.state) == ("awaiting_subtitle_review", "awaiting_review")
        and document.reopened_at is not None
        and document.render_revision > 1
    )


def _create_isolated_reedit_job(
    *,
    db: Session,
    source_job: Job,
    video: Video,
    clip_id: str,
    paths: StoragePaths,
) -> tuple[Job, SubtitleReviewDocument]:
    source_output_dir = paths.job_outputs(source_job.id)
    with subtitle_review_document_lock(source_output_dir):
        db.refresh(source_job)
        if not _reedit_artifacts_available(source_job.id, video, paths):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="isolated re-edit source artifacts are unavailable",
            )
        source_document = _get_subtitle_review_or_404(source_job.id, paths)
        if not _isolated_reedit_source_state_is_supported(source_job, source_document):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review state is unavailable for isolated re-editing",
            )
        candidate, _source_selection = _reedit_candidate(
            source_output_dir,
            source_document,
            clip_id,
        )
        transcript_segments = _reedit_transcript_segments(
            source_output_dir,
            source_document,
        )
        if not transcript_segments:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="completed transcript is unavailable",
            )
        source_audio_features = _read_json_if_exists(source_output_dir / "audio_features.json")
        source_transcript_summary = _read_json_if_exists(
            source_output_dir / "transcript_summary.json"
        )

    selection = _isolated_reedit_selection(candidate)
    child_settings = dict(source_job.settings_json or {})
    child_settings.update(
        {
            "workflowMode": "manual",
            "automationMode": "manual",
            "manualEditFinalized": True,
            "reeditOf": source_job.id,
            "reeditSourceClipId": clip_id,
            "normalClipCount": len(selection.normal_clips),
            "shortCount": len(selection.shorts),
            "normalClipTimeRanges": (
                [{"startSeconds": candidate.start, "endSeconds": candidate.end}]
                if candidate.type == "normal"
                else []
            ),
            "shortClipTimeRanges": (
                [{"startSeconds": candidate.start, "endSeconds": candidate.end}]
                if candidate.type == "short"
                else []
            ),
            "manualClipMetadata": [
                {
                    "id": candidate.id,
                    "type": candidate.type,
                    "title": candidate.title or candidate.overlay_title or "",
                    "startSeconds": candidate.start,
                    "endSeconds": candidate.end,
                    "hookSceneStart": candidate.hook_scene_start,
                    "hookSceneEnd": candidate.hook_scene_end,
                }
            ],
            "requireSubtitleReview": True,
            "requireClipPlanReview": False,
            "heatmapIntervalMode": False,
            "initialSelectionProvider": "legacy",
            "useOpenAIScoring": False,
            "ensureSelectedOpenAIScored": False,
        }
    )
    child = Job(
        id=make_id("job"),
        video_id=video.id,
        status="awaiting_subtitle_review",
        progress=PROGRESS_MAP["awaiting_subtitle_review"],
        current_step=CURRENT_STEP_MAP["awaiting_subtitle_review"],
        settings_json=child_settings,
    )
    child_output_dir = paths.outputs / child.id
    db.add(child)
    try:
        child_output_dir.mkdir(parents=True, exist_ok=False)
        write_transcript_segments(
            transcript_segments,
            transcript_output_path(child_output_dir),
        )
        write_candidates(selection.normal_clips, child_output_dir / "normal_candidates.json")
        write_candidates(selection.shorts, child_output_dir / "short_candidates.json")
        write_candidates([candidate], child_output_dir / "candidates.json")
        write_candidates([candidate], child_output_dir / "scored_candidates.json")
        write_selected_clips(selection, child_output_dir / "selected_clips.json")

        duration = max(float(video.duration or 0), candidate.end)
        audio_features = (
            source_audio_features
            if isinstance(source_audio_features, dict)
            else {
                "duration": duration,
                "silence_ratio": 0.0,
                "speech_density": 1.0,
                "volume_peak": 0.0,
                "silent_seconds": 0.0,
                "speech_seconds": duration,
            }
        )
        _write_json_payload(child_output_dir / "audio_features.json", audio_features)
        _write_json_payload(
            child_output_dir / "candidate_generation_summary.json",
            {
                "source": "completed_clip_reedit",
                "source_job_id": source_job.id,
                "source_clip_id": clip_id,
                "normal_candidate_count": len(selection.normal_clips),
                "short_candidate_count": len(selection.shorts),
            },
        )
        if isinstance(source_transcript_summary, dict):
            _write_json_payload(
                child_output_dir / "transcript_summary.json",
                source_transcript_summary,
            )

        document = build_subtitle_review(
            child.id,
            selection,
            transcript_segments,
            short_max_duration=float(child_settings.get("shortMaxDuration", 75.0)),
            render_mode=str(child_settings.get("mode", "high_quality")),
            short_overlay_title_mode=_short_overlay_title_mode(child_settings),
            short_layout=_short_layout(child_settings),
            short_top_banner_enabled=bool(child_settings.get("shortTopBannerEnabled", False)),
            short_bottom_banner_enabled=bool(child_settings.get("shortBottomBannerEnabled", False)),
            render_settings=child_settings,
            source_width=video.width,
            source_height=video.height,
        )
        document.reedit_source_job_id = source_job.id
        document.reedit_source_clip_id = clip_id
        document.render_revision = max(2, document.render_revision)
        _write_subtitle_review_unlocked(document, paths)
        db.commit()
        db.refresh(child)
        return child, document
    except Exception:
        db.rollback()
        if child_output_dir.is_dir():
            shutil.rmtree(child_output_dir)
        raise


def _is_legacy_no_usable_selection(job: Job, paths: StoragePaths) -> bool:
    if job.error_code != LEGACY_NO_USABLE_OUTPUT_ERROR_CODE:
        return False

    output_dir = paths.outputs / job.id
    selected = _read_json_if_exists(output_dir / "selected_clips.json")
    rejection_summary = _read_json_if_exists(output_dir / "rejection_summary.json")
    if not isinstance(selected, dict) or not isinstance(rejection_summary, dict):
        return False

    normal_clips = selected.get("normalClips")
    shorts = selected.get("shorts")
    if not isinstance(normal_clips, list) or not isinstance(shorts, list):
        return False
    if normal_clips or shorts:
        return False

    render_failure_count = rejection_summary.get("render_failure_count")
    if not isinstance(render_failure_count, int) or isinstance(render_failure_count, bool) or render_failure_count != 0:
        return False

    render_failures_path = output_dir / "render_failures.json"
    if render_failures_path.is_file():
        render_failures = _read_json_if_exists(render_failures_path)
        if not isinstance(render_failures, list) or render_failures:
            return False

    return not subtitle_review_output_path(output_dir).is_file()


def _is_selection_failure(job: Job, paths: StoragePaths) -> bool:
    if job.status != "failed":
        return False
    if job.error_code == NO_USABLE_SELECTION_ERROR_CODE:
        return True
    return _is_legacy_no_usable_selection(job, paths)


def _is_retryable_selection_failure(job: Job, paths: StoragePaths) -> bool:
    if not _is_selection_failure(job, paths):
        return False
    return RETRY_SOURCE_SETTING_KEY not in (job.settings_json or {})


def _has_terminal_retry_child(db: Session, source_job_id: str) -> bool:
    child_status = db.scalar(select(Job.status).where(Job.id == _retry_job_id(source_job_id)))
    return child_status in TERMINAL_STATUSES


def _quality_gate_attention_clip_ids(
    checks: list[Any],
    *,
    all_clip_ids: set[str],
) -> set[str]:
    clip_ids: set[str] = set()
    has_global_attention = False
    list_keys = {
        "invalidClipIds",
        "missingClipIds",
        "staleClipIds",
        "uncoveredClipIds",
        "failedClipIds",
        "unknownClipIds",
        "incompleteClipIds",
    }
    for check in checks:
        if getattr(check, "outcome", "pass") == "pass":
            continue
        evidence = getattr(check, "evidence", {})
        found_for_check = False
        if isinstance(evidence, dict):
            for key in list_keys:
                values = evidence.get(key)
                if isinstance(values, list):
                    valid_values = {
                        value
                        for value in values
                        if isinstance(value, str) and value in all_clip_ids
                    }
                    clip_ids.update(valid_values)
                    found_for_check = found_for_check or bool(valid_values)
            flags = evidence.get("flagsByClipId")
            if isinstance(flags, dict):
                valid_values = {
                    value
                    for value in flags
                    if isinstance(value, str) and value in all_clip_ids
                }
                clip_ids.update(valid_values)
                found_for_check = found_for_check or bool(valid_values)
            for item_key in (
                "problems",
                "duplicates",
                "unknown",
                "failures",
                "inconsistent",
            ):
                items = evidence.get(item_key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for key in ("clipId", "candidateId", "duplicateOf"):
                        value = item.get(key)
                        if isinstance(value, str) and value in all_clip_ids:
                            clip_ids.add(value)
                            found_for_check = True
        if not found_for_check:
            has_global_attention = True
    return set(all_clip_ids) if has_global_attention else clip_ids


def _job_quality_gate_mode(
    job: Job,
    output_dir: Path,
) -> QualityGateMode | None:
    manifest_path = automation_manifest_path(output_dir)
    if manifest_path.is_file():
        try:
            effective_mode = load_automation_manifest(manifest_path).effective_mode
        except (OSError, ValueError):
            pass
        else:
            return (
                effective_mode
                if effective_mode in {"shadow", "guarded", "auto"}
                else None
            )
    requested_mode = str(
        (job.settings_json or {}).get("automationMode") or "manual"
    ).strip()
    return (
        requested_mode
        if requested_mode in {"shadow", "guarded", "auto"}
        else None
    )


def _evaluate_and_write_content_quality_gate(
    *,
    job: Job,
    document: SubtitleReviewDocument,
    output_dir: Path,
) -> QualityGateDecision | None:
    mode = _job_quality_gate_mode(job, output_dir)
    if mode is None:
        return None
    title_hook_evidence: dict[str, TitleHookSuggestionsDocument] = {}
    if mode == "auto":
        for clip in document.clips:
            artifact_path = title_hook_suggestions_path(output_dir, clip.id)
            if not artifact_path.is_file():
                continue
            try:
                artifact = load_title_hook_suggestions(artifact_path)
            except (OSError, ValueError):
                continue
            if artifact.clip_id == clip.id:
                title_hook_evidence[clip.id] = artifact
    try:
        content_gate = evaluate_content_quality_gate(
            job_id=job.id,
            document=document,
            settings=dict(job.settings_json or {}),
            mode=mode,
            title_hook_evidence=title_hook_evidence,
        )
    except Exception as exc:
        content_gate = unknown_quality_gate_decision(
            job_id=job.id,
            stage="content",
            reason_code="content_gate_evaluation_failed",
            evidence={"errorType": exc.__class__.__name__},
            mode=mode,
        )
    try:
        write_quality_gate_decision(
            content_gate,
            quality_gate_decision_path(output_dir, "content"),
        )
    except OSError:
        return None
    return content_gate


def _write_content_quality_gate(
    *,
    job: Job,
    document: SubtitleReviewDocument,
    output_dir: Path,
) -> bool:
    return (
        _evaluate_and_write_content_quality_gate(
            job=job,
            document=document,
            output_dir=output_dir,
        )
        is not None
    )


def _prepare_auto_review_render_unlocked(
    *,
    db: Session,
    job: Job,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
) -> tuple[SubtitleReviewDocument, bool]:
    output_dir = paths.job_outputs(job.id)
    if (
        _job_quality_gate_mode(job, output_dir) != "auto"
        or job.status != "awaiting_subtitle_review"
        or document.state != "awaiting_review"
    ):
        return document, False

    decision = _evaluate_and_write_content_quality_gate(
        job=job,
        document=document,
        output_dir=output_dir,
    )
    if decision is None or decision.route != "continue":
        return document, False

    document = queue_auto_review_render(document)
    write_subtitle_review(
        document,
        subtitle_review_output_path(output_dir),
    )
    write_subtitle_review_summary(
        document,
        subtitle_review_summary_path(output_dir),
    )
    job.status = "rendering_normal_clips"
    job.progress = PROGRESS_MAP["rendering_normal_clips"]
    job.current_step = CURRENT_STEP_MAP["rendering_normal_clips"]
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)
    return document, True


def _enqueue_prepared_auto_review_render(
    *,
    db: Session,
    job: Job,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    enqueue_render: RenderEnqueue,
) -> None:
    output_dir = paths.job_outputs(job.id)
    try:
        enqueue_render(job.id, document.render_revision)
    except Exception as exc:
        with subtitle_review_document_lock(output_dir):
            latest = _get_subtitle_review_or_404(job.id, paths)
            if latest.state == "render_queued":
                latest.state = "awaiting_review"
                write_subtitle_review(
                    latest,
                    subtitle_review_output_path(output_dir),
                )
                write_subtitle_review_summary(
                    latest,
                    subtitle_review_summary_path(output_dir),
                )
            db.refresh(job)
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
            job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
            job.updated_at = utc_now()
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue automatic subtitle rendering",
        ) from exc


def _quality_gate_stage_order(
    job_status: str,
    *,
    auto_post_render_review: bool = False,
) -> tuple[QualityGateStage, ...]:
    if job_status in {"preparing_clip_review", "awaiting_clip_review"}:
        return ("selection",)
    if job_status == "preparing_subtitle_review":
        return ("content",)
    if job_status == "awaiting_subtitle_review":
        return (
            ("post_render", "content")
            if auto_post_render_review
            else ("content",)
        )
    if job_status in {
        "rendering_normal_clips",
        "rendering_shorts",
        "packaging_zip",
        "completed",
    }:
        return ("post_render",)
    if job_status == "failed":
        return ("post_render", "content", "selection")
    return ("selection",)


def _job_details(job: Job, paths: StoragePaths) -> dict[str, Any]:
    details: dict[str, Any] = {}
    output_dir = paths.job_outputs(job.id)
    job_settings = job.settings_json if isinstance(job.settings_json, dict) else {}
    initial_selection_provider = str(
        job_settings.get("initialSelectionProvider") or "legacy"
    ).strip()
    details["initialSelectionProvider"] = (
        initial_selection_provider
        if initial_selection_provider in {"legacy", "codex"}
        else "legacy"
    )
    effective_automation_mode: str | None = None
    manifest_path = automation_manifest_path(output_dir)
    if manifest_path.is_file():
        try:
            automation_manifest = load_automation_manifest(manifest_path)
        except (OSError, ValueError):
            details["automationManifestAvailable"] = False
            details["automationManifestInvalid"] = True
        else:
            details["automationManifestAvailable"] = True
            details["automationMode"] = automation_manifest.requested_mode
            details["automationEffectiveMode"] = automation_manifest.effective_mode
            effective_automation_mode = automation_manifest.effective_mode
            details["automationDecisionInputHash"] = (
                automation_manifest.decision_input_hash
            )

    selected_payload = _read_json_if_exists(output_dir / "selected_clips.json")
    all_clip_ids: set[str] = set()
    if isinstance(selected_payload, dict):
        for key in ("normalClips", "shorts"):
            clips = selected_payload.get(key)
            if not isinstance(clips, list):
                continue
            all_clip_ids.update(
                str(item.get("id"))
                for item in clips
                if isinstance(item, dict) and item.get("id")
            )
    quality_decision = None
    gate_document_found = False
    for stage in _quality_gate_stage_order(
        job.status,
        auto_post_render_review=effective_automation_mode == "auto",
    ):
        decision_path = quality_gate_decision_path(output_dir, stage)
        if not decision_path.is_file():
            continue
        gate_document_found = True
        try:
            quality_decision = load_quality_gate_decision(decision_path)
            if quality_decision.job_id != job.id or quality_decision.stage != stage:
                raise ValueError("quality gate decision identity does not match its job and stage")
            if (
                effective_automation_mode in {"shadow", "guarded", "auto"}
                and quality_decision.mode != effective_automation_mode
            ):
                raise ValueError("quality gate decision mode does not match the active automation mode")
        except (OSError, ValueError):
            quality_decision = None
            details["automationGateState"] = "fallback_manual"
            details["automationGateInvalid"] = True
        break
    if quality_decision is not None:
        attention_clip_ids = _quality_gate_attention_clip_ids(
            quality_decision.checks,
            all_clip_ids=all_clip_ids,
        )
        details["automationGateState"] = (
            "passed" if quality_decision.outcome == "pass" else "needs_attention"
        )
        details["automationGateStage"] = quality_decision.stage
        details["automationGateOutcome"] = quality_decision.outcome
        details["automationGateInputHash"] = quality_decision.input_hash
        details["automationGateAutoPassedClips"] = max(
            0,
            len(all_clip_ids) - len(attention_clip_ids),
        )
        details["automationGateAttentionClips"] = len(attention_clip_ids)
        details["automationGateAttentionClipIds"] = sorted(attention_clip_ids)
        details["automationGateReasonCodes"] = [
            check.reason_code
            for check in quality_decision.checks
            if check.reason_code is not None
        ]
    elif (
        effective_automation_mode in {"guarded", "auto"}
        and not gate_document_found
    ):
        if job.status in {"awaiting_clip_review", "awaiting_subtitle_review", "completed"}:
            details["automationGateState"] = "fallback_manual"
            details["automationGateMissing"] = True
        else:
            details["automationGateState"] = "evaluating"

    initial_codex_summary = _read_json_if_exists(
        output_dir / "codex_initial_selection_summary.json"
    )
    reselection_codex_summary = _read_json_if_exists(
        output_dir / "codex_reselection_summary.json"
    )
    codex_summary = (
        reselection_codex_summary
        if isinstance(reselection_codex_summary, dict)
        else initial_codex_summary
    )
    if isinstance(codex_summary, dict):
        details["codexInitialSelectionSummaryAvailable"] = True
        details["codexInitialSelectionPhase"] = _first_value(
            codex_summary.get("phase"),
            "reselection"
            if isinstance(reselection_codex_summary, dict)
            else "initial",
        )
        details["codexInitialSelectionStatus"] = _first_value(
            codex_summary.get("status"),
            codex_summary.get("state"),
        )
        details["codexInitialSelectionFallbackUsed"] = bool(
            _first_value(
                codex_summary.get("fallback_used"),
                codex_summary.get("fallbackUsed"),
                False,
            )
        )
        details["codexInitialSelectionFallbackReason"] = _first_value(
            codex_summary.get("fallback_reason"),
            codex_summary.get("fallbackReason"),
        )
        details["codexInitialSelectionRequestedNormalCount"] = _first_value(
            codex_summary.get("requested_normal_count"),
            codex_summary.get("requestedNormalCount"),
            job_settings.get("normalClipCount"),
        )
        details["codexInitialSelectionRequestedShortCount"] = _first_value(
            codex_summary.get("requested_short_count"),
            codex_summary.get("requestedShortCount"),
            job_settings.get("shortCount"),
        )
        normal_clips = _first_value(
            codex_summary.get("normal_clips"),
            codex_summary.get("normalClips"),
        )
        shorts = codex_summary.get("shorts")
        details["codexInitialSelectionSelectedNormalCount"] = _first_value(
            codex_summary.get("selected_normal_count"),
            codex_summary.get("selectedNormalCount"),
            len(normal_clips) if isinstance(normal_clips, list) else None,
        )
        details["codexInitialSelectionSelectedShortCount"] = _first_value(
            codex_summary.get("selected_short_count"),
            codex_summary.get("selectedShortCount"),
            len(shorts) if isinstance(shorts, list) else None,
        )
        details["codexInitialSelectionPromptVersion"] = _first_value(
            codex_summary.get("prompt_version"),
            codex_summary.get("promptVersion"),
        )
        details["codexInitialSelectionRequestId"] = _first_value(
            codex_summary.get("request_id"),
            codex_summary.get("requestId"),
        )
        details["codexInitialSelectionAttemptCount"] = _first_value(
            codex_summary.get("attempt_count"),
            codex_summary.get("attemptCount"),
        )
        details["codexInitialSelectionHostErrorCode"] = _first_value(
            codex_summary.get("host_error_code"),
            codex_summary.get("hostErrorCode"),
        )
        summary_error = codex_summary.get("error")
        if isinstance(summary_error, dict):
            details["codexInitialSelectionErrorCode"] = summary_error.get("code")
            details["codexInitialSelectionErrorMessage"] = summary_error.get("message")
            details["codexInitialSelectionError"] = _first_value(
                summary_error.get("message"),
                summary_error.get("code"),
            )
        elif summary_error is not None:
            details["codexInitialSelectionError"] = str(summary_error)
            details["codexInitialSelectionErrorMessage"] = str(summary_error)
    else:
        details["codexInitialSelectionSummaryAvailable"] = False

    audio_features = _read_json_if_exists(output_dir / "audio_features.json")
    if isinstance(audio_features, dict):
        for key in ("duration", "silence_ratio", "speech_seconds", "speech_density", "volume_peak"):
            if key in audio_features:
                details[key] = audio_features[key]

    heatmap_summary = _read_json_if_exists(output_dir / "heatmap_validation_summary.json")
    if isinstance(heatmap_summary, dict):
        details["heatmapStatus"] = heatmap_summary.get("status")
        details["heatmapApplied"] = bool(heatmap_summary.get("applied", False))
        details["heatmapFallbackUsed"] = bool(heatmap_summary.get("fallback_used", False))
        details["heatmapFallbackReason"] = heatmap_summary.get("fallback_reason")
        details["heatmapSegmentCount"] = heatmap_summary.get("segment_count", 0)
        details["heatmapIntervalModeRequested"] = bool(heatmap_summary.get("interval_mode_requested", False))
        details["heatmapIntervalModeApplied"] = bool(heatmap_summary.get("interval_mode_applied", False))
        details["heatmapSelectionBehavior"] = heatmap_summary.get("selection_behavior")

    transcript_segments = _read_json_if_exists(output_dir / "transcript_segments.json")
    if isinstance(transcript_segments, list):
        texts = [str(segment.get("text", "")).strip() for segment in transcript_segments if isinstance(segment, dict)]
        confidences = [
            float(segment["confidence"])
            for segment in transcript_segments
            if isinstance(segment, dict) and segment.get("confidence") is not None
        ]
        speech_duration = sum(
            max(0.0, float(segment.get("end", 0.0)) - float(segment.get("start", 0.0)))
            for segment in transcript_segments
            if isinstance(segment, dict) and str(segment.get("text", "")).strip()
        )
        details["segment_count"] = len(transcript_segments)
        details["total_text_length"] = len(" ".join(text for text in texts if text).strip())
        details["total_speech_duration"] = round(speech_duration, 6)
        if confidences:
            details["average_confidence"] = round(sum(confidences) / len(confidences), 6)

    correction_progress = _read_json_if_exists(output_dir / TRANSCRIPT_CORRECTION_PROGRESS_FILENAME)
    if isinstance(correction_progress, dict):
        for key in (
            "stage",
            "stageProgress",
            "correctionBatchesCompleted",
            "correctionBatchesTotal",
            "correctionRetryCount",
            "correctionTargetsCompleted",
            "correctionTargetsTotal",
            "transcriptSegmentCount",
            "fallbackUsed",
            "finished",
        ):
            if key in correction_progress:
                details[key] = correction_progress[key]

    subtitle_review = _read_json_if_exists(subtitle_review_output_path(output_dir))
    if isinstance(subtitle_review, dict):
        details["subtitleReviewState"] = subtitle_review.get("state")
        details["subtitleReviewConfirmedClips"] = subtitle_review.get("confirmedClipCount", 0)
        details["subtitleReviewTotalClips"] = subtitle_review.get("totalClipCount", 0)
        details["subtitleReviewEditedSegments"] = subtitle_review.get("editedSegmentCount", 0)

    clip_plan = _read_json_if_exists(clip_plan_output_path(output_dir))
    if isinstance(clip_plan, dict):
        details["clipPlanState"] = clip_plan.get("state")
        details["clipPlanRevision"] = clip_plan.get("revision", 1)
        clips = clip_plan.get("clips")
        details["clipPlanClipCount"] = len(clips) if isinstance(clips, list) else 0

    return details


def _stale_worker_timeout_seconds(job: Job) -> int:
    value = (job.settings_json or {}).get("workerHeartbeatTimeoutSeconds", DEFAULT_STALE_WORKER_SECONDS)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_STALE_WORKER_SECONDS
    return max(60, parsed)


def _mark_stale_running_job_failed(db: Session, job: Job) -> None:
    if job.status in TERMINAL_STATUSES or job.status in NON_WORKER_STATUSES:
        return
    timeout_seconds = _stale_worker_timeout_seconds(job)
    age = utc_now() - job.updated_at
    if age <= timedelta(seconds=timeout_seconds):
        return
    previous_status = job.status
    job.status = "failed"
    job.progress = 100
    job.current_step = "Failed"
    job.error_code = "worker_terminated_unexpectedly"
    job.error_message = (
        "Worker heartbeat stopped while job was running. "
        f"Previous status: {previous_status}. "
        f"Heartbeat age seconds: {round(age.total_seconds(), 3)}."
    )
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)


@router.post(
    "/reedit-upload",
    response_model=CompletedVideoReeditResponse,
)
def reopen_from_completed_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    settings: Settings = Depends(get_settings),
) -> CompletedVideoReeditResponse:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".mp4":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "reedit_mp4_required",
                "message": "AutoClipperで書き出したMP4を選択してください。",
            },
        )
    content_type = (file.content_type or "").lower()
    if content_type not in {"", "application/octet-stream", "video/mp4"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "reedit_mp4_required",
                "message": "AutoClipperで書き出したMP4を選択してください。",
            },
        )

    try:
        fingerprint = fingerprint_stream(file.file, settings.max_upload_size_bytes)
    except UploadSizeLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": "再編集するMP4がアップロード上限を超えています。",
            },
        ) from exc

    exports = matching_exports(db, paths, fingerprint)
    if not exports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "reedit_source_not_found",
                "message": ("このMP4に対応する完成済みjobが見つかりません。同じPCで作成した未変更のAutoClipper出力を選択してください。"),
            },
        )

    unavailable_match_found = False
    for export in exports:
        job = db.get(Job, export.job_id)
        video = db.get(Video, export.video_id)
        if job is None or video is None:
            unavailable_match_found = True
            continue
        try:
            reedit_job, document = _create_isolated_reedit_job(
                db=db,
                source_job=job,
                video=video,
                clip_id=export.candidate_id or "",
                paths=paths,
            )
        except HTTPException as exc:
            if exc.status_code not in {
                status.HTTP_404_NOT_FOUND,
                status.HTTP_409_CONFLICT,
            }:
                raise
            unavailable_match_found = True
            continue
        return CompletedVideoReeditResponse(
            jobId=reedit_job.id,
            exportId=export.id,
            matchedClipId=export.candidate_id,
            clipType=export.type,
            title=export.title,
            reviewState=document.state,
        )

    if unavailable_match_found:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "reedit_source_unavailable",
                "message": (
                    "対応するjobは見つかりましたが、再編集に必要な保存データが不足しているか、"
                    "現在の処理状態が再編集に対応していません。"
                ),
            },
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "reedit_source_not_found",
            "message": "このMP4に対応する完成済みjobが見つかりません。",
        },
    )


@router.post(
    "/{job_id}/clips/{clip_id}/reedit",
    response_model=SubtitleReviewDocument,
    status_code=status.HTTP_201_CREATED,
)
def create_clip_reedit(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> SubtitleReviewDocument:
    source_job = _get_job_or_404(db, job_id)
    video = db.get(Video, source_job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    _child, document = _create_isolated_reedit_job(
        db=db,
        source_job=source_job,
        video=video,
        clip_id=clip_id,
        paths=paths,
    )
    return document


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    enqueue_job: JobEnqueue = Depends(get_enqueue_job),
    paths: StoragePaths = Depends(get_storage_paths),
    app_settings: Settings = Depends(get_settings),
) -> JobCreateResponse:
    video = db.get(Video, request.video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="video not found")

    settings = request.settings
    if settings.short_count > 0:
        for position, enabled, default_path in (
            ("top", settings.short_top_banner_enabled, DEFAULT_SHORT_TOP_BANNER_PATH),
            ("bottom", settings.short_bottom_banner_enabled, DEFAULT_SHORT_BOTTOM_BANNER_PATH),
        ):
            if enabled and not resolve_banner_path(
                settings.model_dump(by_alias=True), position, default_path, paths
            ).is_file():
                raise HTTPException(422, "帯画像が見つかりません。画像を選び直してください。")
    thumbnail_style = settings.normal_thumbnail_style
    if settings.normal_clip_count > 0 and thumbnail_style and thumbnail_style.design == "custom":
        if not banner_asset_path(thumbnail_style.background_asset_id, paths).is_file():
            raise HTTPException(422, "サムネイル背景画像が見つかりません。")
    automatic_output = (settings.normal_clip_count > 0 and not settings.normal_clip_time_ranges) or (
        settings.short_count > 0 and not settings.short_clip_time_ranges
    )
    if (
        settings.workflow_mode != "manual"
        and settings.heatmap_interval_mode
        and automatic_output
    ):
        sidecar_path = paths.resolve_video_heatmap(video.id, video.stored_path)
        unavailable_reason = "heatmap_sidecar_not_provided"
        try:
            if sidecar_path.stat().st_size > app_settings.max_heatmap_sidecar_size_bytes:
                unavailable_reason = "heatmap_sidecar_too_large"
            else:
                sidecar = parse_heatmap_sidecar(sidecar_path.read_bytes())
                if sidecar.heatmap_available and any(segment.value > 0 for segment in sidecar.heatmap):
                    unavailable_reason = ""
                else:
                    unavailable_reason = "heatmap_unavailable"
        except HeatmapSidecarError as exc:
            unavailable_reason = exc.code
        except OSError:
            unavailable_reason = "heatmap_sidecar_not_provided"
        if unavailable_reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "heatmap_interval_mode_requires_data",
                    "message": "人気度JSONを参考にするには有効なJSONが必要です。",
                    "reason": unavailable_reason,
                },
            )

    job = Job(
        id=make_id("job"),
        video_id=video.id,
        status="queued",
        progress=5,
        current_step="Queued",
        settings_json=request.settings.model_dump(by_alias=True, mode="json"),
    )
    db.add(job)
    db.commit()

    enqueue_job(job.id)

    return JobCreateResponse(jobId=job.id, status=job.status)


def _retry_job_id(source_job_id: str) -> str:
    digest = hashlib.sha256(f"retry:{source_job_id}".encode("utf-8")).hexdigest()
    return f"job_{digest[:32]}"


@router.post(
    "/{job_id}/retry",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    enqueue_retry_job: RetryJobEnqueue = Depends(get_enqueue_retry_job),
    paths: StoragePaths = Depends(get_storage_paths),
) -> JobCreateResponse:
    source_job = _get_job_or_404(db, job_id)
    if not _is_retryable_selection_failure(
        source_job,
        paths,
    ) or _has_terminal_retry_child(db, source_job.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "job_retry_not_available",
                "message": "このjobは同じ動画・設定で再処理できません。",
            },
        )

    video = db.get(Video, source_job.video_id)
    if video is None or not paths.resolve_stored_file(video.stored_path).is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "retry_source_unavailable",
                "message": "元動画が残っていないため再処理できません。",
            },
        )

    settings = _validated_persisted_job_settings(source_job.settings_json)
    automatic_output = (settings.normal_clip_count > 0 and not settings.normal_clip_time_ranges) or (
        settings.short_count > 0 and not settings.short_clip_time_ranges
    )
    if settings.heatmap_interval_mode and automatic_output:
        sidecar_path = paths.resolve_video_heatmap(video.id, video.stored_path)
        if not sidecar_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "retry_source_unavailable",
                    "message": "参考用の人気度JSONが残っていないため再処理できません。",
                },
            )

    retry_settings = settings.model_dump(by_alias=True, mode="json")
    retry_settings[RETRY_SOURCE_SETTING_KEY] = source_job.id
    retry_id = _retry_job_id(source_job.id)
    retry = db.get(Job, retry_id)
    if retry is not None:
        db.refresh(retry)
        if retry.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "job_retry_not_available",
                    "message": "このjobの再処理は終了しています。",
                },
            )
    should_enqueue = False
    if retry is None:
        retry = Job(
            id=retry_id,
            video_id=video.id,
            status="queued",
            progress=5,
            current_step=RETRY_ENQUEUE_PENDING_STEP,
            settings_json=retry_settings,
        )
        db.add(retry)
        try:
            db.commit()
            should_enqueue = True
        except IntegrityError:
            db.rollback()
            retry = db.get(Job, retry_id)
            if retry is None:
                raise
            if retry.status == "queued" and retry.current_step == RETRY_ENQUEUE_PENDING_STEP:
                should_enqueue = True
    elif retry.status == "queued" and retry.current_step == RETRY_ENQUEUE_PENDING_STEP:
        should_enqueue = True

    if should_enqueue:

        def terminal_retry_allowed() -> bool:
            result = db.execute(
                update(Job)
                .where(
                    Job.id == retry.id,
                    Job.status == "queued",
                    Job.current_step == RETRY_ENQUEUE_PENDING_STEP,
                )
                .values(updated_at=utc_now())
            )
            db.commit()
            return result.rowcount == 1

        try:
            enqueue_retry_job(retry.id, terminal_retry_allowed)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "retry_enqueue_failed",
                    "message": "再処理を開始できませんでした。もう一度押してください。",
                },
            )
        db.refresh(retry)

    return JobCreateResponse(jobId=retry.id, status=retry.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> JobStatusResponse:
    job = _get_job_or_404(db, job_id)
    _mark_stale_running_job_failed(db, job)
    error = None
    if job.error_code or job.error_message:
        error_code = job.error_code or "unknown"
        error_message = job.error_message or ""
        if _is_selection_failure(job, paths):
            if RETRY_SOURCE_SETTING_KEY in (job.settings_json or {}):
                error_code = NO_USABLE_SELECTION_RETRY_EXHAUSTED_ERROR_CODE
                error_message = "再処理でも選定基準を満たす切り抜き候補がありませんでした。"
            elif _has_terminal_retry_child(db, job.id):
                error_code = NO_USABLE_SELECTION_RETRY_EXHAUSTED_ERROR_CODE
                error_message = "このJobの再処理は終了しています。"
            else:
                error_code = NO_USABLE_SELECTION_ERROR_CODE
                error_message = "分析は完了しましたが、選定基準を満たす切り抜き候補がありませんでした。"
        elif error_code == LEGACY_NO_USABLE_OUTPUT_ERROR_CODE:
            error_message = "切り抜き動画を生成できませんでした。レンダリング結果を確認してください。"
        error = JobError(code=error_code, message=error_message)

    return JobStatusResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        currentStep=job.current_step,
        details=_job_details(job, paths),
        error=error,
    )


@router.get("/{job_id}/source-video")
def get_job_source_video(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="video not found")
    source_path = paths.resolve_stored_file(video.stored_path)
    if not source_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source video not found")
    media_type = mimetypes.guess_type(video.original_filename)[0] or "video/mp4"
    return FileResponse(source_path, media_type=media_type)


@router.get("/{job_id}/editor-video")
def get_job_editor_video(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    _get_job_or_404(db, job_id)
    preview_path = manual_source_proxy_path(paths.job_outputs(job_id))
    if not preview_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="editor video not found",
        )
    return FileResponse(preview_path, media_type="video/mp4")


@router.get("/{job_id}/clip-plan", response_model=ClipPlanDocument)
def get_clip_plan(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    _get_job_or_404(db, job_id)
    return _get_clip_plan_or_404(job_id, paths)


@router.post(
    "/{job_id}/clip-plan/clips",
    response_model=ClipPlanDocument,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_clip(
    job_id: str,
    request: ManualClipCreateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job, video, document = _get_manual_edit_context(db, job_id, paths)
    _validate_manual_clip_range(
        video,
        document,
        start=request.start,
        end=request.end,
    )
    type_index = sum(clip.type == request.type for clip in document.clips) + 1
    default_title = "通常切り抜き" if request.type == "normal" else "ショート"
    clip = ClipPlanClip(
        id=make_id("clip"),
        type=request.type,
        title=request.title.strip() or f"{default_title} {type_index:02d}",
        start=round(request.start, 3),
        end=round(request.end, 3),
        duration=round(request.end - request.start, 3),
        selectionReason="manual_edit",
        recommendedStart=round(request.start, 3),
        recommendedEnd=round(request.end, 3),
        manuallyAdjusted=True,
    )
    document.clips.append(clip)
    try:
        validate_manual_clip_counts(document.clips)
    except ValueError as exc:
        document.clips.pop()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document


@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}",
    response_model=ClipPlanDocument,
)
def update_manual_clip(
    job_id: str,
    clip_id: str,
    request: ManualClipUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job, video, document = _get_manual_edit_context(db, job_id, paths)
    clip_index = next(
        (index for index, clip in enumerate(document.clips) if clip.id == clip_id),
        None,
    )
    if clip_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    current = document.clips[clip_index]
    start = current.start if request.start is None else request.start
    end = current.end if request.end is None else request.end
    clip_type = request.type or current.type
    _validate_manual_clip_range(video, document, start=start, end=end)
    payload = current.model_dump()
    payload.update(
        {
            "type": clip_type,
            "title": current.title if request.title is None else request.title.strip(),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "manually_adjusted": True,
        }
    )
    try:
        updated = ClipPlanClip.model_validate(payload)
        proposed = list(document.clips)
        proposed[clip_index] = updated
        validate_manual_clip_counts(proposed)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    document.clips = proposed
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document


@router.delete(
    "/{job_id}/clip-plan/clips/{clip_id}",
    response_model=ClipPlanDocument,
)
def delete_manual_clip(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    _job, _video, document = _get_manual_edit_context(db, job_id, paths)
    original_count = len(document.clips)
    document.clips = [clip for clip in document.clips if clip.id != clip_id]
    if len(document.clips) == original_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document


@router.get(
    "/{job_id}/clip-plan/clips/{clip_id}/transcript-segments",
    response_model=list[TranscriptSegment],
)
def get_clip_plan_transcript_segments(
    job_id: str,
    clip_id: str,
    start: float,
    end: float,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> list[TranscriptSegment]:
    job = _get_job_or_404(db, job_id)
    document = _get_clip_plan_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in document.clips):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    if start < 0 or end <= start or end - start < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid clip transcript range",
        )
    video = db.get(Video, job.video_id)
    source_duration = float((video.duration if video is not None else None) or document.source_duration or 0)
    if source_duration > 0 and end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )

    transcript_payload = _read_json_if_exists(paths.job_outputs(job_id) / "transcript_segments.json")
    if not isinstance(transcript_payload, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="transcript segments are unavailable",
        )
    transcript_segments = [TranscriptSegment.model_validate(item) for item in transcript_payload]
    transcript_segments = repair_known_transcript_artifact_segments(transcript_segments)
    return [segment for segment in transcript_segments if segment.end > start and segment.start < end]


@router.get("/{job_id}/clip-plan/clips/{clip_id}/preview-video")
def get_clip_plan_preview_video(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    _get_job_or_404(db, job_id)
    document = _get_clip_plan_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in document.clips):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    preview_path = subtitle_review_preview_path(
        paths.job_outputs(job_id),
        clip_id,
    )
    if not preview_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan preview not found",
        )
    return FileResponse(preview_path, media_type="video/mp4")


@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/type",
    response_model=ClipPlanDocument,
)
def update_clip_plan_clip_type(
    job_id: str,
    clip_id: str,
    request: ClipPlanTypeUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting type adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.state != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting type adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    if request.type != "normal":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="only conversion to a normal clip is supported",
        )

    output_dir = paths.job_outputs(job_id)
    selected_path = output_dir / "selected_clips.json"
    selected_payload = _read_json_if_exists(selected_path)
    if not isinstance(selected_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="selected clip data is unavailable",
        )
    try:
        selection = CandidateSelection.model_validate(selected_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="selected clip data is invalid",
        ) from exc
    if planned_clip.type == "short" and len(selection.normal_clips) >= 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="normal clip count cannot exceed 12",
        )
    try:
        converted_selection = convert_selected_clip_to_normal(selection, clip_id)
        convert_clip_plan_clip_to_normal(document, clip_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    next_settings = {
        **dict(job.settings_json or {}),
        "normalClipCount": len(converted_selection.normal_clips),
        "shortCount": len(converted_selection.shorts),
    }
    document.settings = {
        **document.settings,
        "normalClipCount": len(converted_selection.normal_clips),
        "shortCount": len(converted_selection.shorts),
    }
    plan_path = clip_plan_output_path(output_dir)
    artifact_snapshot = {
        selected_path: selected_path.read_bytes(),
        plan_path: plan_path.read_bytes(),
    }
    previous_settings = dict(job.settings_json or {})
    try:
        _write_json_payload(
            selected_path,
            converted_selection.model_dump(by_alias=True, mode="json"),
        )
        _write_json_payload(
            plan_path,
            document.model_dump(by_alias=True, mode="json"),
        )
        job.settings_json = next_settings
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        job.settings_json = previous_settings
        for path, payload in artifact_snapshot.items():
            temporary_path = path.with_suffix(f"{path.suffix}.rollback")
            temporary_path.write_bytes(payload)
            temporary_path.replace(path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="could not update clip type",
        ) from exc
    return document


@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/boundary",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_clip_plan_clip_boundary(
    job_id: str,
    clip_id: str,
    request: ClipPlanBoundaryUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_boundary_update: ClipPlanBoundaryUpdateEnqueue = Depends(get_enqueue_clip_plan_boundary_update),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    manual_edit = job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    )
    if job.status != "awaiting_clip_review" and not manual_edit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    expected_state = "manual_editing" if manual_edit else "awaiting_review"
    if document.state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="video not found",
        )
    source_duration = float(video.duration or document.source_duration or 0)
    if source_duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video duration is unavailable",
        )
    if request.end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )
    if (
        planned_clip.hook_scene_start is not None
        and planned_clip.hook_scene_end is not None
        and (request.start > planned_clip.hook_scene_start + 0.001 or request.end < planned_clip.hook_scene_end - 0.001)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip boundary must continue to contain the hook scene",
        )

    if manual_edit:
        update_clip_plan_boundary(
            document,
            clip_id,
            start=request.start,
            end=request.end,
            transcript_excerpt=planned_clip.transcript_excerpt,
        )
        touch_manual_document(document)
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        return ClipPlanActionResponse(jobId=job.id, status=job.status)

    job.status = "preparing_clip_review"
    job.progress = PROGRESS_MAP["preparing_clip_review"]
    job.current_step = "調整した範囲の確認動画を準備中"
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    document.state = "preparing"
    document.source_duration = source_duration
    write_clip_plan(
        document,
        clip_plan_output_path(paths.job_outputs(job_id)),
    )
    db.commit()
    db.refresh(job)

    try:
        enqueue_boundary_update(
            job.id,
            clip_id,
            request.start,
            request.end,
        )
    except Exception as exc:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue clip plan boundary adjustment",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/hook-scene",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_clip_plan_hook_scene(
    job_id: str,
    clip_id: str,
    request: ClipPlanHookSceneUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_hook_scene_update: ClipPlanHookSceneUpdateEnqueue = Depends(get_enqueue_clip_plan_hook_scene_update),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    manual_edit = job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    )
    if job.status != "awaiting_clip_review" and not manual_edit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting hook scene adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    expected_state = "manual_editing" if manual_edit else "awaiting_review"
    if document.state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting hook scene adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    if request.start is not None and request.end is not None:
        video = db.get(Video, job.video_id)
        if video is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="source video record is unavailable",
            )
        if video.has_audio is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="hook scene is unavailable for a source video without audio",
            )
        if request.start < planned_clip.start - 0.001 or request.end > planned_clip.end + 0.001:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="hook scene must stay within the selected clip",
            )
        short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
        if planned_clip.type == "short" and hook_scene_newly_exceeds_short_limit(
            clip_duration=planned_clip.duration,
            hook_duration=request.end - request.start,
            short_max_duration=short_max_duration,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=("hook scene would exceed the configured short maximum duration"),
            )

    if manual_edit:
        try:
            update_clip_plan_hook_scene_document(
                document,
                clip_id,
                start=request.start,
                end=request.end,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        touch_manual_document(document)
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        return ClipPlanActionResponse(jobId=job.id, status=job.status)

    job.status = "preparing_clip_review"
    job.progress = PROGRESS_MAP["preparing_clip_review"]
    job.current_step = "冒頭フック映像の確認動画を準備中"
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    document.state = "preparing"
    write_clip_plan(
        document,
        clip_plan_output_path(paths.job_outputs(job_id)),
    )
    db.commit()
    db.refresh(job)

    try:
        enqueue_hook_scene_update(
            job.id,
            clip_id,
            request.start,
            request.end,
        )
    except Exception as exc:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue hook scene adjustment",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.post(
    "/{job_id}/clip-plan/reselect",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reselect_clip_plan(
    job_id: str,
    request: ClipPlanReselectionRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_reselection: ClipPlanReselectionEnqueue = Depends(get_enqueue_clip_plan_reselection),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting reselection",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    previous_settings = dict(job.settings_json or {})
    settings_payload = dict(previous_settings)
    settings_payload.update(
        request.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
    )
    validated_settings = _validated_persisted_job_settings(settings_payload)
    job.settings_json = validated_settings.model_dump(
        by_alias=True,
        mode="json",
    )
    job.status = "reselecting_clips"
    job.progress = PROGRESS_MAP["reselecting_clips"]
    job.current_step = CURRENT_STEP_MAP["reselecting_clips"]
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    document.state = "reselecting"
    write_clip_plan(
        document,
        clip_plan_output_path(paths.job_outputs(job_id)),
    )
    db.commit()
    db.refresh(job)

    try:
        enqueue_reselection(job.id)
    except Exception as exc:
        job.settings_json = previous_settings
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue clip plan reselection",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.post(
    "/{job_id}/clip-plan/approve",
    response_model=ClipPlanActionResponse,
)
def approve_clip_plan(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_job: JobEnqueue = Depends(get_enqueue_job),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    ):
        document = _get_clip_plan_or_404(job_id, paths)
        if document.state != "manual_editing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="manual clip plan is not editable",
            )
        if not document.clips:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="manual clip plan must contain at least one clip",
            )
        for clip in document.clips:
            _validate_manual_clip_range(
                video,
                document,
                start=clip.start,
                end=clip.end,
            )
        previous_settings = dict(job.settings_json or {})
        try:
            next_settings = _validated_persisted_job_settings(
                manual_plan_settings(document, previous_settings)
            ).model_dump(by_alias=True, mode="json")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        job.settings_json = next_settings
        job.status = "queued"
        job.progress = PROGRESS_MAP["queued"]
        job.current_step = CURRENT_STEP_MAP["queued"]
        job.error_code = None
        job.error_message = None
        job.updated_at = utc_now()
        document.state = "preparing"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        db.refresh(job)
        try:
            enqueue_job(job.id)
        except Exception as exc:
            job.settings_json = previous_settings
            job.status = "awaiting_manual_edit"
            job.progress = PROGRESS_MAP["awaiting_manual_edit"]
            job.current_step = CURRENT_STEP_MAP["awaiting_manual_edit"]
            job.updated_at = utc_now()
            document.state = "manual_editing"
            write_clip_plan(
                document,
                clip_plan_output_path(paths.job_outputs(job_id)),
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="could not queue manual clip plan",
            ) from exc
        return ClipPlanActionResponse(jobId=job.id, status=job.status)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting approval",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    output_dir = paths.job_outputs(job_id)
    selected_payload = _read_json_if_exists(output_dir / "selected_clips.json")
    transcript_payload = _read_json_if_exists(output_dir / "transcript_segments.json")
    if not isinstance(selected_payload, dict) or not isinstance(
        transcript_payload,
        list,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="clip plan source artifacts are unavailable",
        )
    selection = CandidateSelection.model_validate(selected_payload)
    transcript_segments = [TranscriptSegment.model_validate(item) for item in transcript_payload]
    transcript_segments = repair_known_transcript_artifact_segments(transcript_segments)
    review_document = build_subtitle_review(
        job.id,
        selection,
        transcript_segments,
        short_max_duration=float((job.settings_json or {}).get("shortMaxDuration", 75.0)),
        render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
        short_overlay_title_mode=_short_overlay_title_mode(dict(job.settings_json or {})),
        short_layout=_short_layout(dict(job.settings_json or {})),
        short_top_banner_enabled=bool((job.settings_json or {}).get("shortTopBannerEnabled", False)),
        short_bottom_banner_enabled=bool((job.settings_json or {}).get("shortBottomBannerEnabled", False)),
        render_settings=dict(job.settings_json or {}),
        source_width=video.width,
        source_height=video.height,
    )
    planned_titles = {clip.id: clip.title for clip in document.clips}
    for clip in review_document.clips:
        if clip.id in planned_titles:
            clip.title = planned_titles[clip.id]
            clip.original_title = planned_titles[clip.id]
    _persist_subtitle_review(review_document, paths)
    write_clip_plan(
        mark_clip_plan_approved(document),
        clip_plan_output_path(output_dir),
    )
    if _job_quality_gate_mode(job, output_dir) == "auto":
        previous_settings = dict(job.settings_json or {})
        claimed_settings = {
            **previous_settings,
            AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING: True,
        }
        claim = db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == "awaiting_clip_review",
            )
            .values(
                settings_json=claimed_settings,
                status="queued",
                progress=PROGRESS_MAP["queued"],
                current_step=CURRENT_STEP_MAP["queued"],
                error_code=None,
                error_message=None,
                updated_at=utc_now(),
            )
        )
        if claim.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="clip plan approval is already being processed",
            )
        db.commit()
        db.refresh(job)
        try:
            enqueue_job(job.id)
        except Exception:
            job.settings_json = previous_settings
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
            job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
        else:
            return ClipPlanActionResponse(jobId=job.id, status=job.status)
    job.status = "awaiting_subtitle_review"
    job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
    job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)
    with subtitle_review_document_lock(output_dir):
        review_document = _get_subtitle_review_or_404(job.id, paths)
        review_document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=review_document,
            paths=paths,
        )
    review_document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=review_document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    _write_content_quality_gate(
        job=job,
        document=review_document,
        output_dir=output_dir,
    )
    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.get("/{job_id}/subtitle-review", response_model=SubtitleReviewDocument)
def get_subtitle_review(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    output_dir = paths.job_outputs(job_id)
    queued_previews: list[tuple[str, str]] = []
    refresh_quality_gate = False
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        document = _get_subtitle_review_or_404(job_id, paths)
        if job.status == "awaiting_subtitle_review" and document.state == "awaiting_review":
            document, settings_changed = _hydrate_subtitle_review_render_settings(
                document,
                job,
                video,
            )
            document, queued_previews, preview_changed = refresh_subtitle_review_preview_states(
                job=job,
                video=video,
                document=document,
                paths=paths,
            )
            if settings_changed or preview_changed:
                _write_subtitle_review_unlocked(document, paths)
                refresh_quality_gate = True
        else:
            document = document.model_copy(deep=True)
            document, _settings_changed = _hydrate_subtitle_review_render_settings(
                document,
                job,
                video,
            )
            document = _hydrate_legacy_subtitle_review_preview_urls(
                document,
                paths,
            )
    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    refresh_quality_gate = refresh_quality_gate or bool(queued_previews)
    if (
        refresh_quality_gate
        or not quality_gate_decision_path(output_dir, "content").is_file()
    ):
        _write_content_quality_gate(
            job=job,
            document=document,
            output_dir=output_dir,
        )
    return document


@router.get(
    "/{job_id}/subtitle-review/clips/{clip_id}/title-hook-suggestions",
    response_model=TitleHookSuggestionsDocument,
)
def get_title_hook_suggestions(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_suggestions: TitleHookSuggestionsEnqueue = Depends(
        get_enqueue_title_hook_suggestions
    ),
) -> TitleHookSuggestionsDocument:
    job = _get_job_or_404(db, job_id)
    review = _get_subtitle_review_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in review.clips):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subtitle review clip not found",
        )
    artifact = _get_title_hook_suggestions_or_404(job_id, clip_id, paths)
    if (
        artifact.state in {"queued", "generating"}
        and job.status == "awaiting_subtitle_review"
        and review.state == "awaiting_review"
    ):
        request_path = title_hook_suggestion_input_path(
            paths.job_outputs(job_id),
            clip_id,
        )
        try:
            generation_input = load_title_hook_suggestion_input(request_path)
        except (OSError, ValueError, json.JSONDecodeError):
            generation_input = None
        if (
            generation_input is not None
            and generation_input.input_hash == artifact.input_hash
            and generation_input.draft_hash == artifact.draft_hash
        ):
            try:
                enqueue_suggestions(job_id, clip_id, artifact.input_hash)
            except Exception:
                return artifact
    return artifact


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/title-hook-suggestions",
    response_model=TitleHookSuggestionsDocument,
)
def create_title_hook_suggestions(
    job_id: str,
    clip_id: str,
    request: TitleHookSuggestionRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_suggestions: TitleHookSuggestionsEnqueue = Depends(
        get_enqueue_title_hook_suggestions
    ),
) -> TitleHookSuggestionsDocument:
    job = _get_job_or_404(db, job_id)
    if db.get(Video, job.video_id) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    state_path = title_hook_suggestions_path(output_dir, clip_id)
    request_path = title_hook_suggestion_input_path(output_dir, clip_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        try:
            generation_input = build_title_hook_suggestion_input(
                document,
                clip_id,
                [
                    TitleHookDraftSegment(
                        segmentId=segment.segment_id,
                        text=segment.text,
                    )
                    for segment in request.segments
                ],
                model=str((job.settings_json or {}).get("titleHookModel") or "codex-default"),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip or segment not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        existing_artifact: TitleHookSuggestionsDocument | None = None
        if state_path.is_file():
            try:
                existing_artifact = load_title_hook_suggestions(state_path)
            except (OSError, ValueError, json.JSONDecodeError):
                existing_artifact = None
        previous_thread_id = existing_artifact.thread_id if existing_artifact is not None else None
        cached: TitleHookSuggestionsDocument | None = (
            None if request.force_regenerate else existing_artifact
        )
        if cached is not None:
            if (
                cached.input_hash == generation_input.input_hash
                and cached.draft_hash == generation_input.draft_hash
            ):
                if cached.state in {"ready", "failed"}:
                    return cached
                write_title_hook_suggestion_input(generation_input, request_path)
                queued = cached
            else:
                cached = None

        if cached is None:
            write_title_hook_suggestion_input(generation_input, request_path)
            queued = queued_title_hook_suggestions(
                generation_input,
                thread_id=previous_thread_id,
            )
            write_title_hook_suggestions(queued, state_path)

    try:
        enqueue_suggestions(job_id, clip_id, generation_input.input_hash)
    except Exception:
        with subtitle_review_document_lock(output_dir):
            active = load_title_hook_suggestions(state_path)
            if (
                active.input_hash == generation_input.input_hash
                and active.draft_hash == generation_input.draft_hash
            ):
                active = failed_title_hook_suggestions(
                    generation_input,
                    "could not queue title/hook generation",
                )
                write_title_hook_suggestions(active, state_path)
        return active
    return queued


@router.get("/{job_id}/subtitle-review/banner-assets/{position}")
def get_subtitle_review_banner_asset(
    job_id: str,
    position: Literal["top", "bottom"],
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    default_path = DEFAULT_SHORT_TOP_BANNER_PATH if position == "top" else DEFAULT_SHORT_BOTTOM_BANNER_PATH
    asset_path = resolve_banner_path(job.settings_json, position, default_path, paths)
    if not asset_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"short {position} banner asset not found",
        )
    return FileResponse(asset_path, media_type="image/png")


@router.patch(
    "/{job_id}/subtitle-review/settings",
    response_model=SubtitleReviewDocument,
)
def update_subtitle_review_settings(
    job_id: str,
    request: SubtitleReviewSettingsUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )

        settings = dict(job.settings_json or {})
        previous_top_banner_enabled = bool(settings.get("shortTopBannerEnabled", False))
        short_overlay_title_mode = _short_overlay_title_mode(settings)
        short_layout = request.short_layout or _short_layout(settings)
        if previous_top_banner_enabled and not request.short_top_banner_enabled:
            short_overlay_title_mode = "always"
        settings["shortTopBannerEnabled"] = request.short_top_banner_enabled
        settings["shortBottomBannerEnabled"] = request.short_bottom_banner_enabled
        settings["shortOverlayTitleMode"] = short_overlay_title_mode
        settings["shortLayout"] = short_layout
        document = update_review_render_settings(
            document,
            render_mode=str(settings.get("mode", "high_quality")),
            short_overlay_title_mode=short_overlay_title_mode,
            short_layout=short_layout,
            short_top_banner_enabled=request.short_top_banner_enabled,
            short_bottom_banner_enabled=request.short_bottom_banner_enabled,
            render_settings=settings,
            source_width=video.width,
            source_height=video.height,
        )
        job.settings_json = settings
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids={clip.id for clip in document.clips if clip.type == "short"},
        )
        _write_subtitle_review_unlocked(document, paths)
    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.post(
    "/{job_id}/subtitle-review/reopen",
    response_model=SubtitleReviewDocument,
)
def reopen_subtitle_review(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    document = _reopen_job_subtitle_review(job, video, paths)
    db.commit()
    return document


@router.get("/{job_id}/subtitle-review/clips/{clip_id}/preview-video")
def get_subtitle_review_preview_video(
    job_id: str,
    clip_id: str,
    spec_hash: str | None = Query(default=None, alias="specHash"),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    output_dir = paths.job_outputs(job_id)
    queued_previews: list[tuple[str, str]] = []
    legacy_preview_path: Path | None = None
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        document = _get_subtitle_review_or_404(job_id, paths)
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            )
        if document.state != "awaiting_review" and clip.preview_spec_hash is None and spec_hash is None:
            candidate_legacy_path = subtitle_review_preview_path(
                output_dir,
                clip_id,
            )
            if _legacy_subtitle_review_preview_is_available(candidate_legacy_path):
                legacy_preview_path = candidate_legacy_path
        if job.status == "awaiting_subtitle_review" and document.state == "awaiting_review":
            document, queued_previews = _refresh_subtitle_review_previews_unlocked(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_ids={clip_id},
            )
    if legacy_preview_path is not None:
        return FileResponse(
            legacy_preview_path,
            media_type="video/mp4",
            headers={"Cache-Control": "no-store"},
        )
    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    clip = next(item for item in document.clips if item.id == clip_id)
    if spec_hash is not None and clip.preview_spec_hash != spec_hash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subtitle review preview revision not found",
        )
    if clip.preview_state != "ready" or clip.preview_spec_hash is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "subtitle_review_preview_not_ready",
                "message": "現在の編集内容のプレビューを準備中です。",
            },
        )
    preview_paths = exact_subtitle_review_preview_paths(
        paths.job_outputs(job_id),
        clip_id,
        clip.preview_spec_hash,
    )
    if not exact_subtitle_review_preview_is_ready(
        preview_paths,
        clip.preview_spec_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "subtitle_review_preview_not_ready",
                "message": "現在の編集内容のプレビューを準備中です。",
            },
        )
    return FileResponse(
        preview_paths.video_path,
        media_type="video/mp4",
        headers={"Cache-Control": ("public, max-age=31536000, immutable" if spec_hash is not None else "no-store")},
    )


@router.get("/{job_id}/subtitle-review/clips/{clip_id}/live-preview-video")
def get_subtitle_review_live_preview_video(
    job_id: str,
    clip_id: str,
    spec_hash: str = Query(alias="specHash"),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    output_dir = paths.job_outputs(job_id)
    queued_previews: list[tuple[str, str]] = []
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        document = _get_subtitle_review_or_404(job_id, paths)
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            )
        if job.status == "awaiting_subtitle_review" and document.state == "awaiting_review":
            document, queued_previews = _refresh_subtitle_review_previews_unlocked(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_ids={clip_id},
            )
    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    clip = next(item for item in document.clips if item.id == clip_id)
    if clip.live_preview_spec_hash != spec_hash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subtitle review live preview revision not found",
        )
    live_paths = live_subtitle_review_preview_paths(
        output_dir,
        clip_id,
        spec_hash,
    )
    if not live_subtitle_review_preview_is_ready(live_paths, spec_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "subtitle_review_live_preview_not_ready",
                "message": "即時編集用の映像を準備中です。",
            },
        )
    return FileResponse(
        live_paths.video_path,
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/preview/retry",
    response_model=SubtitleReviewDocument,
)
def retry_subtitle_review_preview(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    output_dir = paths.job_outputs(job_id)
    queued_previews: list[tuple[str, str]] = []
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting preview retry",
            )
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            )
        try:
            _spec, current_hash, _inputs = current_subtitle_review_preview_spec(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_id=clip_id,
            )
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review preview inputs are unavailable",
            ) from exc

        if clip.preview_spec_hash == current_hash and clip.preview_state in {
            "queued",
            "rendering",
            "ready",
        }:
            return document
        if clip.preview_spec_hash != current_hash:
            document, _auto_queued = _refresh_subtitle_review_previews_unlocked(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_ids={clip_id},
            )
            clip = next(item for item in document.clips if item.id == clip_id)
            if clip.preview_state == "ready":
                return document
        try:
            exact_subtitle_review_preview_error_path(
                output_dir,
                clip_id,
                current_hash,
            ).unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not reset subtitle review preview",
            ) from exc
        clip.preview_state = "queued"
        clip.preview_spec_hash = current_hash
        clip.preview_video_url = None
        clip.preview_error = None
        clip.confirmed = False
        document.confirmed_clip_count = sum(1 for item in document.clips if item.confirmed)
        queued_previews = [(clip_id, current_hash)]
        _write_subtitle_review_unlocked(document, paths)

    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.patch(
    "/{job_id}/subtitle-review/clips/{clip_id}/hook-scene",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_subtitle_review_hook_scene(
    job_id: str,
    clip_id: str,
    request: ClipPlanHookSceneUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_hook_scene_update: SubtitleReviewHookSceneUpdateEnqueue = Depends(get_enqueue_subtitle_review_hook_scene_update),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting hook scene adjustment",
            )
        if (
            request.start is not None
            and request.end is not None
            and video.has_audio is False
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="hook scene is unavailable for a source video without audio",
            )
        validation_document = document.model_copy(deep=True)
        validation_document.short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
        try:
            update_review_hook_scene(
                validation_document,
                clip_id,
                start=request.start,
                end=request.end,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        job.status = "preparing_subtitle_review"
        job.progress = PROGRESS_MAP["preparing_subtitle_review"]
        job.current_step = "冒頭フック映像の確認動画を準備中"
        job.error_code = None
        job.error_message = None
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)

    try:
        enqueue_hook_scene_update(
            job.id,
            clip_id,
            request.start,
            request.end,
        )
    except Exception as exc:
        job.status = "awaiting_subtitle_review"
        job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
        job.updated_at = utc_now()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue subtitle review hook scene adjustment",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.patch(
    "/{job_id}/subtitle-review/clips/{clip_id}/content",
    response_model=SubtitleReviewDocument,
)
def update_subtitle_review_clip_content(
    job_id: str,
    clip_id: str,
    request: SubtitleReviewClipContentUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        try:
            style_updates: dict[str, object] = {}
            if "title_style" in request.model_fields_set:
                style_updates["title_style"] = request.title_style
            if "hook_style" in request.model_fields_set:
                style_updates["hook_style"] = request.hook_style
            if "subtitle_style" in request.model_fields_set:
                style_updates["subtitle_style"] = request.subtitle_style
            if "subtitle_styles" in request.model_fields_set:
                style_updates["subtitle_styles"] = request.subtitle_styles
            document = update_review_clip_content(
                document,
                clip_id,
                title=request.title,
                hook_text=request.hook_text,
                hook_duration_seconds=request.hook_duration_seconds,
                thumbnail_kicker=request.thumbnail_kicker,
                thumbnail_line1=request.thumbnail_line1,
                thumbnail_line2=request.thumbnail_line2,
                thumbnail_frame_seconds=request.thumbnail_frame_seconds,
                **style_updates,
            )
            document, _contract_changed = refresh_review_render_contract(
                document,
                render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
                render_settings=dict(job.settings_json or {}),
                source_width=video.width,
                source_height=video.height,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids={clip_id},
        )
        _write_subtitle_review_unlocked(document, paths)
    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.patch(
    "/{job_id}/subtitle-review/clips/{clip_id}/framing",
    response_model=SubtitleReviewDocument,
)
def update_subtitle_review_clip_framing(
    job_id: str,
    clip_id: str,
    request: SubtitleReviewClipFramingUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        try:
            document = update_review_clip_framing(
                document,
                clip_id,
                framing_offset_x=request.framing_offset_x,
                framing_offset_y=request.framing_offset_y,
                framing_zoom=request.framing_zoom,
            )
            document, _contract_changed = refresh_review_render_contract(
                document,
                render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
                render_settings=dict(job.settings_json or {}),
                source_width=video.width,
                source_height=video.height,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids={clip_id},
        )
        _write_subtitle_review_unlocked(document, paths)
    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/convert-to-short",
    response_model=SubtitleReviewDocument,
)
def convert_subtitle_review_clip_to_short(
    job_id: str,
    clip_id: str,
    request: SubtitleReviewConvertToShortRequest | None = None,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        selection_payload = _read_json_if_exists(output_dir / "selected_clips.json")
        try:
            selection = CandidateSelection.model_validate(selection_payload or {})
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        selection = apply_reviewed_clip_content(selection, document)
        candidate = next(
            (item for item in selection.normal_clips if item.id == clip_id),
            None,
        )
        if candidate is None or selection.shorts or len(selection.normal_clips) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="isolated normal clip data is unavailable",
            )

        review_clip = next((item for item in document.clips if item.id == clip_id), None)
        if review_clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            )
        source_duration = review_clip.end - review_clip.start
        supplied_range = bool(
            request is not None
            and request.start_seconds is not None
            and request.end_seconds is not None
        )
        if supplied_range:
            assert request is not None
            assert request.start_seconds is not None
            assert request.end_seconds is not None
            if request.end_seconds > source_duration + 0.001:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="short range must stay within the source normal clip",
                )
            short_start = review_clip.start + request.start_seconds
            short_end = review_clip.start + request.end_seconds
        else:
            hook_duration = 0.0
            if review_clip.hook_scene_start is not None and review_clip.hook_scene_end is not None:
                hook_duration = review_clip.hook_scene_end - review_clip.hook_scene_start
            if review_clip.duration + hook_duration > document.short_max_duration + 0.001:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "startSeconds and endSeconds are required when the source normal clip "
                        f"exceeds {document.short_max_duration:g} seconds"
                    ),
                )
            short_start = review_clip.start
            short_end = review_clip.end

        try:
            document = convert_review_clip_to_short(
                document,
                clip_id,
                start=short_start,
                end=short_end,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        retained_segments = sorted(document.segments, key=lambda item: item.index)
        segment_indices = [segment.index for segment in retained_segments]
        transcript_text = " ".join(
            segment.text.strip() for segment in retained_segments if segment.text.strip()
        )
        speech_seconds = sum(
            max(0.0, min(segment.end, short_end) - max(segment.start, short_start))
            for segment in retained_segments
        )
        duration = short_end - short_start
        converted_clip = document.clips[0]
        settings = dict(job.settings_json or {})
        posting_copy = build_youtube_posting_copy(
            clip_type="short",
            source_title=str(settings.get("youtubeSourceTitle") or ""),
            source_url=str(settings.get("youtubeSourceUrl") or ""),
            profile=settings.get("youtubePostingProfile"),
            fallback_description=candidate.youtube_description or "",
            topic_hashtags=candidate.youtube_tags,
        )
        converted_clip.youtube_description = posting_copy.description
        converted_clip.youtube_hashtags = posting_copy.hashtags
        converted_clip.youtube_tags = posting_copy.tags
        candidate_payload = candidate.model_dump(mode="python")
        candidate_payload.update(
            {
                "type": "short",
                "start": short_start,
                "end": short_end,
                "duration": duration,
                "transcript_text": transcript_text,
                "segment_start_index": min(segment_indices) if segment_indices else None,
                "segment_end_index": max(segment_indices) if segment_indices else None,
                "transcript_char_count": len(transcript_text),
                "speech_seconds": round(speech_seconds, 6),
                "silence_ratio": round(max(0.0, 1.0 - (speech_seconds / duration)), 6),
                "hook_scene_start": converted_clip.hook_scene_start,
                "hook_scene_end": converted_clip.hook_scene_end,
                "original_start": short_start,
                "original_end": short_end,
                "refined_start": short_start,
                "refined_end": short_end,
                "boundary_refined": False,
                "boundary_refinement_reason": None,
                "boundary_expansion_seconds": 0.0,
                "clip_plan_recommended_start": short_start,
                "clip_plan_recommended_end": short_end,
                "clip_plan_boundary_adjusted": False,
                "selection_reason": "completed_normal_to_short",
                "youtube_description": posting_copy.description,
                "youtube_hashtags": posting_copy.hashtags,
                "youtube_tags": posting_copy.tags,
            }
        )
        short_candidate = Candidate.model_validate(candidate_payload)
        selection = selection.model_copy(
            update={
                "normal_clips": [],
                "shorts": [short_candidate],
                "requested_normal_count": 0,
                "requested_short_count": 1,
                "normal_hard_gate_passed_count": 0,
                "short_hard_gate_passed_count": 1,
            }
        )

        settings.update(
            {
                "normalClipCount": 0,
                "shortCount": 1,
                "normalClipTimeRanges": [],
                "shortClipTimeRanges": [
                    {
                        "startSeconds": short_candidate.start,
                        "endSeconds": short_candidate.end,
                    }
                ],
                "manualClipMetadata": [
                    {
                        "id": short_candidate.id,
                        "type": "short",
                        "title": short_candidate.title or short_candidate.overlay_title or "",
                        "startSeconds": short_candidate.start,
                        "endSeconds": short_candidate.end,
                        "hookSceneStart": short_candidate.hook_scene_start,
                        "hookSceneEnd": short_candidate.hook_scene_end,
                    }
                ],
                "reeditTargetType": "short",
            }
        )
        document, _contract_changed = refresh_review_render_contract(
            document,
            render_mode=str(settings.get("mode", "high_quality")),
            render_settings=settings,
            source_width=video.width,
            source_height=video.height,
        )
        summary_payload = _read_json_if_exists(output_dir / "candidate_generation_summary.json")
        summary = dict(summary_payload) if isinstance(summary_payload, dict) else {}
        summary.update(
            {
                "source": "completed_normal_to_short",
                "normal_candidate_count": 0,
                "short_candidate_count": 1,
                "candidates_kept_by_type": {"normal": 0, "short": 1},
            }
        )

        artifact_snapshot = _snapshot_short_conversion_artifacts(output_dir)
        try:
            write_candidates([], output_dir / "normal_candidates.json")
            write_candidates([short_candidate], output_dir / "short_candidates.json")
            write_candidates([short_candidate], output_dir / "candidates.json")
            write_candidates([short_candidate], output_dir / "scored_candidates.json")
            write_selected_clips(selection, output_dir / "selected_clips.json")
            invalidate_quality_gate_decisions(output_dir, ("selection",))
            _write_json_payload(output_dir / "candidate_generation_summary.json", summary)
            job.settings_json = settings
            job.updated_at = utc_now()
            document, queued_previews = _refresh_subtitle_review_previews_unlocked(
                job=job,
                video=video,
                document=document,
                paths=paths,
                clip_ids={clip_id},
            )
            _write_subtitle_review_unlocked(document, paths)
            db.commit()
        except Exception:
            db.rollback()
            try:
                _restore_short_conversion_artifacts(artifact_snapshot)
            except OSError as restore_exc:
                raise RuntimeError(
                    "short conversion failed and artifact rollback could not be completed"
                ) from restore_exc
            raise
    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/apply",
    response_model=SubtitleReviewDocument,
)
def apply_subtitle_review_clip(
    job_id: str,
    clip_id: str,
    request: SubtitleReviewClipApplyRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
    enqueue_render: RenderEnqueue = Depends(get_enqueue_render_job),
) -> SubtitleReviewDocument:
    """Persist one clip's drafts and accept it without waiting for exact preview rendering."""
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip not found",
            )
        allowed_segment_ids = set(clip.segment_ids)
        requested_segment_ids = {segment_update.segment_id for segment_update in request.segments}
        if not requested_segment_ids.issubset(allowed_segment_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="subtitle segment does not belong to the selected clip",
            )

        affected_clip_ids = {clip_id}
        segments_by_id = {segment.id: segment for segment in document.segments}
        for segment_id in requested_segment_ids:
            segment = segments_by_id.get(segment_id)
            if segment is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="subtitle segment not found",
                )
            affected_clip_ids.update(segment.affected_clip_ids)

        draft_text_by_id = {
            segment_update.segment_id: segment_update.text for segment_update in request.segments
        }

        def revision_hash(text_by_id: dict[str, str]) -> str:
            return build_post_metadata_revision_hash(
                clip_id=clip.id,
                clip_type=clip.type,
                start=clip.start,
                end=clip.end,
                segments=[
                    {
                        "segmentId": segment.id,
                        "start": round(
                            min(clip.duration, max(0.0, segment.start - clip.start)),
                            3,
                        ),
                        "end": round(
                            min(
                                clip.duration,
                                max(0.0, segment.end - clip.start),
                            ),
                            3,
                        ),
                        "text": text_by_id.get(segment.id, segment.text).strip(),
                    }
                    for segment in sorted(
                        (segments_by_id[segment_id] for segment_id in clip.segment_ids),
                        key=lambda item: item.index,
                    )
                ],
            )

        current_revision_hash = revision_hash({})
        prospective_revision_hash = revision_hash(draft_text_by_id)
        revision_changed_in_save = current_revision_hash != prospective_revision_hash
        posting_fields = {
            "title_candidates",
            "recommended_title_id",
            "selected_title_id",
            "youtube_description",
            "youtube_hashtags",
            "youtube_tags",
            "description_evidence_segment_ids",
            "post_metadata_source",
            "post_metadata_revision_hash",
        }
        supplied_posting_fields = request.model_fields_set.intersection(posting_fields)
        stale_codex_payload = (
            request.post_metadata_source == "codex"
            and request.post_metadata_revision_hash != prospective_revision_hash
        )
        incoming_ai_state = bool(
            request.title_candidates
            or request.recommended_title_id
            or request.selected_title_id
            or request.description_evidence_segment_ids
            or request.post_metadata_revision_hash
        )
        stored_ai_state = bool(
            clip.post_metadata_source == "codex"
            or clip.title_candidates
            or clip.recommended_title_id
            or clip.selected_title_id
            or clip.description_evidence_segment_ids
            or clip.post_metadata_revision_hash
        )
        manualize_stale_payload = (
            revision_changed_in_save
            and request.post_metadata_source == "manual"
            and request.post_metadata_revision_hash != prospective_revision_hash
            and (incoming_ai_state or stored_ai_state)
        )
        if stale_codex_payload:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="AI proposal is stale; regenerate it from the current subtitles",
            )

        try:
            style_updates: dict[str, object] = {}
            if "title_style" in request.model_fields_set:
                style_updates["title_style"] = request.title_style
            if "hook_style" in request.model_fields_set:
                style_updates["hook_style"] = request.hook_style
            if "subtitle_style" in request.model_fields_set:
                style_updates["subtitle_style"] = request.subtitle_style
            if "subtitle_styles" in request.model_fields_set:
                style_updates["subtitle_styles"] = request.subtitle_styles
            if "publication_title" in request.model_fields_set:
                style_updates["publication_title"] = request.publication_title
            resolved_title_candidates = list(request.title_candidates)
            resolved_description_evidence_ids = list(
                request.description_evidence_segment_ids
            )
            resolved_artifact: TitleHookSuggestionsDocument | None = None
            if (
                not manualize_stale_payload
                and request.post_metadata_source == "codex"
                and request.post_metadata_revision_hash == prospective_revision_hash
            ):
                try:
                    artifact = load_title_hook_suggestions(
                        title_hook_suggestions_path(output_dir, clip_id)
                    )
                except (OSError, ValueError, json.JSONDecodeError):
                    artifact = None
                if (
                    artifact is not None
                    and artifact.state == "ready"
                    and artifact.revision_hash == prospective_revision_hash
                ):
                    resolved_artifact = artifact
                    evidence_by_id = {
                        suggestion.id: suggestion.evidence_segment_ids
                        for suggestion in artifact.suggestions
                    }
                    resolved_title_candidates = [
                        candidate.model_copy(
                            update={
                                "evidence_segment_ids": evidence_by_id.get(
                                    candidate.id,
                                    candidate.evidence_segment_ids,
                                )
                            }
                        )
                        for candidate in resolved_title_candidates
                    ]
                    if not resolved_description_evidence_ids:
                        resolved_description_evidence_ids = list(
                            artifact.description_evidence_segment_ids
                        )
            if not manualize_stale_payload:
                referenced_evidence_ids = set(resolved_description_evidence_ids)
                for candidate in resolved_title_candidates:
                    referenced_evidence_ids.update(candidate.evidence_segment_ids)
                if not referenced_evidence_ids.issubset(allowed_segment_ids):
                    raise ValueError("posting metadata referenced an unknown subtitle segment")

            for field_name in posting_fields:
                if field_name in supplied_posting_fields:
                    style_updates[field_name] = getattr(request, field_name)
            if resolved_artifact is not None:
                posting_copy = build_youtube_posting_copy(
                    clip_type=clip.type,
                    source_title=str(
                        (job.settings_json or {}).get("youtubeSourceTitle") or ""
                    ),
                    source_url=str(
                        (job.settings_json or {}).get("youtubeSourceUrl") or ""
                    ),
                    profile=(job.settings_json or {}).get("youtubePostingProfile"),
                    fallback_description=resolved_artifact.youtube_description,
                    topic_hashtags=resolved_artifact.hashtags,
                )
                style_updates.update(
                    {
                        "youtube_description": posting_copy.description,
                        "youtube_hashtags": posting_copy.hashtags,
                        "youtube_tags": posting_copy.tags,
                    }
                )
            elif supplied_posting_fields and request.post_metadata_source == "manual":
                # Manual edits keep their wording; source credits and default tags
                # must not disappear just because the copy is no longer AI-owned.
                manual_description = (
                    request.youtube_description if "youtube_description" in supplied_posting_fields else clip.youtube_description
                )
                manual_hashtags = request.youtube_hashtags if "youtube_hashtags" in supplied_posting_fields else clip.youtube_hashtags
                manual_tags = request.youtube_tags if "youtube_tags" in supplied_posting_fields else clip.youtube_tags
                posting_copy = build_youtube_posting_copy(
                    clip_type=clip.type,
                    source_title=str((job.settings_json or {}).get("youtubeSourceTitle") or ""),
                    source_url=str((job.settings_json or {}).get("youtubeSourceUrl") or ""),
                    profile=(job.settings_json or {}).get("youtubePostingProfile"),
                    fallback_description=manual_description,
                    topic_hashtags=manual_hashtags,
                )
                style_updates.update(
                    {
                        "youtube_description": posting_copy.description,
                        "youtube_hashtags": manual_hashtags or posting_copy.hashtags,
                        "youtube_tags": manual_tags or posting_copy.tags,
                    }
                )
            if "title_candidates" in supplied_posting_fields:
                style_updates["title_candidates"] = resolved_title_candidates
            if "description_evidence_segment_ids" in supplied_posting_fields or (
                request.post_metadata_source == "codex"
                and request.post_metadata_revision_hash == prospective_revision_hash
            ):
                style_updates["description_evidence_segment_ids"] = (
                    resolved_description_evidence_ids
                )
            stored_metadata_became_stale = (
                not supplied_posting_fields
                and clip.post_metadata_revision_hash
                and clip.post_metadata_revision_hash != prospective_revision_hash
            )
            if stored_metadata_became_stale:
                style_updates.update(
                    {
                        "youtube_description": "",
                        "youtube_hashtags": [],
                        "youtube_tags": [],
                    }
                )
            if manualize_stale_payload or stored_metadata_became_stale:
                style_updates.update(
                    {
                        "title_candidates": [],
                        "recommended_title_id": None,
                        "selected_title_id": None,
                        "description_evidence_segment_ids": [],
                        "post_metadata_source": "manual",
                        "post_metadata_revision_hash": None,
                    }
                )
            document = update_review_clip_content(
                document,
                clip_id,
                title=request.title,
                hook_text=request.hook_text,
                hook_duration_seconds=request.hook_duration_seconds,
                thumbnail_kicker=request.thumbnail_kicker,
                thumbnail_line1=request.thumbnail_line1,
                thumbnail_line2=request.thumbnail_line2,
                thumbnail_frame_seconds=request.thumbnail_frame_seconds,
                **style_updates,
            )
            if {
                "hook_scene_start",
                "hook_scene_end",
            }.issubset(request.model_fields_set):
                document = update_review_hook_scene(
                    document,
                    clip_id,
                    start=request.hook_scene_start,
                    end=request.hook_scene_end,
                )
            for segment_update in request.segments:
                document = update_review_segment(
                    document,
                    segment_update.segment_id,
                    segment_update.text,
                )
            document, _contract_changed = refresh_review_render_contract(
                document,
                render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
                render_settings=dict(job.settings_json or {}),
                source_width=video.width,
                source_height=video.height,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle review clip or segment not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids=affected_clip_ids,
        )
        document = confirm_review_clip(document, clip_id)
        _write_subtitle_review_unlocked(document, paths)
        document, auto_render_queued = _prepare_auto_review_render_unlocked(
            db=db,
            job=job,
            document=document,
            paths=paths,
        )

    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    if auto_render_queued:
        _enqueue_prepared_auto_review_render(
            db=db,
            job=job,
            document=document,
            paths=paths,
            enqueue_render=enqueue_render,
        )
    return document


@router.patch(
    "/{job_id}/subtitle-review/segments/{segment_id}",
    response_model=SubtitleReviewDocument,
)
def update_subtitle_review_segment(
    job_id: str,
    segment_id: str,
    request: SubtitleReviewSegmentUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting edits",
            )
        segment = next(
            (item for item in document.segments if item.id == segment_id),
            None,
        )
        if segment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle segment not found",
            )
        affected_clip_ids = set(segment.affected_clip_ids)
        try:
            document = update_review_segment(document, segment_id, request.text)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="subtitle segment not found",
            ) from exc
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids=affected_clip_ids,
        )
        _write_subtitle_review_unlocked(document, paths)
    return _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/confirm",
    response_model=SubtitleReviewDocument,
)
def confirm_subtitle_review_clip(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
    enqueue_render: RenderEnqueue = Depends(get_enqueue_render_job),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not editable",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting confirmation",
            )
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
            clip_ids={clip_id},
        )
        clip = next((item for item in document.clips if item.id == clip_id), None)
        if clip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="clip not found",
            )
        preview_ready = clip.preview_state == "ready"
        if preview_ready:
            try:
                document = confirm_review_clip(document, clip_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="clip not found",
                ) from exc
            _write_subtitle_review_unlocked(document, paths)
            document, auto_render_queued = _prepare_auto_review_render_unlocked(
                db=db,
                job=job,
                document=document,
                paths=paths,
            )
        else:
            auto_render_queued = False
    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    if not preview_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "subtitle_review_preview_not_ready",
                "message": "現在の編集内容のプレビュー完成後に確認してください。",
            },
        )
    if auto_render_queued:
        _enqueue_prepared_auto_review_render(
            db=db,
            job=job,
            document=document,
            paths=paths,
            enqueue_render=enqueue_render,
        )
    return document


@router.post(
    "/{job_id}/subtitle-review/finalize",
    response_model=SubtitleReviewFinalizeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def finalize_subtitle_review(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_render: RenderEnqueue = Depends(get_enqueue_render_job),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> SubtitleReviewFinalizeResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not awaiting finalization",
        )
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting finalization",
            )
        document = _get_subtitle_review_or_404(job_id, paths)
        if document.state != "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="subtitle review is not awaiting finalization",
            )
        document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=document,
            paths=paths,
        )
        previews_ready = all(clip.preview_state == "ready" for clip in document.clips)
        if previews_ready:
            try:
                document = queue_review_render(document)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
            _write_subtitle_review_unlocked(document, paths)
            job.status = "rendering_normal_clips"
            job.progress = PROGRESS_MAP["rendering_normal_clips"]
            job.current_step = CURRENT_STEP_MAP["rendering_normal_clips"]
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
    document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    if not previews_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "subtitle_review_preview_not_ready",
                "message": "現在の編集内容のプレビュー完成後に書き出してください。",
            },
        )
    try:
        enqueue_render(job.id, document.render_revision)
    except Exception as exc:
        with subtitle_review_document_lock(output_dir):
            latest = _get_subtitle_review_or_404(job_id, paths)
            if latest.state == "render_queued":
                latest.state = "awaiting_review"
                _write_subtitle_review_unlocked(latest, paths)
        job.status = "awaiting_subtitle_review"
        job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
        job.updated_at = utc_now()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue subtitle rendering",
        ) from exc

    return SubtitleReviewFinalizeResponse(jobId=job.id, status=job.status)


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> JobResultsResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="source video record is unavailable",
        )
    output_dir = paths.job_outputs(job.id)
    exports = []
    if not _job_publication_unresolved(job, paths):
        exports = [
            export
            for export in db.scalars(
                select(ExportItem).where(ExportItem.job_id == job.id)
            ).all()
            if _export_is_published(export, output_dir, paths)
        ]
    selected_by_candidate = _selected_clips_by_candidate(output_dir)
    audit = _audit_report(output_dir)
    audit_by_candidate = _audit_clips_by_candidate(audit)
    items = [
        _result_item(
            export,
            selected=selected_by_candidate.get(export.candidate_id or ""),
            metadata=_read_export_metadata(export, paths),
            audit_clip=audit_by_candidate.get(export.candidate_id or ""),
        )
        for export in exports
    ]
    normal_clips = [item for item in items if item.type == "normal"]
    shorts = [item for item in items if item.type == "short"]
    reedit_source_job_id: str | None = None
    review_path = subtitle_review_output_path(output_dir)
    if review_path.is_file():
        try:
            source_job_id = load_subtitle_review(review_path).reedit_source_job_id
        except (OSError, ValueError):
            source_job_id = None
        if source_job_id and db.get(Job, source_job_id) is not None:
            reedit_source_job_id = source_job_id

    return JobResultsResponse(
        jobId=job.id,
        zipDownloadUrl=f"/api/jobs/{job.id}/download.zip",
        canReopenForEditing=_can_reopen_subtitle_review(job, video, paths),
        reeditSourceJobId=reedit_source_job_id,
        auditSummary=_audit_summary(audit),
        normalClips=normal_clips,
        shorts=shorts,
    )


@router.get("/{job_id}/download.zip")
def download_job_zip(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    job = _get_job_or_404(db, job_id)
    if _job_publication_unresolved(job, paths):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="zip is unavailable while re-render publication is unresolved",
        )
    zip_path = paths.zip_path(job_id)
    if not zip_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="zip not found")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}.zip")
