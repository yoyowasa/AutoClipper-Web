from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.queue import (
    ThumbnailRegenerationEnqueue,
    get_enqueue_thumbnail_regeneration,
)
from app.jobs.thumbnails import read_export_metadata, write_export_metadata
from app.models import ExportItem, Job
from app.schemas import ThumbnailRegenerationRequest, ThumbnailRegenerationResponse
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


def _thumbnail_file_or_404(export: ExportItem, paths: StoragePaths) -> Path:
    metadata = read_export_metadata(export)
    value = metadata.get("thumbnail_path")
    if metadata.get("thumbnail_status") not in {"ready", "generating"} or not isinstance(
        value,
        str,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail file not found",
        )
    thumbnail_path = paths.resolve_stored_file(value)
    try:
        thumbnail_path.resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail is not published",
        ) from None
    if not thumbnail_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail file not found",
        )
    return thumbnail_path


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


@router.get("/{export_id}/thumbnail")
def view_export_thumbnail(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    thumbnail_path = _thumbnail_file_or_404(export, paths)
    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.get("/{export_id}/thumbnail/download")
def download_export_thumbnail(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    thumbnail_path = _thumbnail_file_or_404(export, paths)
    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        filename=thumbnail_path.name,
    )


@router.post(
    "/{export_id}/thumbnail/regenerate",
    response_model=ThumbnailRegenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_export_thumbnail(
    export_id: str,
    request: ThumbnailRegenerationRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_thumbnail: ThumbnailRegenerationEnqueue = Depends(
        get_enqueue_thumbnail_regeneration
    ),
) -> ThumbnailRegenerationResponse:
    export = _get_export_or_404(db, export_id, paths)
    if export.type != "normal":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="thumbnail regeneration supports normal clips only",
        )
    if request.frame_seconds > float(export.duration) + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="thumbnail frame must stay within the completed clip",
        )
    if not export.metadata_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thumbnail export metadata is unavailable",
        )
    metadata_path = paths.resolve_stored_file(export.metadata_path)
    try:
        metadata_path.resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="export metadata is not published",
        ) from None
    if not metadata_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thumbnail export metadata is unavailable",
        )
    previous = read_export_metadata(export)
    try:
        revision = max(0, int(previous.get("thumbnail_request_revision", 0))) + 1
    except (TypeError, ValueError):
        revision = 1
    try:
        previous_variant_index = int(previous.get("thumbnail_variant_index", -1))
    except (TypeError, ValueError):
        previous_variant_index = -1
    variant_index = (
        (previous_variant_index + 1) % 6
        if request.advance_frame
        else max(0, previous_variant_index)
    )
    pending = {
        **previous,
        "thumbnail_status": "generating",
        "thumbnail_frame_seconds": round(request.frame_seconds, 3),
        "thumbnail_subject_anchor_x": round(request.subject_anchor_x, 3),
        "thumbnail_advance_frame": request.advance_frame,
        "thumbnail_variant_index": variant_index,
        "thumbnail_request_revision": revision,
        "thumbnail_error_code": None,
    }
    write_export_metadata(metadata_path, pending)
    try:
        enqueue_thumbnail(export.id, revision)
    except Exception as exc:
        write_export_metadata(metadata_path, previous)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue thumbnail regeneration",
        ) from exc
    return ThumbnailRegenerationResponse(
        exportId=export.id,
        status="generating",
        revision=revision,
    )
