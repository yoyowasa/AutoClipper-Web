"""Compact report serialization and explicitly covered additive daily summaries."""

from collections import Counter
from datetime import timedelta

ADDITIVE_METRICS = frozenset({"views", "engagedViews", "estimatedMinutesWatched", "likes", "comments", "shares",
                              "subscribersGained", "subscribersLost"})
REPORT_DEFAULTS = {"source": "youtube_analytics", "definition_version": "youtube-native-2026-10-v1",
                   "report_timezone": "America/Los_Angeles"}


def native_report(row, *, kind=None) -> dict:
    report = {"id": f"r:{row.id}", "kind": kind or row.kind, "period": [str(row.period_start), str(row.period_end)],
              "observed_at": row.observed_at.isoformat() + "Z", "values": {}, "missing": {}}
    for key in REPORT_DEFAULTS:
        if getattr(row, key) != REPORT_DEFAULTS[key]:
            report[key] = getattr(row, key)
    partition = row.dimensions.get("creatorContentType")
    if partition:
        report["creatorContentType"] = partition
    for metric, value in row.values.items():
        if value is None:
            report["missing"][metric] = row.missing_reasons.get(metric, "UNAVAILABLE")
        else:
            report["values"][metric] = value
    return report


def summarize_video_days(video_id, rows, start, end) -> list[dict]:
    if not rows:
        return []
    days = {row.period_start: row for row in sorted(rows, key=lambda row: (row.observed_at, row.id))}
    rows = list(days.values())
    values, missing = {}, {}
    for metric in sorted(ADDITIVE_METRICS):
        if all(row.values.get(metric) is not None for row in rows):
            values[metric] = sum(row.values[metric] for row in rows)
        else:
            reasons = Counter(row.missing_reasons.get(metric, "UNAVAILABLE") for row in rows if row.values.get(metric) is None)
            missing[metric] = dict(sorted(reasons.items()))
    expected = (end - start).days + 1
    total = {"id": f"v:{video_id}:period_total", "kind": "period_total", "period": [str(start), str(end)],
             "observed_at": max(row.observed_at for row in rows).isoformat() + "Z", "values": values, "missing": missing,
             "coverage": {"returned_days": len(days), "unreturned_days": expected - len(days),
                          "complete": len(days) == expected, "method": "sum_returned_days_additive_metrics_only"}}
    # Keep native definition differences visible; never combine incompatible series.
    definitions = {(row.source, row.definition_version, row.report_timezone) for row in rows}
    if len(definitions) != 1:
        total["values"], total["missing"] = {}, {metric: "INCOMPATIBLE_DEFINITIONS" for metric in sorted(ADDITIVE_METRICS)}
    else:
        source, definition, timezone = next(iter(definitions))
        total.update(source=source, definition_version=definition, report_timezone=timezone)
    peaks = [row for row in rows if row.values.get("views") is not None]
    return [total, *([native_report(max(peaks, key=lambda row: (row.values["views"], row.period_start)), kind="peak_day")]
                    if peaks else [])]


def reports_for_video(video_id, rows, start, end) -> tuple[list[dict], int]:
    selected = [row for row in rows if row.kind != "video_day"]
    periods = [row for row in selected if row.kind == "video_period"]
    duplicates = {row.id for row in selected if row.kind == "video_format" and any(
        (row.period_start, row.period_end, row.source, row.definition_version, row.report_timezone, row.values, row.missing_reasons)
        == (other.period_start, other.period_end, other.source, other.definition_version,
            other.report_timezone, other.values, other.missing_reasons) for other in periods)}
    reports = [native_report(row) for row in selected if row.id not in duplicates]
    daily = [row for row in rows if row.kind == "video_day"]
    reports.extend(summarize_video_days(video_id, daily, start, end))
    if not daily:
        reports.append({"id": f"v:{video_id}:period_total", "kind": "period_total", "period": [str(start), str(end)],
                        "values": {}, "missing": {"report": "NO_DAILY_ROWS"}})
    # Unreturned initial/recent-period reports are missing, not zero.
    for kind in ("first7", "first30", "video_period"):
        if not any(report["kind"] == kind for report in reports):
            reports.append({"id": f"v:{video_id}:{kind}", "kind": kind, "values": {}, "missing": {"report": "NO_ROWS"}})
    return reports, len(duplicates)


def within_input_period(row, last, start) -> bool:
    if row.kind in {"daily", "video_day"}:
        return start <= row.period_start == row.period_end <= last
    if row.kind in {"current", "video_period", "video_format"}:
        return (row.period_start, row.period_end) == (last - timedelta(days=27), last)
    if row.kind == "previous":
        return (row.period_start, row.period_end) == (last - timedelta(days=55), last - timedelta(days=28))
    return row.kind in {"first7", "first30"}
