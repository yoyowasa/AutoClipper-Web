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


def _result_item(export: ExportItem) -> ResultExportItem:
    url = f"/api/exports/{export.id}/download"
    return ResultExportItem(
        id=export.id,
        type=export.type,
        title=export.title,
        duration=export.duration,
        score=export.score,
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
def get_job_results(job_id: str, db: Session = Depends(get_db)) -> JobResultsResponse:
    job = _get_job_or_404(db, job_id)
    exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()
    normal_clips = [_result_item(export) for export in exports if export.type == "normal"]
    shorts = [_result_item(export) for export in exports if export.type == "short"]

    return JobResultsResponse(
        jobId=job.id,
        zipDownloadUrl=f"/api/jobs/{job.id}/download.zip",
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
