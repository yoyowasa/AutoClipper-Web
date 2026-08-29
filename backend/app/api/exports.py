from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.models import ExportItem, Job
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/exports", tags=["exports"])

_UNSTABLE_EXPORT_STATUSES = {
    "rendering_normal_clips",
    "rendering_shorts",
    "packaging_zip",
}
_UNSTABLE_EXPORT_ERROR_CODES = {
    "subtitle_rerender_rollback_failed",
    "worker_terminated_unexpectedly",
}


def _get_export_or_404(
    db: Session,
    export_id: str,
    paths: StoragePaths,
) -> ExportItem:
    export = db.get(ExportItem, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export not found")
    job = db.get(Job, export.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export job not found")
    if (
        job.status in _UNSTABLE_EXPORT_STATUSES
        or job.error_code in _UNSTABLE_EXPORT_ERROR_CODES
        or rerender_publication_is_unresolved(paths.job_outputs(job.id))
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="export is unavailable while re-render publication is unresolved",
        )
    try:
        paths.resolve_stored_file(export.video_path).resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="export is not published",
        ) from None
    return export


def _stored_file_or_404(paths: StoragePaths, value: str | None, *, detail: str, media_type: str) -> FileResponse:
    if not value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    path = paths.resolve_stored_file(value)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    video_path = paths.resolve_stored_file(export.video_path)
    if not video_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export file not found")

    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)


@router.get("/{export_id}/metadata")
def download_export_metadata(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    return _stored_file_or_404(
        paths,
        export.metadata_path,
        detail="metadata file not found",
        media_type="application/json",
    )


@router.get("/{export_id}/subtitle")
def download_export_subtitle(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    return _stored_file_or_404(
        paths,
        export.subtitle_path,
        detail="subtitle file not found",
        media_type="text/plain",
    )
