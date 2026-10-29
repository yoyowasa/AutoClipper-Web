"""Fixed goals and complete calendar-day windows, shared by collection and evaluation."""
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
GOALS = {"normal_views": 100_000, "short_views": 1_000_000, "window_days": 30, "interim_days": 7}


def initial_window(published, days):
    # Match existing first7/trial comparisons: skip the partial publication day.
    published = published if published.tzinfo else published.replace(tzinfo=UTC)
    start = published.astimezone(PACIFIC).date() + timedelta(days=1)
    return start, start + timedelta(days=days - 1)


def goal_target(format):
    return GOALS["short_views"] if format in {"short", "shorts"} else GOALS["normal_views"] if format in {"normal", "long"} else None
