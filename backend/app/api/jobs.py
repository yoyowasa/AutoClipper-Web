import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ids import make_id
from app.jobs.queue import JobEnqueue, get_enqueue_job
from app.models import ExportItem, Job, Video
from app.models import utc_now
from app.schemas import (
    JobAuditSummary,
    JobCreateRequest,
    JobCreateResponse,
    JobError,
    JobResultsResponse,
    JobStatusResponse,
    ResultExportItem,
)
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL_STATUSES = {"completed", "failed"}
NON_WORKER_STATUSES = {"uploaded", "queued"}
DEFAULT_STALE_WORKER_SECONDS = 1800


def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


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


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> JobResultsResponse:
    job = _get_job_or_404(db, job_id)
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
