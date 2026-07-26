import json
import mimetypes
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio.openai_transcript_correction import TRANSCRIPT_CORRECTION_PROGRESS_FILENAME
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.select_candidates import CandidateSelection
from app.config import Settings, get_settings
from app.db import get_db
from app.ids import make_id
from app.jobs.clip_plan import (
    ClipPlanDocument,
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_approved,
    write_clip_plan,
)
from app.jobs.reedit_upload import (
    UploadSizeLimitExceeded,
    fingerprint_stream,
    matching_exports,
)
from app.jobs.queue import (
    ClipPlanBoundaryUpdateEnqueue,
    ClipPlanReselectionEnqueue,
    JobEnqueue,
    RenderEnqueue,
    get_enqueue_clip_plan_boundary_update,
    get_enqueue_clip_plan_reselection,
    get_enqueue_job,
    get_enqueue_render_job,
)
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    build_subtitle_review,
    confirm_review_clip,
    load_subtitle_review,
    queue_review_render,
    reopen_completed_review,
    subtitle_review_output_path,
    subtitle_review_preview_path,
    subtitle_review_preview_url,
    subtitle_review_summary_path,
    update_review_clip_content,
    update_review_segment,
    write_subtitle_review,
    write_subtitle_review_summary,
)
from app.models import ExportItem, Job, Video
from app.models import utc_now
from app.schemas import (
    ClipPlanActionResponse,
    ClipPlanBoundaryUpdateRequest,
    ClipPlanReselectionRequest,
    CompletedVideoReeditResponse,
    JobAuditSummary,
    JobCreateRequest,
    JobCreateResponse,
    JobError,
    JobResultsResponse,
    JobSettings,
    JobStatusResponse,
    ResultExportItem,
    SubtitleReviewFinalizeResponse,
    SubtitleReviewClipContentUpdateRequest,
    SubtitleReviewSegmentUpdateRequest,
)
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL_STATUSES = {"completed", "failed"}
NON_WORKER_STATUSES = {
    "uploaded",
    "queued",
    "awaiting_clip_review",
    "awaiting_subtitle_review",
}
DEFAULT_STALE_WORKER_SECONDS = 1800


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


def _persist_subtitle_review(document: SubtitleReviewDocument, paths: StoragePaths) -> None:
    output_dir = paths.job_outputs(document.job_id)
    write_subtitle_review(document, subtitle_review_output_path(output_dir))
    write_subtitle_review_summary(document, subtitle_review_summary_path(output_dir))


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
    return (
        all(path.is_file() for path in required_artifacts)
        and paths.resolve_stored_file(video.stored_path).is_file()
    )


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
    document = _get_subtitle_review_or_404(job.id, paths)
    if job.status == "awaiting_subtitle_review" and document.state == "awaiting_review":
        if not _reedit_artifacts_available(job.id, video, paths):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="source artifacts are unavailable",
            )
        return document
    if not _can_reopen_subtitle_review(job, video, paths):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="completed job cannot be reopened because source artifacts are unavailable",
        )
    try:
        document = reopen_completed_review(document)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    _persist_subtitle_review(document, paths)
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
    score = _number_or_none(
        _first_value(selected.get("score"), selected.get("final_score"), metadata.get("score"), export.score)
    )
    final_score = _number_or_none(
        _first_value(selected.get("final_score"), selected.get("score"), audit_clip.get("final_score"), score)
    )
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
        refinedEnd=_number_or_none(
            _first_value(metadata.get("refined_end"), selected.get("refined_end"), audit_clip.get("refined_end"))
        ),
        resolution=resolution,
        auditWarnings=audit_clip.get("warnings") if isinstance(audit_clip.get("warnings"), list) else [],
        subtitlePath=_first_value(metadata.get("subtitle_path"), export.subtitle_path),
        subtitleUrl=subtitle_url,
        metadataPath=export.metadata_path,
        metadataUrl=metadata_url,
        videoUrl=url,
        downloadUrl=url,
    )


