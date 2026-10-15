import calendar
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.intelligence.common import now
from app.intelligence.models import Channel, VideoDailyStat, YouTubeVideo

POLICY_URL = "https://developers.google.com/youtube/terms/derived-metrics-policy"


def statistical_expiry(observed: datetime, config: Settings) -> datetime:
    if not config.youtube_extended_storage:
        return observed + timedelta(days=30)
    year = observed.year + 3
    return observed.replace(year=year, day=min(observed.day, calendar.monthrange(year, observed.month)[1]))


def expire_youtube_data(db: Session, config: Settings, *, clock: datetime | None = None) -> None:
    stamp = clock or now()
    db.execute(delete(VideoDailyStat).where(VideoDailyStat.expires_at <= stamp))
    if not config.youtube_extended_storage:
        db.execute(delete(VideoDailyStat).where(VideoDailyStat.observed_at <= stamp - timedelta(days=30)))
    # Retain opaque IDs and statistical records, never stale titles/names.
    cutoff = stamp - timedelta(days=30)
    db.execute(update(Channel).where(Channel.metadata_updated_at <= cutoff).values(name=None, metadata_updated_at=None))
    db.execute(update(YouTubeVideo).where(YouTubeVideo.metadata_updated_at <= cutoff).values(
        title=None, published_at=None, duration_seconds=None, format="unknown", format_source="unknown", metadata_updated_at=None))
    for video in db.scalars(select(YouTubeVideo).where(YouTubeVideo.public_observed_at.is_not(None))):
        if statistical_expiry(video.public_observed_at, config) <= stamp:
            video.public_statistics = None
            video.public_observed_at = None
    db.commit()
