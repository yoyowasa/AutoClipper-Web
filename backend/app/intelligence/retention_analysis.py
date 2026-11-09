"""Summarize fixed-window curves and keep weekly cohorts outside the video budget."""

import math
from collections import defaultdict
from datetime import UTC, timedelta
from statistics import median

from app.intelligence.collection import RETENTION_DEFINITION, RETENTION_WINDOWS
from app.intelligence.dashboard_reports import native_window
from app.intelligence.evaluation_rules import PACIFIC, initial_window
from app.intelligence.youtube_client import RETENTION_METRICS

FORMATS = {"shorts": "shorts", "long": "videoondemand", "live": "live", "unknown": "unknown"}
SECONDS = (3, 10, 20, 30)
PERCENTAGES = (25, 50, 90)


def pacific_day(stamp):
    return stamp.replace(tzinfo=UTC).astimezone(PACIFIC).date()


def retention_reports(video, rows, today, last):
    reports = []
    if video.published_at is None:
        return reports
    by_window = {(row.kind, row.period_start, row.period_end): row for row in rows
                 if row.definition_version == RETENTION_DEFINITION and row.source == "youtube_analytics"
                 and row.report_timezone == PACIFIC.key}
    for kind, days in RETENTION_WINDOWS.items():
        begin, end = initial_window(video.published_at, days)
        row = by_window.get((kind, begin, end))
        report = {"id": f"v:{video.id}:{kind}", "kind": kind, "period": [str(begin), str(end)],
                  "definition_version": RETENTION_DEFINITION, "values": {}, "missing": {}}
        if end >= today or end > last or row is None or not any(row.values.values()):
            reason = ("WINDOW_NOT_REACHED" if end >= today else "REPORT_NOT_RETURNED" if end > last or row is None
                      else next(iter(row.missing_reasons.values()), "NO_ROWS"))
            report["missing"]["report"] = reason
        else:
            report["observed_at"] = row.observed_at.isoformat() + "Z"
            _sample_curve(report, row, video.duration_seconds)
        reports.append(report)
    return reports


def _sample_curve(report, row, duration):
    # The ratio is the exclusive end of a bucket. Use the bucket that
    # contains the requested instant, without interpolation or extrapolation.
    points = {f"watch_at_{percent}pct": (RETENTION_METRICS[0], percent) for percent in PERCENTAGES}
    for second in SECONDS:
        bucket = math.floor(100 * second / duration) + 1 if duration and second < duration else None
        points[f"watch_at_{second}s"] = (RETENTION_METRICS[0], bucket)
    points["relative_at_3s"] = (RETENTION_METRICS[1], points["watch_at_3s"][1])
    report["sample_ratios"] = {}
    for name, (metric, bucket) in points.items():
        if bucket is None:
            report["missing"][name] = "OUTSIDE_DURATION" if duration else "DURATION_UNAVAILABLE"
            continue
        ratio = f"{bucket / 100:.2f}"
        report["sample_ratios"][name] = float(ratio)
        value = (row.values.get(metric) or {}).get(ratio)
        if value is None:
            report["missing"][name] = row.missing_reasons.get(metric, "BUCKET_NOT_RETURNED")
        else:
            report["values"][name] = value


def weekly_trends(videos, rows, curves, timings, today, last):
    cutoff = today - timedelta(days=89)
    groups = defaultdict(list)
    for video in videos:
        if video.published_at is None:
            continue
        day = pacific_day(video.published_at)
        if cutoff <= day <= today:
            week = day - timedelta(days=day.weekday())
            groups[week, FORMATS.get(video.format, "unknown")].append(video)
    result = []
    for (week, format), members in sorted(groups.items()):
        views, source_days = [], []
        metrics = defaultdict(list)
        for video in members:
            start, end = initial_window(video.published_at, 7)
            if end <= last:
                value = native_window(rows[video.id], "first7", start, end, expected_format=video.format).metrics["views"].value
                if value is not None:
                    views.append(value)
            timing = timings.get(video.id)
            if timing:
                source_days.append(timing["days_since_source"])
            for report in curves[video.id]:
                for name, value in report["values"].items():
                    metrics[f"{report['kind']}:{name}"].append(value)
        result.append({"id": f"w:{week}:{format}", "source": "independent_aggregation",
                       "format": format, "week_start": str(week), "video_count": len(members),
                       "first7_views": _summary(views),
                       "retention": {key: _summary(values) for key, values in sorted(metrics.items())},
                       "days_since_source": {**_summary(source_days), "min": min(source_days, default=None),
                                             "max": max(source_days, default=None),
                                             "counts_by_age": {"0_1": sum(day <= 1 for day in source_days),
                                                               "2_7": sum(2 <= day <= 7 for day in source_days),
                                                               "8_30": sum(8 <= day <= 30 for day in source_days),
                                                               "31_plus": sum(day >= 31 for day in source_days)}}})
    return {"source": "independent_aggregation", "period": [str(cutoff), str(today)],
            "report_timezone": "America/Los_Angeles", "week_starts": "Monday", "groups": result}


def _summary(values):
    return {"count": len(values), "median": median(values) if values else None}
