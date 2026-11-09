from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.intelligence.common import YouTubeError
from app.intelligence.youtube_client import INITIAL_LIMIT, REPORT_PAGE_SIZE, RETENTION_DIMENSION, RETENTION_METRICS, YouTubeClient
from app.intelligence.evaluation_rules import PACIFIC, initial_window


RETENTION_WINDOWS = {"retention7": 7, "retention30": 30}
RETENTION_DEFINITION = "youtube-retention-v1"
# Reports can silently truncate endDate. Allow the documented 48–72 hour
# processing delay after the last Pacific day has fully ended.
RETENTION_LAG_DAYS = 3


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
        for kind, days in (("first30", 30), ("first7", 7)):
            begin, finish = initial_window(video.published_at, days)
            if finish <= last:
                requests.append(ReportRequest(kind, begin, finish, "creatorContentType", [video.id]))
    return requests


def collect_reports(client: YouTubeClient, external_id: str, videos, stamp: datetime, *,
                    pending: list[dict] | None = None, retention_completed=(), before_optional=None):
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
        if before_optional:
            before_optional()
        return start, end, None, reports, pending or []
    current = last - timedelta(days=27)
    fetch("current", current, last)
    fetch("previous", last - timedelta(days=55), last - timedelta(days=28))
    if before_optional:
        before_optional()
    if pending:
        available = {video.id for video in videos}
        requests = [ReportRequest(item["kind"], date.fromisoformat(item["start"]), date.fromisoformat(item["end"]),
                                  item["dimensions"], [id for id in item["videoIds"] if id in available]) for item in pending]
        requests = [request for request in requests if request.video_ids]
    else:
        requests = optional_requests(videos, start, end, last)
        for video in videos:
            for kind, days in RETENTION_WINDOWS.items():
                begin, finish = initial_window(video.published_at, days)
                if finish <= min(last, end - timedelta(days=RETENTION_LAG_DAYS)):
                    requests.append(ReportRequest(kind, begin, finish, RETENTION_DIMENSION, [video.id]))
    requests = [request for request in requests if request.kind not in RETENTION_WINDOWS or
                (request.kind, request.video_ids[0], request.start, request.end) not in retention_completed]
    first7_count = 0
    for index, request in enumerate(requests):
        if request.kind in {"first7", "first30"} and first7_count >= INITIAL_LIMIT:
            return start, end, last, reports, [item.checkpoint() for item in requests[index:]]
        error = None
        try:
            rows = client.report(external_id, request.start, request.end, request.dimensions, request.video_ids)
        except YouTubeError as failure:
            if failure.code == "SYNC_LIMIT":
                return start, end, last, reports, [item.checkpoint() for item in requests[index:]]
            if failure.code != "API_5XX" and not (request.kind in RETENTION_WINDOWS and failure.code in
                    {"API_BAD_REQUEST", "API_NOT_FOUND", "FORBIDDEN", "INVALID_RESPONSE", "NETWORK_ERROR"}):
                raise
            rows, error = [], failure
        if request.kind in RETENTION_WINDOWS:
            # One stored row per fixed window. Preserve every returned bucket,
            # but never treat an entirely null report as a finished observation.
            curves = {metric: {row[RETENTION_DIMENSION]: row[metric] for row in rows if row[metric] is not None}
                      for metric in RETENTION_METRICS}
            rows = [{metric: curve or None for metric, curve in curves.items()}] if any(curves.values()) else []
        first7_count += request.kind in {"first7", "first30"}
        for video_id in request.video_ids:
            video_rows = [row for row in rows if row.get("video", video_id) == video_id]
            reports.append(CollectedReport(request.kind, request.start, request.end, video_rows, video_id, error))
    return start, end, last, reports, []
