import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.intelligence.common import YouTubeError
from app.intelligence.models import SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.policy import statistical_expiry
from app.intelligence.youtube_client import METRICS


def ingest_video(db: Session, channel_id: int, item: dict[str, Any], observed: datetime) -> YouTubeVideo:
    video = db.get(YouTubeVideo, item["id"])
    if video is not None and video.channel_id != channel_id:
        raise YouTubeError("CHANNEL_MISMATCH")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", item["id"]):
        raise YouTubeError("INVALID_RESPONSE")
    if video is None:
        video = YouTubeVideo(id=item["id"], channel_id=channel_id)
        db.add(video)
    video.title = item["snippet"]["title"]
    video.published_at = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", item["contentDetails"]["duration"])
    if not match:
        raise YouTubeError("INVALID_RESPONSE")
    video.duration_seconds = sum(float(value or 0) * unit for value, unit in zip(match.groups(), (86400, 3600, 60, 1))) or None
    video.metadata_updated_at = observed
    video.availability = "available"
    if item.get("liveStreamingDetails"):
        video.format, video.format_source = "live", "youtube_public"
    else:
        video.format, video.format_source = "unknown", "unknown"
    values, missing = {}, {}
    for name, api_name in {"views": "viewCount", "likes": "likeCount", "comments": "commentCount"}.items():
        raw = item.get("statistics", {}).get(api_name)
        values[name] = int(raw) if raw is not None else None
        if values[name] is not None and values[name] < 0:
            raise YouTubeError("INVALID_RESPONSE")
        if raw is None:
            missing[name] = "UNAVAILABLE"
    video.public_statistics = {"source": "youtube_public", "values": values, "missingReasons": missing}
    video.public_observed_at = observed
    return video


def save_report(db: Session, run: SyncRun, config: Settings, kind, start, end, rows, observed, video_id=None,
                *, error: YouTubeError | None = None) -> None:
    if error:
        run.missing_reports = [*run.missing_reports, {"kind": kind, "videoId": video_id, "start": str(start), "end": str(end),
                                                    **error.details()}]
    elif rows and video_id:
        # A successful retry supersedes the null placeholder for that range.
        placeholder = db.scalar(select(VideoDailyStat).where(
            VideoDailyStat.channel_id == run.channel_id, VideoDailyStat.kind == kind,
            VideoDailyStat.dimension_key == f":{video_id}:",
            VideoDailyStat.period_start == start, VideoDailyStat.period_end == end))
        if placeholder and set(placeholder.missing_reasons.values()) == {"API_5XX"}:
            db.delete(placeholder)
            db.flush()
    if kind in {"first7", "video_format"} and video_id:
        video = db.get(YouTubeVideo, video_id)
        content_types = {row.get("creatorContentType") for row in rows}
        if video and len(content_types) == 1:
            video.format = {"SHORTS": "shorts", "VIDEO_ON_DEMAND": "long", "LIVE_STREAM": "live"}.get(
                next(iter(content_types)), "unknown")
            video.format_source = "youtube_analytics"
    # Persist a null report row instead of inventing zeroes when no rows return.
    for row in rows or [{}]:
        selected_id = row.get("video", video_id)
        dimensions = {key: value for key, value in row.items() if key not in METRICS}
        key = ":".join(str(dimensions.get(name, selected_id if name == "video" else ""))
                       for name in ("day", "video", "creatorContentType"))
        period_start = date.fromisoformat(row["day"]) if "day" in row else start
        period_end = date.fromisoformat(row["day"]) if "day" in row else end
        saved = db.scalar(select(VideoDailyStat).where(
            VideoDailyStat.channel_id == run.channel_id, VideoDailyStat.kind == kind,
            VideoDailyStat.dimension_key == key, VideoDailyStat.period_start == period_start, VideoDailyStat.period_end == period_end))
        if saved is not None and error:
            # A transient failure must not erase previously returned statistics.
            continue
        if saved is None:
            saved = VideoDailyStat(channel_id=run.channel_id, kind=kind, dimension_key=key,
                                   period_start=period_start, period_end=period_end)
            db.add(saved)
        saved.video_id, saved.sync_run_id = selected_id, run.id
        saved.dimensions = dimensions
        saved.values = {metric: row.get(metric) for metric in METRICS}
        missing = error.code if error else "NO_ROWS"
        saved.missing_reasons = {metric: "UNAVAILABLE" if rows else missing for metric in METRICS if row.get(metric) is None}
        saved.observed_at, saved.expires_at = observed, statistical_expiry(observed, config)
        if not rows and not error:
            run.missing_reports = [*run.missing_reports, {"kind": kind, "videoId": video_id, "reason": "NO_ROWS"}]
