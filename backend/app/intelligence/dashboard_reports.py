"""Read native windows and sum only additive, explicitly covered observations."""
from datetime import UTC, timedelta

from app.intelligence.analysis_reports import REPORT_DEFAULTS
from app.intelligence.collection import PACIFIC
from app.intelligence.dashboard_schemas import MetricRead, ReportRead
from app.intelligence.policy import statistical_expiry
from app.intelligence.video_formats import content_format
from app.intelligence.youtube_client import METRICS

OVERVIEW_METRICS = ("views", "engagedViews", "estimatedMinutesWatched", "subscribersGained")


def duration_band(seconds, format):
    if seconds is None or seconds <= 0 or format not in {"shorts", "long"}:
        return "unknown"
    bands = ((30, "30秒未満"), (45, "30〜45秒未満"), (60, "45〜60秒未満"), (76, "60〜75秒")) if format == "shorts" else (
        (180, "3分未満"), (360, "3〜6分未満"), (600, "6〜10分未満"), (1200, "10〜20分未満"))
    # 75 seconds is inclusive; do not put fractional values above 75 into that band.
    if format == "shorts" and seconds > 75:
        return "75秒超"
    return next((label for limit, label in bands if seconds < limit), "20分以上")


def fresh_video(video, stamp):
    return (video.availability == "available" and video.metadata_updated_at is not None
            and video.metadata_updated_at > stamp - timedelta(days=30))


def valid_stat(row, config, stamp):
    return (row.expires_at > stamp and statistical_expiry(row.observed_at, config) > stamp
            and all(getattr(row, key) == value for key, value in REPORT_DEFAULTS.items()))


def missing_report(reason, start=None, end=None, *, source="youtube_analytics"):
    return ReportRead(source=source, start=start, end=end, reason=reason,
                      metrics={key: MetricRead(missingReason=reason) for key in METRICS})


def native_window(rows, kind, start, end, *, expected_format=None):
    selected = [row for row in rows if row.kind == kind and row.period_start == start and row.period_end == end]
    if not selected:
        return missing_report("NO_ROWS", start, end)
    # An empty transient-error placeholder is not a second content-type partition.
    measured = [row for row in selected if any(value is not None for value in row.values.values())]
    if measured:
        selected = measured
    formats = {content_format(row.dimensions.get("creatorContentType")) for row in selected}
    if len(formats) > 1:
        return missing_report("MULTIPLE_CONTENT_TYPES", start, end)
    row = max(selected, key=lambda row: (row.observed_at, row.id))
    format = next(iter(formats))
    if expected_format and format not in {expected_format, "unknown"}:
        return missing_report("FORMAT_MISMATCH", start, end)
    return ReportRead(start=start, end=end, observedAt=row.observed_at, format=format, metrics={
        key: MetricRead(value=row.values.get(key), missingReason=(row.missing_reasons.get(key, "UNAVAILABLE")
                       if row.values.get(key) is None else None)) for key in METRICS})


def first7_report(video, rows, last):
    if video.published_at is None:
        return missing_report("PUBLICATION_UNAVAILABLE")
    start = video.published_at.replace(tzinfo=UTC).astimezone(PACIFIC).date() + timedelta(days=1)
    end = start + timedelta(days=6)
    if last is None or end > last:
        return missing_report("FIRST7_NOT_READY", start, end)
    return native_window(rows, "first7", start, end, expected_format=video.format)


def derived_window(videos, rows, start, end):
    """Missing days are not zeroes. Expose partial observed sums separately."""
    latest = {}
    ids = {video.id for video in videos}
    for row in sorted(rows, key=lambda row: (row.observed_at, row.id)):
        if row.kind == "video_day" and row.video_id in ids and start <= row.period_start == row.period_end <= end:
            latest[row.video_id, row.period_start] = row
    expected = []
    for video in videos:
        published = video.published_at.replace(tzinfo=UTC).astimezone(PACIFIC).date() if video.published_at else None
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if published is None or day >= published:
                expected.append((video.id, day))
    selected = [latest[key] for key in expected if key in latest]
    reason = "NO_VIDEOS" if not expected else "PARTIAL_COVERAGE" if len(selected) < len(expected) else None
    metrics = {}
    for metric in OVERVIEW_METRICS:
        values = [row.values[metric] for row in selected if row.values.get(metric) is not None]
        absent = {row.missing_reasons.get(metric, "UNAVAILABLE") for row in selected if row.values.get(metric) is None}
        missing = reason or ("/".join(sorted(absent)) if absent else None)
        metrics[metric] = MetricRead(value=sum(values) if not missing else None, missingReason=missing,
                                    observedSubtotal=sum(values) if missing and values else None)
    return ReportRead(source="independent_aggregation", start=start, end=end, metrics=metrics, reason=reason,
                      returned=len(selected), expected=len(expected), observedAt=max((row.observed_at for row in selected), default=None))
