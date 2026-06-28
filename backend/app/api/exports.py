from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ExportItem
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = db.get(ExportItem, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export not found")

    video_path = paths.resolve_stored_file(export.video_path)
    if not video_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export file not found")

    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)
