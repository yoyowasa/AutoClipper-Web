from collections.abc import Sequence
from typing import Any, Protocol, TypeVar


USED_RANGES_SETTING = "_usedSourceRanges"
PREVIOUS_PROPOSALS_SETTING = "_previousProposedRanges"


class TimedItem(Protocol):
    start: float
    end: float


T = TypeVar("T", bound=TimedItem)


def used_ranges(settings: dict[str, Any]) -> list[tuple[float, float]]:
    return [tuple(item) for item in settings.get(USED_RANGES_SETTING, [])]


def overlaps_used(start: float, end: float, ranges: Sequence[tuple[float, float]]) -> bool:
    # Touching endpoints are not duplicates. Do not use a ratio: even a short
    # reused scene inside a much longer normal clip must be excluded.
    return any(min(end, old_end) - max(start, old_start) > 0.001 for old_start, old_end in ranges)


def unused_items(items: Sequence[T], settings: dict[str, Any]) -> list[T]:
    ranges = used_ranges(settings)
    return [item for item in items if not overlaps_used(item.start, item.end, ranges)]


def merge_ranges(ranges: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def with_reselection_exclusions(settings: dict[str, Any], previous_plan: Any) -> dict[str, Any]:
    """Avoid earlier proposals in this job without marking them as exported footage."""
    if previous_plan is None:
        return settings
    previous = [
        *previous_plan.settings.get(PREVIOUS_PROPOSALS_SETTING, []),
        *previous_plan.settings.get("_reselectionExcludedRanges", []),
    ]
    ranges = sorted(set([
        *[tuple(item) for item in previous],
        *[(clip.start, clip.end) for clip in previous_plan.clips if clip.end > clip.start],
    ]))
    if not settings.get("excludePreviousSelection"):
        # OFF allows overlapping old material for a longer edit, but the old
        # proposals remain available for near-duplicate prevention.
        return {**settings, PREVIOUS_PROPOSALS_SETTING: ranges}
    return {
        **settings,
        PREVIOUS_PROPOSALS_SETTING: ranges,
        "_reselectionExcludedRanges": merge_ranges(ranges),
        USED_RANGES_SETTING: merge_ranges([*used_ranges(settings), *ranges]),
    }


def near_duplicate_of_previous(
    start: float, end: float, settings: dict[str, Any], *, threshold: float = 0.9,
) -> bool:
    """Reject almost unchanged proposals while allowing substantially longer edits."""
    duration = end - start
    if duration <= 0:
        return False
    for old_start, old_end in settings.get(PREVIOUS_PROPOSALS_SETTING, []):
        old_duration = old_end - old_start
        overlap = max(0.0, min(end, old_end) - max(start, old_start))
        if old_duration > 0 and overlap / max(duration, old_duration) >= threshold:
            return True
    return False
