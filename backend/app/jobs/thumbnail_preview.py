"""Prepare one source frame in the worker, then render unsaved image drafts."""

import json
import math
import tempfile
import time
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.db import SessionLocal
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.jobs.thumbnail_regeneration import THUMBNAIL_FACE_HEIGHT_RATIOS, _metadata_path
from app.jobs.thumbnails import read_export_metadata
from app.models import ExportItem, Job, Video
from app.render.render_thumbnail import extract_thumbnail_frame, render_normal_thumbnail
from app.scoring.thumbnail_copy import ThumbnailCopyText
from app.storage.paths import get_storage_paths
from app.thumbnail_style import (
    ThumbnailDesign, ThumbnailSubjectPlacement, ThumbnailTextStyles, resolve_export_thumbnail_style,
)
from app.jobs.thumbnail_character_assets import explicit_character_asset


class ThumbnailPreviewState(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    state: Literal["queued", "ready", "failed"]
    frame_key: str = Field(alias="frameKey")
    error: str | None = None


class ThumbnailPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    frame_key: str = Field(alias="frameKey", pattern=r"^[0-9a-f]{64}$")
    text: ThumbnailCopyText
    text_styles: ThumbnailTextStyles = Field(alias="textStyles")
    design: ThumbnailDesign | None = None
    subject_placement: ThumbnailSubjectPlacement = Field(
        default_factory=ThumbnailSubjectPlacement, alias="subjectPlacement"
    )
    subject_source: Literal["video", "asset"] = Field(default="video", alias="subjectSource")
    character_asset_id: str | None = Field(default=None, alias="characterAssetId", pattern=r"^asset_[0-9a-f]{32}$")


def preview_cache_dir(paths, export):
    return paths.temp / "thumbnail-preview" / sha256(export.id.encode()).hexdigest()[:24]


def _read(directory):
    path = directory / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write(directory, state):
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"state.{uuid4().hex}.tmp"
    temp.write_text(json.dumps(state), encoding="utf-8")
    temp.replace(directory / "state.json")


def preview_context(db, paths, export, *, subject_source="video", character_asset_id=None):
    job = db.get(Job, export.job_id)
    if export.type != "normal" or not job or job.status != "completed":
        raise ValueError("完成した通常動画のサムネだけが対象です。")
    _metadata_path(export, paths)
    metadata = read_export_metadata(export)
    if metadata.get("thumbnail_status") == "generating":
        raise ValueError("保存したサムネを更新中です。完了後にプレビューします。")
    asset = None
    if subject_source == "asset":
        asset = explicit_character_asset(db, paths, job.settings_json or {}, character_asset_id)
        source = paths.character_asset(asset.preset_id, asset.emotion, asset.id)
    else:
        video = db.get(Video, export.video_id)
        if not video:
            raise ValueError("元動画が見つかりません。")
        source = paths.resolve_stored_file(video.stored_path)
    source_stat = source.stat()
    start = float(metadata.get("start", 0))
    frame = float(metadata.get("thumbnail_frame_seconds", float(export.duration) * 0.38))
    if not all(math.isfinite(v) for v in (start, frame)) or start < 0 or not 0 <= frame <= float(export.duration) + 0.001:
        raise ValueError("サムネの場面を確認できません。")
    timestamp = start + min(frame, float(export.duration))
    key = sha256(json.dumps([
        str(source.resolve()), source_stat.st_size, source_stat.st_mtime_ns, timestamp,
        *([asset.id, asset.face_box] if asset else []),
    ]).encode()).hexdigest()
    return {
        "frameKey": key, "source": source, "timestamp": timestamp,
        "anchor": min(1, max(0, float(metadata.get("thumbnail_subject_anchor_x", 1)))),
        "faceRatio": THUMBNAIL_FACE_HEIGHT_RATIOS.get(metadata.get("thumbnail_crop_mode"), 0.25),
        "characterStyle": (job.settings_json or {}).get("normalThumbnailStyle"),
        "asset": asset,
    }


def prepare_thumbnail_preview(db, paths, export, enqueue, *, force=False, subject_source="video", character_asset_id=None):
    context = preview_context(db, paths, export, subject_source=subject_source, character_asset_id=character_asset_id)
    directory = preview_cache_dir(paths, export)
    with subtitle_review_document_lock(directory):
        previous = _read(directory)
        if previous.get("frameKey") == context["frameKey"]:
            if previous.get("state") == "ready" and (directory / "frame.jpg").is_file():
                return ThumbnailPreviewState.model_validate(previous)
            if previous.get("state") == "queued" and time.time() - previous.get("created", 0) < 120:
                return ThumbnailPreviewState.model_validate(previous)
            if previous.get("state") == "failed" and not force:
                return ThumbnailPreviewState.model_validate(previous)
        state = {"state": "queued", "frameKey": context["frameKey"], "requestId": uuid4().hex, "created": time.time(),
                 "subjectSource": subject_source, "characterAssetId": character_asset_id}
        _write(directory, state)
        try:
            enqueue(export.id, state["requestId"])
        except Exception:
            _write(directory, previous)
            raise
    return ThumbnailPreviewState.model_validate(state)


def run_thumbnail_preview_prepare(export_id, request_id, *, session_factory=SessionLocal, paths=None, extractor=extract_thumbnail_frame):
    storage = paths or get_storage_paths()
    with session_factory() as db:
        export = db.get(ExportItem, export_id)
        if export is None:
            return
        directory = preview_cache_dir(storage, export)
        temp_frame = directory / f"frame.{request_id}.jpg"
        try:
            with subtitle_review_document_lock(directory):
                state = _read(directory)
                if state.get("requestId") != request_id or state.get("state") != "queued":
                    return
                subject = {"subject_source": state.get("subjectSource", "video"), "character_asset_id": state.get("characterAssetId")}
                context = preview_context(db, storage, export, **subject)
                if context["frameKey"] != state["frameKey"]:
                    raise ValueError("サムネの場面が変更されました。再読み込みしてください。")
            if context["asset"]:
                shutil.copyfile(context["source"], temp_frame)
            else:
                extractor(context["source"], temp_frame, context["timestamp"])
            with subtitle_review_document_lock(directory):
                if _read(directory).get("requestId") != request_id:
                    return
                if preview_context(db, storage, export, **subject)["frameKey"] != state["frameKey"]:
                    raise ValueError("サムネの場面が変更されました。再読み込みしてください。")
                temp_frame.replace(directory / "frame.jpg")
                _write(directory, {**state, "state": "ready"})
        except Exception:
            with subtitle_review_document_lock(directory):
                state = _read(directory)
                if state.get("requestId") == request_id:
                    _write(directory, {**state, "state": "failed", "error": "プレビューの場面を読み込めませんでした。"})
        finally:
            temp_frame.unlink(missing_ok=True)


def render_thumbnail_preview(db, paths, export, request: ThumbnailPreviewRequest, *, asset_render_info=None):
    context = preview_context(db, paths, export, subject_source=request.subject_source, character_asset_id=request.character_asset_id)
    directory = preview_cache_dir(paths, export)
    with subtitle_review_document_lock(directory):
        state = _read(directory)
        if state.get("state") != "ready" or state.get("frameKey") != request.frame_key or context["frameKey"] != request.frame_key:
            raise ValueError("プレビューの場面を読み込み直してください。")
        # The same renderer as the saved JPEG, using only a cached still image.
        with tempfile.TemporaryDirectory(dir=directory, prefix="draft-") as temp:
            output = Path(temp) / "preview.jpg"
            text_regions: dict[str, dict[str, int]] = {}
            render_normal_thumbnail(
                context["source"], output, source_frame_path=directory / "frame.jpg", frame_time=context["timestamp"],
                eyebrow=request.text.heading.strip(), title_first_line=request.text.upper.strip(),
                title_second_line=request.text.lower.strip(),
                subject_anchor_x=context["anchor"], face_height_ratio=context["faceRatio"],
                subject_scale=request.subject_placement.scale,
                subject_offset_x=request.subject_placement.offset_x,
                subject_offset_y=request.subject_placement.offset_y,
                character_style=resolve_export_thumbnail_style(context["characterStyle"], request.design),
                text_styles=request.text_styles.model_dump(mode="json", by_alias=True),
                text_regions=text_regions,
                **({"character_asset_path": directory / "frame.jpg", "character_asset_face_box": context["asset"].face_box,
                    "asset_render_info": asset_render_info} if context["asset"] else {}),
            )
            return output.read_bytes(), text_regions
