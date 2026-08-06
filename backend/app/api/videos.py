from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.ids import make_id
from app.models import Video
from app.schemas import VideoUploadResponse
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.heatmap import (
    HeatmapSidecarError,
    heatmap_sidecar_filename,
    heatmap_sidecar_path,
    validate_heatmap_sidecar,
    write_heatmap_sidecar,
)


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


def _save_upload_with_size_limit(
    file: UploadFile,
    stored_path: Path,
    max_size_bytes: int,
) -> tuple[int, str]:
    digest = sha256()
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
                digest.update(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    return total_size, digest.hexdigest()


def _read_heatmap_upload(file: UploadFile, max_size_bytes: int) -> bytes:
    payload = bytearray()
    while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
        payload.extend(chunk)
        if len(payload) > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=_error_detail(
                    "heatmap_file_too_large",
                    "heatmap sidecar exceeds maximum size of "
                    f"{_format_byte_size(max_size_bytes)}",
                ),
            )
    return bytes(payload)


def _validate_heatmap_upload_filename(file: UploadFile, media_filename: str) -> None:
    expected = heatmap_sidecar_filename(media_filename)
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_error_detail(
                "heatmap_filename_required",
                "heatmap sidecar filename is required",
            ),
        )
    if file.filename != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_error_detail(
                "heatmap_filename_mismatch",
                f"heatmap sidecar filename must be {expected}",
            ),
        )


@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_video(
    file: UploadFile = File(...),
    heatmap: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    settings: Settings = Depends(get_settings),
) -> VideoUploadResponse:
    suffix = _validate_upload_metadata(file, settings)
    video_id = make_id("vid")
    stored_path = paths.uploads / f"{video_id}{suffix}"
    sidecar_path = heatmap_sidecar_path(stored_path)

    try:
        size_bytes, sha256_hex = _save_upload_with_size_limit(
            file,
            stored_path,
            settings.max_upload_size_bytes,
        )
        if heatmap is not None:
            original_filename = file.filename or stored_path.name
            _validate_heatmap_upload_filename(heatmap, original_filename)
            raw_sidecar = _read_heatmap_upload(
                heatmap,
                settings.max_heatmap_sidecar_size_bytes,
            )
            try:
                parsed_sidecar = validate_heatmap_sidecar(
                    raw_sidecar,
                    expected_filename=original_filename,
                    actual_size_bytes=size_bytes,
                    actual_sha256=sha256_hex,
                )
            except HeatmapSidecarError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_error_detail(exc.code, exc.message),
                ) from exc
            write_heatmap_sidecar(parsed_sidecar, sidecar_path)

        video = Video(
            id=video_id,
            original_filename=file.filename or stored_path.name,
            stored_path=str(stored_path),
        )
        db.add(video)
        db.commit()
    except Exception:
        db.rollback()
        sidecar_path.unlink(missing_ok=True)
        stored_path.unlink(missing_ok=True)
        raise

    return VideoUploadResponse(videoId=video.id, filename=video.original_filename)