def _read_json_if_exists(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _job_details(job: Job, paths: StoragePaths) -> dict[str, Any]:
    details: dict[str, Any] = {}
    output_dir = paths.job_outputs(job.id)
    audio_features = _read_json_if_exists(output_dir / "audio_features.json")
    if isinstance(audio_features, dict):
        for key in ("duration", "silence_ratio", "speech_seconds", "speech_density", "volume_peak"):
            if key in audio_features:
                details[key] = audio_features[key]

    transcript_segments = _read_json_if_exists(output_dir / "transcript_segments.json")
    if isinstance(transcript_segments, list):
        texts = [
            str(segment.get("text", "")).strip()
            for segment in transcript_segments
            if isinstance(segment, dict)
        ]
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
                "message": (
                    "このMP4に対応する完成済みjobが見つかりません。"
                    "同じPCで作成した未変更のAutoClipper出力を選択してください。"
                ),
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
            document = _reopen_job_subtitle_review(job, video, paths)
        except HTTPException as exc:
            if exc.status_code not in {
                status.HTTP_404_NOT_FOUND,
                status.HTTP_409_CONFLICT,
            }:
                raise
            unavailable_match_found = True
            continue
        db.commit()
        return CompletedVideoReeditResponse(
            jobId=job.id,
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
                    "対応するjobは見つかりましたが、元動画または編集データが残っていないため"
                    "再編集できません。"
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


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    enqueue_job: JobEnqueue = Depends(get_enqueue_job),
) -> JobCreateResponse:
    video = db.get(Video, request.video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="video not found")

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
        error = JobError(code=job.error_code or "unknown", message=job.error_message or "")

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


@router.get("/{job_id}/clip-plan", response_model=ClipPlanDocument)
def get_clip_plan(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    _get_job_or_404(db, job_id)
    return _get_clip_plan_or_404(job_id, paths)


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
    source_duration = float(
        (video.duration if video is not None else None)
        or document.source_duration
        or 0
    )
    if source_duration > 0 and end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )

    transcript_payload = _read_json_if_exists(
        paths.job_outputs(job_id) / "transcript_segments.json"
    )
    if not isinstance(transcript_payload, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="transcript segments are unavailable",
        )
    transcript_segments = [
        TranscriptSegment.model_validate(item)
        for item in transcript_payload
    ]
    return [
        segment
        for segment in transcript_segments
        if segment.end > start and segment.start < end
    ]


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
    enqueue_boundary_update: ClipPlanBoundaryUpdateEnqueue = Depends(
        get_enqueue_clip_plan_boundary_update
    ),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.state != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    if not any(clip.id == clip_id for clip in document.clips):
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
    enqueue_reselection: ClipPlanReselectionEnqueue = Depends(
        get_enqueue_clip_plan_reselection
    ),
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
    settings_payload.update(request.model_dump(by_alias=True, mode="json"))
    validated_settings = JobSettings.model_validate(settings_payload)
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
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting approval",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    output_dir = paths.job_outputs(job_id)
    selected_payload = _read_json_if_exists(output_dir / "selected_clips.json")
    transcript_payload = _read_json_if_exists(
        output_dir / "transcript_segments.json"
    )
    if not isinstance(selected_payload, dict) or not isinstance(
        transcript_payload,
        list,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="clip plan source artifacts are unavailable",
        )
    selection = CandidateSelection.model_validate(selected_payload)
    transcript_segments = [
        TranscriptSegment.model_validate(item)
        for item in transcript_payload
    ]
    review_document = build_subtitle_review(
        job.id,
        selection,
        transcript_segments,
    )
    for clip in review_document.clips:
        preview_path = subtitle_review_preview_path(output_dir, clip.id)
        if preview_path.is_file():
            clip.preview_video_url = subtitle_review_preview_url(
                job.id,
                clip.id,
            )
    _persist_subtitle_review(review_document, paths)
    write_clip_plan(
        mark_clip_plan_approved(document),
        clip_plan_output_path(output_dir),
    )
    job.status = "awaiting_subtitle_review"
    job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
    job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)
    return ClipPlanActionResponse(jobId=job.id, status=job.status)


@router.get("/{job_id}/subtitle-review", response_model=SubtitleReviewDocument)
def get_subtitle_review(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> SubtitleReviewDocument:
    _get_job_or_404(db, job_id)
    return _get_subtitle_review_or_404(job_id, paths)


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
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    _get_job_or_404(db, job_id)
    document = _get_subtitle_review_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in document.clips):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subtitle review clip not found")
    preview_path = subtitle_review_preview_path(paths.job_outputs(job_id), clip_id)
    if not preview_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subtitle review preview not found")
    return FileResponse(preview_path, media_type="video/mp4")


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
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    document = _get_subtitle_review_or_404(job_id, paths)
    try:
        document = update_review_clip_content(
            document,
            clip_id,
            title=request.title,
            hook_text=request.hook_text,
            hook_duration_seconds=request.hook_duration_seconds,
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
    _persist_subtitle_review(document, paths)
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
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    document = _get_subtitle_review_or_404(job_id, paths)
    try:
        document = update_review_segment(document, segment_id, request.text)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subtitle segment not found") from exc
    _persist_subtitle_review(document, paths)
    return document


@router.post(
    "/{job_id}/subtitle-review/clips/{clip_id}/confirm",
    response_model=SubtitleReviewDocument,
)
def confirm_subtitle_review_clip(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> SubtitleReviewDocument:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not editable",
        )
    document = _get_subtitle_review_or_404(job_id, paths)
    try:
        document = confirm_review_clip(document, clip_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found") from exc
    _persist_subtitle_review(document, paths)
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
) -> SubtitleReviewFinalizeResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_subtitle_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subtitle review is not awaiting finalization",
        )
    document = _get_subtitle_review_or_404(job_id, paths)
    try:
        document = queue_review_render(document)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    _persist_subtitle_review(document, paths)
    job.status = "rendering_normal_clips"
    job.progress = PROGRESS_MAP["rendering_normal_clips"]
    job.current_step = CURRENT_STEP_MAP["rendering_normal_clips"]
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)

    try:
        enqueue_render(job.id)
    except Exception as exc:
        document.state = "awaiting_review"
        _persist_subtitle_review(document, paths)
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
    exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()
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

    return JobResultsResponse(
        jobId=job.id,
        zipDownloadUrl=f"/api/jobs/{job.id}/download.zip",
        canReopenForEditing=_can_reopen_subtitle_review(job, video, paths),
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
    _get_job_or_404(db, job_id)
    zip_path = paths.zip_path(job_id)
    if not zip_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="zip not found")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}.zip")
