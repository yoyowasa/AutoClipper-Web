"""Normalize valid short context ranges without changing the finished clip."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SHORT_PARENT_MIN_RATIO = 1.5
SHORT_PARENT_MAX_RATIO = 3.0


class ShortParentRangeAdjustment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    proposal_id: str = Field(alias="proposalId")
    reason: Literal["parent_ratio_adjusted"] = "parent_ratio_adjusted"
    original_start: float = Field(alias="originalParentStart")
    original_end: float = Field(alias="originalParentEnd")
    original_ratio: float = Field(alias="originalRatio")
    adjusted_start: float = Field(alias="adjustedParentStart")
    adjusted_end: float = Field(alias="adjustedParentEnd")
    adjusted_ratio: float = Field(alias="adjustedRatio")
    source_limited: bool = Field(alias="sourceLimited")


def adjust_short_parent_range(
    proposal_id: str, *, start: float, end: float, parent_start: float, parent_end: float, source_duration: float,
) -> ShortParentRangeAdjustment | None:
    """Return an audit record for an out-of-band, already validated range."""
    duration = end - start
    ratio = (parent_end - parent_start) / duration
    if (SHORT_PARENT_MIN_RATIO <= ratio <= SHORT_PARENT_MAX_RATIO
            or math.isclose(ratio, SHORT_PARENT_MIN_RATIO) or math.isclose(ratio, SHORT_PARENT_MAX_RATIO)):
        return None
    target_ratio = max(SHORT_PARENT_MIN_RATIO, min(SHORT_PARENT_MAX_RATIO, ratio))
    desired_duration = duration * target_ratio
    available_duration = min(source_duration, desired_duration)
    center = start + duration / 2
    adjusted_start = max(0.0, min(center - available_duration / 2, source_duration - available_duration))
    adjusted_end = min(source_duration, adjusted_start + available_duration)
    return ShortParentRangeAdjustment(
        proposalId=proposal_id, originalParentStart=parent_start, originalParentEnd=parent_end, originalRatio=ratio,
        adjustedParentStart=adjusted_start, adjustedParentEnd=adjusted_end,
        adjustedRatio=(adjusted_end - adjusted_start) / duration, sourceLimited=source_duration < desired_duration,
    )
