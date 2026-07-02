from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ExportItem
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/exports", tags=["exports"])


def _get_export_or_404(db: Session, export_id: str) -> ExportItem:
    export = db.get(ExportItem, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export not found")
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
    export = _get_export_or_404(db, export_id)
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
    export = _get_export_or_404(db, export_id)
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
    export = _get_export_or_404(db, export_id)
    return _stored_file_or_404(
        paths,
        export.subtitle_path,
        detail="subtitle file not found",
        media_type="text/plain",
    )
