"""Names and temporary archives for upload-ready downloads.

Only download names change; published files and historical metadata stay intact.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path, PureWindowsPath
import re
from tempfile import mkstemp
from typing import Any
import os
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.responses import FileResponse
from starlette.types import Receive, Scope, Send

from app.jobs.thumbnails import read_export_metadata
from app.models import ExportItem
from app.storage.paths import StoragePaths


TITLE_FILENAME_LIMIT = 100
_WINDOWS_CHARACTERS = str.maketrans('?:/\\*"<>|', "？：／＼＊＂＜＞｜")


@dataclass(frozen=True)
class DownloadName:
    stem: str
    truncated: bool


def upload_ready_name(title: str | None, *, fallback: str) -> DownloadName:
    """Use Unicode code points for the 100-character limit, including Japanese."""
    source = title if title and title.strip() else fallback
    cleaned = "".join(c for c in source if unicodedata.category(c) not in {"Cc", "Cf"})
    cleaned = re.sub(r"[.\s]+$", "", cleaned.translate(_WINDOWS_CHARACTERS))
    if not cleaned:
        cleaned = fallback
    truncated = len(cleaned) > TITLE_FILENAME_LIMIT
    cleaned = re.sub(r"[.\s]+$", "", cleaned[:TITLE_FILENAME_LIMIT])
    if PureWindowsPath(cleaned).is_reserved():
        truncated = truncated or len(cleaned) > TITLE_FILENAME_LIMIT - 1
        cleaned = "_" + cleaned[: TITLE_FILENAME_LIMIT - 1]
    return DownloadName(cleaned or "clip", truncated)


def export_download_name(export: ExportItem) -> DownloadName:
    return upload_ready_name(export.title, fallback=Path(export.video_path).stem)


def thumbnail_extension(path: str | Path | None) -> str:
    return ".png" if path and Path(path).suffix.lower() == ".png" else ".jpg"


def published_thumbnail(export: ExportItem, job_dir: Path) -> Path | None:
    metadata = read_export_metadata(export)
    value = metadata.get("thumbnail_path")
    if metadata.get("thumbnail_status") not in {"ready", "generating"} or not isinstance(value, str):
        return None
    path = Path(value)
    if not path.resolve().is_relative_to(job_dir.resolve()) or not path.is_file():
        return None
    return path


def posting_text(export: ExportItem) -> str:
    metadata = read_export_metadata(export)
    # Older exports sometimes keep posting fields only in selected_clips.json.
    selected_path = Path(export.video_path).parent.parent / "selected_clips.json"
    if selected_path.is_file():
        try:
            payload = json.loads(selected_path.read_text(encoding="utf-8"))
            candidates = payload.get("normalClips", payload.get("normal_clips", [])) + payload.get("shorts", [])
            selected = next((c for c in candidates if (c.get("id") or c.get("candidate_id")) == export.candidate_id), {})
            metadata = {**selected, **metadata}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    tags = metadata.get("youtube_tags") or []
    hashtags = metadata.get("youtube_hashtags") or []
    return "\n".join(
        [
            "タイトル",
            export.title or "",
            "",
            "説明",
            str(metadata.get("youtube_description") or ""),
            "",
            "タグ",
            ", ".join(str(tag) for tag in tags),
            "",
            "ハッシュタグ",
            " ".join("#" + str(tag).lstrip("#") for tag in hashtags),
            "",
        ]
    )


def posting_set_manifest(export: ExportItem, thumbnail: Path) -> dict[str, Any]:
    name = export_download_name(export)
    return {
        "stem": name.stem,
        "truncated": name.truncated,
        "files": [
            {"name": name.stem + ".mp4", "url": f"/api/exports/{export.id}/download", "mimeType": "video/mp4"},
            {
                "name": name.stem + thumbnail_extension(thumbnail),
                "url": f"/api/exports/{export.id}/thumbnail/download",
                "mimeType": "image/png" if thumbnail.suffix.lower() == ".png" else "image/jpeg",
            },
            {"name": name.stem + "_投稿文.txt", "url": f"/api/exports/{export.id}/posting-text", "mimeType": "text/plain"},
        ],
    }


def create_download_archive(
    path: Path,
    exports: Sequence[ExportItem],
    *,
    job_dir: Path,
    metadata_files: Sequence[Path] = (),
    posting_set: bool = False,
) -> None:
    """Keep equal titles in separate subdirectories rather than renaming titles."""
    names = {export.id: export_download_name(export).stem for export in exports}
    counts = Counter((export.type, names[export.id].casefold()) for export in exports)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for export in exports:
            stem = names[export.id]
            type_dir = "shorts" if export.type == "short" else "normal"
            folder = type_dir + (f"/{export.id}" if counts[(export.type, stem.casefold())] > 1 else "")
            for section, value in [("videos", export.video_path), ("subtitles", export.subtitle_path), ("metadata", export.metadata_path)]:
                if posting_set and section != "videos":
                    continue
                source = Path(value) if value else None
                if source and source.is_file() and source.resolve().is_relative_to(job_dir.resolve()):
                    arcname = stem + source.suffix if posting_set else f"{section}/{folder}/{stem}{source.suffix}"
                    archive.write(source, arcname=arcname)
            thumbnail = published_thumbnail(export, job_dir)
            if thumbnail:
                filename = stem + thumbnail_extension(thumbnail)
                archive.write(thumbnail, arcname=filename if posting_set else f"thumbnails/{folder}/{filename}")
            text_name = stem + "_投稿文.txt"
            archive.writestr(text_name if posting_set else f"posting/{folder}/{text_name}", posting_text(export))
        for metadata in metadata_files:
            if metadata.is_file() and metadata.resolve().is_relative_to(job_dir.resolve()):
                archive.write(metadata, arcname=f"metadata/{metadata.name}")


class TemporaryArchiveResponse(FileResponse):
    """Clean up even if sending raises or the receiving client disconnects."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # A path-send extension can defer reading until after FileResponse returns.
        # Stream the file ourselves so deletion always follows the last read.
        scope = {**scope, "extensions": {k: v for k, v in scope.get("extensions", {}).items() if k != "http.response.pathsend"}}
        try:
            await super().__call__(scope, receive, send)
        finally:
            Path(self.path).unlink(missing_ok=True)


def temporary_archive_path(paths: StoragePaths) -> Path:
    paths.temp.mkdir(parents=True, exist_ok=True)
    descriptor, value = mkstemp(prefix="download-", suffix=".zip", dir=paths.temp)
    os.close(descriptor)
    return Path(value)
