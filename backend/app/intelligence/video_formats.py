"""Native creatorContentType values, including observed camelCase responses."""

from collections import Counter
from datetime import timedelta
import re

from sqlalchemy import select

from app.intelligence.common import now
from app.intelligence.models import VideoDailyStat, YouTubeVideo


def content_format(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    key = re.sub(r"[\s_-]", "", value).casefold()
    return {"shorts": "shorts", "videoondemand": "long", "livestream": "live"}.get(key, "unknown")


def repair_video_formats(db, *, execute: bool = False, clock=None) -> dict:
    stamp = clock or now()
    changes, ambiguous = [], 0
    before = Counter(db.scalars(select(YouTubeVideo.format)))
    for video in db.scalars(select(YouTubeVideo).order_by(YouTubeVideo.id)):
        if not video.metadata_updated_at or video.metadata_updated_at <= stamp - timedelta(days=30):
            continue  # Do not restore expired metadata.
        rows = db.scalars(select(VideoDailyStat).where(
            VideoDailyStat.video_id == video.id, VideoDailyStat.channel_id == video.channel_id,
            VideoDailyStat.kind.in_(["video_format", "first7"]), VideoDailyStat.expires_at > stamp,
        ).order_by(VideoDailyStat.observed_at.desc())).all()
        rows = [row for row in rows if row.dimensions.get("creatorContentType") or row.dimension_key.rsplit(":", 1)[-1]]
        if not rows:
            continue
        newest = rows[0].observed_at
        formats = {content_format(row.dimensions.get("creatorContentType") or row.dimension_key.rsplit(":", 1)[-1])
                   for row in rows if row.observed_at == newest}
        if len(formats) != 1 or "unknown" in formats:
            ambiguous += 1
            continue
        detected = formats.pop()
        if video.format != detected or video.format_source != "youtube_analytics":
            changes.append({"videoId": video.id, "before": video.format, "after": detected})
            if execute:
                video.format, video.format_source = detected, "youtube_analytics"
    if execute:
        db.commit()
    after = before.copy()
    for change in changes:
        after[change["before"]] -= 1
        after[change["after"]] += 1
    return {"command": "repair-youtube-video-formats", "dry_run": not execute,
            "before": dict(before), "after": dict(after), "changed": len(changes),
            "ambiguous": ambiguous, "changes": changes, "errors": []}
