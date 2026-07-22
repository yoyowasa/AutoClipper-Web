from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.ids import make_id
from app.models import Video
from app.schemas import VideoUploadResponse
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api/videos", tags=["videos"])
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _safe_upload_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".bin"


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _format_byte_size(size_bytes: int) -> str:
    gibibyte = 1024**3
    mebibyte = 1024**2
    if size_bytes >= gibibyte and size_bytes % gibibyte == 0:
        return f"{size_bytes // gibibyte} GiB"
    if size_bytes >= mebibyte and size_bytes % mebibyte == 0:
        return f"{size_bytes // mebibyte} MiB"
    return f"{size_bytes} bytes"


def _validate_upload_metadata(file: UploadFile, settings: Settings) -> str:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail("upload_filename_required", "filename is required"),
        )

    suffix = _safe_upload_suffix(file.filename)
    if suffix not in settings.upload_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_error_detail(
                "invalid_file_type",
                f"unsupported video file extension: {suffix}",
            ),
        )

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in settings.upload_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_error_detail(
                "invalid_file_type",
                f"unsupported video content type: {content_type}",
            ),
        )
    return suffix


def _save_upload_with_size_limit(file: UploadFile, stored_path: Path, max_size_bytes: int) -> int:
    total_size = 0
    try:
        with stored_path.open("wb") as output_file:
            while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_error_detail(
                            "file_too_large",
                            "upload exceeds maximum size of "
                            f"{_format_byte_size(max_size_bytes)}",
                        ),
                    )
                output_file.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    return total_size


@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    settings: Settings = Depends(get_settings),
) -> VideoUploadResponse:
    suffix = _validate_upload_metadata(file, settings)
    video_id = make_id("vid")
    stored_path = paths.uploads / f"{video_id}{suffix}"

    _save_upload_with_size_limit(file, stored_path, settings.max_upload_size_bytes)

    video = Video(
        id=video_id,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
    )
    db.add(video)
    db.commit()

    return VideoUploadResponse(videoId=video.id, filename=video.original_filename)
