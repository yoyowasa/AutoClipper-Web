from typing import Literal

from pydantic import BaseModel, Field


class AggregateMetricRead(BaseModel):
    count: int
    median: float | None
    baseline_count: int
    baseline_median: float | None
    relative_to_channel_median: float | None
    missing_reason: str | None


class AggregateGroupRead(BaseModel):
    id: str
    character_preset_name: str
    format: Literal["normal", "short"]
    dimension: str
    value: str
    count: int
    sufficient: bool
    status: Literal["available", "insufficient_data"]
    metrics: dict[str, AggregateMetricRead]
    video_ids: list[str]


class ProductionAggregatesRead(BaseModel):
    source: Literal["independent_aggregation"]
    label: str
    channel_id: int
    generated_at: str
    expires_at: str
    minimum_group_videos: int
    linked_videos: int
    excluded_linked_videos: int
    excluded_reasons: dict[str, int] = Field(default_factory=dict)
    record_issues: int
    baselines: dict[str, dict[str, dict[str, int | float | None]]]
    groups: list[AggregateGroupRead]
