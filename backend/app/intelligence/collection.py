from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.intelligence.common import YouTubeError
from app.intelligence.youtube_client import INITIAL_LIMIT, REPORT_PAGE_SIZE, YouTubeClient

PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass
class ReportRequest:
    kind: str
    start: date
    end: date
    dimensions: str
    video_ids: list[str]

    def checkpoint(self) -> dict:
        return {"kind": self.kind, "start": str(self.start), "end": str(self.end),
                "dimensions": self.dimensions, "videoIds": self.video_ids}


@dataclass
class CollectedReport:
    kind: str
    start: date
    end: date
    rows: list[dict]
    video_id: str | None = None
    error: YouTubeError | None = None


def split_video_day_requests(video_ids: list[str], start: date, end: date) -> list[ReportRequest]:
    """Bound the Cartesian product, including empty days, to a single page."""
    if end < start:
        raise ValueError("end precedes start")
    requests = []
    begin = start
    while begin <= end:
        finish = min(end, begin + timedelta(days=REPORT_PAGE_SIZE - 1))
        batch_size = REPORT_PAGE_SIZE // ((finish - begin).days + 1)
        for offset in range(0, len(video_ids), batch_size):
            requests.append(ReportRequest("video_day", begin, finish, "day,video", video_ids[offset:offset + batch_size]))
        begin = finish + timedelta(days=1)
    return requests


def optional_requests(videos, start: date, end: date, last: date) -> list[ReportRequest]:
    ids = [video.id for video in videos]
    requests = split_video_day_requests(ids, start, end)
    for offset in range(0, len(ids), 100):
        for kind, dimensions in (("video_period", "video"), ("video_format", "video,creatorContentType")):
            requests.append(ReportRequest(kind, last - timedelta(days=27), last, dimensions, ids[offset:offset + 100]))
    for video in videos:
        begin = video.published_at.replace(tzinfo=UTC).astimezone(PACIFIC).date() + timedelta(days=1)
        finish = begin + timedelta(days=6)
        if finish <= last:
            requests.append(ReportRequest("first7", begin, finish, "creatorContentType", [video.id]))
    return requests


def collect_reports(client: YouTubeClient, external_id: str, videos, stamp: datetime, *, pending: list[dict] | None = None):
    """The basic collect_self periods; no diagnosis/derived metrics/deep reports."""
    end = stamp.replace(tzinfo=UTC).astimezone(PACIFIC).date() - timedelta(days=1)
    start = end - timedelta(days=59)
    reports = []

    def fetch(kind, begin, finish, dimensions=""):
        rows = client.report(external_id, begin, finish, dimensions)
        reports.append(CollectedReport(kind, begin, finish, rows))
        return rows

    daily = fetch("daily", start, end, "day")
    last = max((date.fromisoformat(row["day"]) for row in daily), default=None)
    if last is None:
        return start, end, None, reports, pending or []
    current = last - timedelta(days=27)
    fetch("current", current, last)
    fetch("previous", last - timedelta(days=55), last - timedelta(days=28))
    if pending:
        available = {video.id for video in videos}
        requests = [ReportRequest(item["kind"], date.fromisoformat(item["start"]), date.fromisoformat(item["end"]),
                                  item["dimensions"], [id for id in item["videoIds"] if id in available]) for item in pending]
        requests = [request for request in requests if request.video_ids]
    else:
        requests = optional_requests(videos, start, end, last)
    first7_count = 0
    for index, request in enumerate(requests):
        if request.kind == "first7" and first7_count >= INITIAL_LIMIT:
            return start, end, last, reports, [item.checkpoint() for item in requests[index:]]
        error = None
        try:
            rows = client.report(external_id, request.start, request.end, request.dimensions, request.video_ids)
        except YouTubeError as failure:
            if failure.code == "SYNC_LIMIT":
                return start, end, last, reports, [item.checkpoint() for item in requests[index:]]
            if failure.code != "API_5XX":
                raise
            rows, error = [], failure
        first7_count += request.kind == "first7"
        for video_id in request.video_ids:
            video_rows = [row for row in rows if row.get("video", video_id) == video_id]
            reports.append(CollectedReport(request.kind, request.start, request.end, video_rows, video_id, error))
    return start, end, last, reports, []
