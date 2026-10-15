from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.intelligence.youtube_client import INITIAL_LIMIT, YouTubeClient

PACIFIC = ZoneInfo("America/Los_Angeles")


def collect_reports(client: YouTubeClient, external_id: str, videos, stamp: datetime):
    """The basic collect_self periods; no diagnosis/derived metrics/deep reports."""
    end = stamp.replace(tzinfo=UTC).astimezone(PACIFIC).date() - timedelta(days=1)
    start = end - timedelta(days=59)
    reports = []

    def fetch(kind, begin, finish, dimensions="", ids=None, video_id=None):
        rows = client.report(external_id, begin, finish, dimensions, ids)
        reports.append((kind, begin, finish, rows, video_id))
        return rows

    daily = fetch("daily", start, end, "day")
    last = max((date.fromisoformat(row["day"]) for row in daily), default=None)
    if last is None:
        return start, end, None, reports, False
    current = last - timedelta(days=27)
    fetch("current", current, last)
    fetch("previous", last - timedelta(days=55), last - timedelta(days=28))
    for offset in range(0, len(videos), 100):
        batch = videos[offset:offset + 100]
        ids = [video.id for video in batch]
        daily_rows = client.report(external_id, start, end, "day,video", ids)
        if daily_rows:
            reports.append(("video_day", start, end, daily_rows, None))
        else:
            reports.extend(("video_day", start, end, [], video.id) for video in batch)
        rows = client.report(external_id, current, last, "video", ids)
        by_id = {row["video"]: row for row in rows}
        formats = client.report(external_id, current, last, "video,creatorContentType", ids)
        for video in batch:
            row = by_id.get(video.id)
            reports.append(("video_period", current, last, [row] if row else [], video.id))
            reports.append(("video_format", current, last, [row for row in formats if row["video"] == video.id], video.id))
    eligible = []
    for video in videos:
        begin = video.published_at.replace(tzinfo=UTC).astimezone(PACIFIC).date() + timedelta(days=1)
        finish = begin + timedelta(days=6)
        if finish <= last:
            eligible.append((video, begin, finish))
    for video, begin, finish in eligible[:INITIAL_LIMIT]:
        fetch("first7", begin, finish, "creatorContentType", [video.id], video.id)
    return start, end, last, reports, len(eligible) > INITIAL_LIMIT
