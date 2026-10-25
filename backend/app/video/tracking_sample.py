"""Measured source-frame regions retained separately from aggregate crop decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackingSample:
    start: float
    end: float
    box: tuple[float, float, float, float]
    confidence: float
    source: str


def region_sample(region, *, start: float, end: float, source: str) -> TrackingSample:
    return TrackingSample(
        start=start, end=end,
        box=(
            max(0.0, region.center_x - region.width / 2),
            max(0.0, region.center_y - region.height / 2),
            min(1.0, region.center_x + region.width / 2),
            min(1.0, region.center_y + region.height / 2),
        ),
        confidence=region.confidence, source=source,
    )
