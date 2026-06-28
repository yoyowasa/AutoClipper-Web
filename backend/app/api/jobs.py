from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.ids import make_id
from app.jobs.queue import JobEnqueue, get_enqueue_job
from app.models import ExportItem, Job, Video
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
        settings_json=request.settings,
    )
    db.add(job)
    db.commit()

    enqueue_job(job.id)

    return JobCreateResponse(jobId=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = _get_job_or_404(db, job_id)
    error = None
    if job.error_code or job.error_message:
        error = JobError(code=job.error_code or "unknown", message=job.error_message or "")

    return JobStatusResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        currentStep=job.current_step,
        details={},
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
