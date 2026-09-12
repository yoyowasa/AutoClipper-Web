from collections.abc import Sequence
from typing import Any, Protocol, TypeVar


USED_RANGES_SETTING = "_usedSourceRanges"


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
