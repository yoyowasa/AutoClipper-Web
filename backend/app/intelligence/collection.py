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
RETENTION_LIMIT = 20
RETENTION_MAX_ATTEMPTS = 3
RETENTION_RETRY_DAYS = 14
RETENTION_FINAL = "RETENTION_NOT_RETURNED_FINAL"


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
    attempts: int | None = None
    missing_reason: str | None = None


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
                    pending: list[dict] | None = None, retention_states=None, retention_final=(),
                    previous_last=None, before_optional=None):
    """The basic collect_self periods; no diagnosis/derived metrics/deep reports."""
    end = stamp.replace(tzinfo=UTC).astimezone(PACIFIC).date() - timedelta(days=1)
    start = end - timedelta(days=59)
    reports = []
    pending = [item for item in (pending or []) if item["kind"] not in RETENTION_WINDOWS]

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
        if previous_last and last > previous_last:
            # Keep the newly available video day fresh while older normal
            # requests drain. Same-day reruns can reuse the saved daily slice.
            requests = split_video_day_requests([video.id for video in videos], last, last) + requests
    else:
        requests = optional_requests(videos, start, end, last)
    checkpoint = []
    first7_count = 0
    for index, request in enumerate(requests):
        if request.kind in {"first7", "first30"} and first7_count >= INITIAL_LIMIT:
            checkpoint = [item.checkpoint() for item in requests[index:]]
            break
        error = None
        try:
            rows = client.report(external_id, request.start, request.end, request.dimensions, request.video_ids)
        except YouTubeError as failure:
            if failure.code == "SYNC_LIMIT":
                return start, end, last, reports, [item.checkpoint() for item in requests[index:]]
            if failure.code != "API_5XX":
                raise
            rows, error = [], failure
        first7_count += request.kind in {"first7", "first30"}
        for video_id in request.video_ids:
            video_rows = [row for row in rows if row.get("video", video_id) == video_id]
            reports.append(CollectedReport(request.kind, request.start, request.end, video_rows, video_id, error))
    reports.extend(collect_retention(client, external_id, videos, end, last, retention_states or {}, retention_final))
    return start, end, last, reports, checkpoint


def collect_retention(client, external_id, videos, end, last, states, final_windows):
    today = end + timedelta(days=1)
    latest = min(last, end - timedelta(days=RETENTION_LAG_DAYS))
    reports, attempted = [], 0
    for video in videos:
        for kind, days in RETENTION_WINDOWS.items():
            begin, finish = initial_window(video.published_at, days)
            if finish > latest or (kind, video.id, str(begin), str(finish)) in final_windows:
                continue
            state = states.get((kind, video.id, begin, finish))
            if state and (any(state.values.values()) or RETENTION_FINAL in state.missing_reasons.values()):
                continue
            attempts = state.dimensions.get("attempts", 1) if state else 0
            deadline = finish + timedelta(days=RETENTION_RETRY_DAYS)
            # Historical backfill gets one first attempt. Only retries have a
            # calendar deadline, so old clips can still contribute evidence.
            if attempts and (attempts >= RETENTION_MAX_ATTEMPTS or today > deadline):
                reports.append(CollectedReport(kind, begin, finish, [], video.id, attempts=attempts,
                                               missing_reason=RETENTION_FINAL))
                continue
            if attempted >= RETENTION_LIMIT:
                continue
            before = client.requests
            error = None
            try:
                rows = client.report(external_id, begin, finish, RETENTION_DIMENSION, [video.id])
            except YouTubeError as failure:
                if failure.code == "SYNC_LIMIT" and client.requests == before:
                    return reports
                if failure.code in {"QUOTA_EXCEEDED", "RECONNECT_REQUIRED"}:
                    reports.append(CollectedReport(kind, begin, finish, [], video.id, failure, attempts))
                    return reports
                rows, error = [], failure
            attempted += 1
            attempts += 1
            curves = {metric: {row[RETENTION_DIMENSION]: row[metric] for row in rows if row[metric] is not None}
                      for metric in RETENTION_METRICS}
            values = [{metric: curve or None for metric, curve in curves.items()}] if any(curves.values()) else []
            final = not values and (attempts >= RETENTION_MAX_ATTEMPTS or today >= deadline)
            reports.append(CollectedReport(kind, begin, finish, values, video.id, error, attempts,
                                           RETENTION_FINAL if final else None))
            if error and error.code == "SYNC_LIMIT":
                return reports
    return reports
