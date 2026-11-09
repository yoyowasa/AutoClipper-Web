"""Explicit source links and bounded, expiring public metadata lookups."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.intelligence.common import YouTubeError
from app.intelligence.evaluation_rules import PACIFIC
from app.intelligence.models import ProductionLink
from app.intelligence.production_catalog import read_families

SOURCE_TIMING = "source_timing"
URL = re.compile(r"https?://[^\s<>「」【】]+")


def youtube_video_id(url):
    try:
        parts = urlsplit(url.rstrip(").,。、）"))
        if parts.scheme not in {"https", "http"} or parts.username or parts.password:
            return None
        path = parts.path.strip("/").split("/")
        value = ""
        if parts.hostname in {"youtu.be", "www.youtu.be"} and len(path) == 1:
            value = path[0]
        if parts.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if path == ["watch"]:
                value = parse_qs(parts.query).get("v", [""])[0]
            elif len(path) == 2 and path[0] in {"live", "shorts"}:
                value = path[1]
        return value if re.fullmatch(r"[A-Za-z0-9_-]{11}", value) else None
    except ValueError:
        return None


def description_candidates(description, own_ids):
    return {id for url in URL.findall(description) if (id := youtube_video_id(url)) and id not in own_ids}


def external_source(candidates, items, own_channel_ids):
    channels = [items.get(id, {}).get("snippet", {}).get("channelId") for id in candidates]
    if not all(channels):
        return None
    foreign = [id for id in candidates if items[id]["snippet"]["channelId"] not in own_channel_ids]
    return foreign[0] if len(foreign) == 1 else None


def linked_records(db, paths, video_ids, *, families=None):
    links = db.scalars(select(ProductionLink).where(ProductionLink.youtube_video_id.in_(video_ids))).all()
    if not links:
        return
    if families is None:
        families, _ = read_families(paths)
    for link in links:
        family = families.get(link.record_family_id)
        record = family.latest if family and not family.ambiguous and family.latest.recordId == link.record_id else None
        yield link.youtube_video_id, record


def fresh_source_timing(video, stamp):
    timing = (video.public_statistics or {}).get(SOURCE_TIMING)
    if timing and datetime.fromisoformat(timing["observed_at"]) > stamp - timedelta(days=30):
        return timing
    return None


def _utc(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def _timing(video, item, origin, id, stamp):
    published = _utc(item.get("snippet", {}).get("publishedAt"))
    started = _utc(item.get("liveStreamingDetails", {}).get("actualStartTime"))
    source_date = started or published
    if source_date is None or source_date > video.published_at.replace(tzinfo=UTC):
        return None
    days = (video.published_at.replace(tzinfo=UTC).astimezone(PACIFIC).date()
            - source_date.astimezone(PACIFIC).date()).days
    return {"source_video_id": id, "link_origin": origin, "observed_at": stamp.isoformat(),
            "source_channel_id": item.get("snippet", {}).get("channelId"),
            "source_published_at": published.isoformat() if published else None,
            "source_started_at": started.isoformat() if started else None,
            "days_since_source": days}


def refresh_source_timings(db, paths, client, videos, descriptions, stamp, own_channel_ids, own_ids):
    records = dict(linked_records(db, paths, [video.id for video in videos]))
    lookup, requested_ids = [], set()
    for video in videos:
        record = records.get(video.id)
        explicit = youtube_video_id(record.source.url) if record and record.source.url else None
        origin = "production_record" if explicit else "description"
        candidates = {explicit} if explicit else description_candidates(descriptions.get(video.id, ""), own_ids)
        timing = fresh_source_timing(video, stamp)
        if (timing and candidates == {timing["source_video_id"]} and timing["link_origin"] == origin
                and (explicit or (timing.get("source_channel_id") and timing["source_channel_id"] not in own_channel_ids))):
            continue
        video.public_statistics = {k: v for k, v in video.public_statistics.items() if k != SOURCE_TIMING}
        candidates.discard(video.id)
        if candidates:
            lookup.append((video, origin, candidates))
            requested_ids.update(candidates)
    if not lookup:
        return
    items_by_id = {}
    try:
        for requested, items in client.videos(sorted(requested_ids)):
            for item in items:
                id = item.get("id")
                if id not in requested:
                    raise YouTubeError("INVALID_RESPONSE")
                items_by_id[id] = item
    except YouTubeError as error:
        if error.code not in {"SYNC_LIMIT", "API_5XX", "NETWORK_ERROR", "FORBIDDEN", "API_NOT_FOUND"}:
            raise
    for video, origin, candidates in lookup:
        id = (next(iter(candidates)) if origin == "production_record"
              else external_source(sorted(candidates), items_by_id, own_channel_ids))
        if id in items_by_id and (timing := _timing(video, items_by_id[id], origin, id, stamp)):
            video.public_statistics = {**video.public_statistics, SOURCE_TIMING: timing}
