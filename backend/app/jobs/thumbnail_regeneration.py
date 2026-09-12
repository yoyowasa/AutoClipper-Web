from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.jobs.thumbnails import (
    read_export_metadata,
    thumbnail_output_path,
    write_export_metadata,
)
from app.jobs.thumbnail_frame_selection import select_thumbnail_frame_seconds
from app.models import ExportItem, Video
from app.render.render_thumbnail import ThumbnailRenderResult, render_normal_thumbnail
from app.storage.paths import StoragePaths, get_storage_paths


SessionFactory = Callable[[], Session]
NormalThumbnailRenderer = Callable[..., ThumbnailRenderResult]
ThumbnailFrameSelector = Callable[..., float]
THUMBNAIL_FACE_HEIGHT_RATIOS = {
    "standard": 0.25,
    "close": 0.34,
}


def _current_revision(payload: dict[str, Any]) -> int:
    value = payload.get("thumbnail_request_revision")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _metadata_path(export: ExportItem, paths: StoragePaths) -> Path:
    if not export.metadata_path:
        raise FileNotFoundError("thumbnail export metadata is unavailable")
    path = paths.resolve_stored_file(export.metadata_path)
    path.resolve(strict=False).relative_to(
        paths.job_outputs(export.job_id).resolve(strict=False)
    )
    if not path.is_file():
        raise FileNotFoundError("thumbnail export metadata is unavailable")
    return path


def _source_path(video: Video, paths: StoragePaths) -> Path:
    path = paths.resolve_stored_file(video.stored_path)
    if not path.is_file():
        raise FileNotFoundError("thumbnail source video is unavailable")
    return path


def _mark_failed_if_current(
    export: ExportItem,
    metadata_path: Path,
    *,
    revision: int,
    error_code: str,
) -> None:
    payload = read_export_metadata(export)
    if _current_revision(payload) != revision:
        return
    write_export_metadata(
        metadata_path,
        {
            **payload,
            "thumbnail_status": "failed",
            "thumbnail_error_code": error_code,
        },
    )


def run_export_thumbnail_regeneration(
    export_id: str,
    revision: int,
    *,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    normal_renderer: NormalThumbnailRenderer = render_normal_thumbnail,
    frame_selector: ThumbnailFrameSelector = select_thumbnail_frame_seconds,
) -> None:
    """Rebuild one normal thumbnail without re-rendering its completed video."""
    storage = paths or get_storage_paths()
    temp_output: Path | None = None
    with session_factory() as db:
        export = db.get(ExportItem, export_id)
        if export is None:
            return
        metadata_path: Path | None = None
        try:
            if export.type != "normal":
                raise ValueError("thumbnail regeneration supports normal clips only")
            metadata_path = _metadata_path(export, storage)
            payload = read_export_metadata(export)
            if (
                _current_revision(payload) != revision
                or payload.get("thumbnail_status") != "generating"
            ):
                return
            video = db.get(Video, export.video_id)
            if video is None:
                raise FileNotFoundError("thumbnail source video record is unavailable")
            source_path = _source_path(video, storage)
            frame_seconds = float(payload.get("thumbnail_frame_seconds", 0.0))
            variant_index = max(0, int(payload.get("thumbnail_variant_index", 0)))
            if bool(payload.get("thumbnail_advance_frame")):
                source_start = float(payload.get("start", 0.0))
                frame_seconds = frame_selector(
                    source_path,
                    clip_start=source_start,
                    clip_end=source_start + float(export.duration),
                    variant_index=variant_index,
                )
            if frame_seconds < 0 or frame_seconds > float(export.duration) + 0.001:
                raise ValueError("thumbnail frame must stay within the completed clip")
            source_start = float(payload.get("start", 0.0))
            source_timestamp = source_start + min(frame_seconds, float(export.duration))
            subject_anchor_x = float(payload.get("thumbnail_subject_anchor_x", 1.0))
            crop_mode = str(payload.get("thumbnail_crop_mode") or "standard")
            if crop_mode not in THUMBNAIL_FACE_HEIGHT_RATIOS:
                crop_mode = "standard"
            output_path = thumbnail_output_path(storage.job_outputs(export.job_id), export)
            output_path.resolve(strict=False).relative_to(
                storage.job_outputs(export.job_id).resolve(strict=False)
            )
            temp_output = output_path.with_name(
                f".{output_path.stem}.r{revision}.tmp{output_path.suffix}"
            )
            from app.models import Job
            job = db.get(Job, export.job_id)
            character_style = (job.settings_json or {}).get("normalThumbnailStyle") if job else None
            result = normal_renderer(
                source_path,
                temp_output,
                **({"character_style": character_style} if character_style is not None else {}),
                frame_time=source_timestamp,
                eyebrow=str(payload.get("thumbnail_kicker") or "").strip(),
                title_first_line=str(payload.get("thumbnail_line1") or "").strip(),
                title_second_line=str(payload.get("thumbnail_line2") or "").strip(),
                subject_anchor_x=min(1.0, max(0.0, subject_anchor_x)),
                face_height_ratio=THUMBNAIL_FACE_HEIGHT_RATIOS[crop_mode],
            )
            if result.path.resolve() != temp_output.resolve() or not temp_output.is_file():
                raise RuntimeError("thumbnail renderer returned an unpublished path")
            latest = read_export_metadata(export)
            if (
                _current_revision(latest) != revision
                or latest.get("thumbnail_status") != "generating"
            ):
                temp_output.unlink(missing_ok=True)
                return
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temp_output.replace(output_path)
            write_export_metadata(
                metadata_path,
                {
                    **latest,
                    "thumbnail_path": str(output_path),
                    "thumbnail_filename": output_path.name,
                    "thumbnail_status": "ready",
                    "thumbnail_source_time": round(result.source_timestamp, 3),
                    "thumbnail_source_time_basis": "source_video_absolute",
                    "thumbnail_width": result.width,
                    "thumbnail_height": result.height,
                    "thumbnail_template_version": "character_normal_v1" if character_style is not None else "raden_normal_v4",
                    "thumbnail_frame_seconds": round(frame_seconds, 3),
                    "thumbnail_variant_index": variant_index,
                    "thumbnail_crop_mode": crop_mode,
                    "thumbnail_advance_frame": False,
                    "thumbnail_render_revision": revision,
                    "thumbnail_error_code": None,
                },
            )
        except Exception as exc:
            if temp_output is not None:
                temp_output.unlink(missing_ok=True)
            if metadata_path is not None:
                _mark_failed_if_current(
                    export,
                    metadata_path,
                    revision=revision,
                    error_code=exc.__class__.__name__,
                )
