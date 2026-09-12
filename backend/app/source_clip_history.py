"""Source identity and successful-export history, without retaining media files."""

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.candidates.used_ranges import USED_RANGES_SETTING, merge_ranges
from app.models import ExportItem, Job, SourceClipUsage, Video, utc_now
from app.storage.paths import StoragePaths


YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
FILENAME_ID = re.compile(r"[\[(]([A-Za-z0-9_-]{11})[\])]")


def source_key(video: Video, settings: dict[str, Any]) -> str | None:
    matches = FILENAME_ID.findall(video.original_filename)
    if matches:
        return f"youtube:{matches[-1]}"
    try:
        url = urlparse(str(settings.get("youtubeSourceUrl") or ""))
        host = (url.hostname or "").lower()
        parts = url.path.strip("/").split("/")
        video_id = ""
        if host in {"youtu.be", "www.youtu.be"}:
            video_id = parts[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parts[0] == "watch":
                video_id = parse_qs(url.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"live", "shorts", "embed"}:
                video_id = parts[1]
        if YOUTUBE_ID.fullmatch(video_id):
            return f"youtube:{video_id}"
    except ValueError:
        pass
    # Fallback for byte-identical uploads only; never identify by title alone.
    stem = Path(video.stored_path).stem
    if re.fullmatch(r"[0-9a-f]{64}", stem):
        return f"sha256:{stem}"
    return None


def record_completed_exports(db: Session, job: Job, paths: StoragePaths | None = None) -> int:
    if job.status != "completed":
        return 0
    video = db.get(Video, job.video_id)
    if video is None or (key := source_key(video, job.settings_json or {})) is None:
        return 0
    db.flush()
    count = 0
    for export in db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)):
        if not export.metadata_path:
            continue
        path = Path(export.metadata_path)
        if paths is not None:
            path = paths.resolve_stored_file(export.metadata_path)
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            start, end = float(metadata["start"]), float(metadata["end"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            continue
        if video.duration and end > video.duration + 0.05:
            continue
        identity = json.dumps([key, job.id, export.type, start, end], separators=(",", ":"))
        result = db.execute(
            insert(SourceClipUsage).values(
                id=sha256(identity.encode()).hexdigest(),
                source_key=key,
                job_id=job.id,
                clip_type=export.type,
                start=start,
                end=end,
                source_duration=video.duration,
                created_at=utc_now(),
            ).on_conflict_do_nothing(index_elements=["id"])
        )
        count += result.rowcount
    return count


def backfill_completed_history(db: Session, paths: StoragePaths | None = None) -> int:
    """Also covers exports produced by an older worker before deployment."""
    return sum(
        record_completed_exports(db, job, paths)
        for job in db.scalars(select(Job).where(Job.status == "completed")).all()
    )


class SourceTimelineChanged(ValueError):
    pass


def selection_history_settings(
    db: Session, job: Job, video: Video, paths: StoragePaths
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = dict(job.settings_json or {})
    # Ignore any client-supplied or copied internal exclusions.
    settings.pop(USED_RANGES_SETTING, None)
    backfill_completed_history(db, paths)
    db.commit()
    key = source_key(video, settings)
    summary: dict[str, Any] = {
        "sourceKey": key,
        "policy": "exclude_any_overlap_across_clip_types",
        "ranges": [],
        "historyCount": 0,
        "skippedReason": None,
    }
    if settings.get("reeditOf") or settings.get("workflowMode", settings.get("workflow_mode")) == "manual":
        summary["skippedReason"] = "manual_or_existing_clip_reedit"
        return settings, summary
    if key is None:
        summary["skippedReason"] = "source_identity_unavailable"
        return settings, summary
    rows = db.scalars(select(SourceClipUsage).where(
        SourceClipUsage.source_key == key,
        SourceClipUsage.job_id != job.id,
    )).all()
    if video.duration and any(
        row.source_duration and abs(row.source_duration - video.duration) > 1.0
        for row in rows
    ):
        raise SourceTimelineChanged(
            "同じ元動画IDですが、過去の動画と長さが異なります。元配信のカット編集がないか確認してください。"
        )
    ranges = merge_ranges([(row.start, row.end) for row in rows])
    settings[USED_RANGES_SETTING] = ranges
    summary.update(ranges=ranges, historyCount=len(rows))
    return settings, summary
