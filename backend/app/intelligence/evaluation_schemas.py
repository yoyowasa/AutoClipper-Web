"""Persisted independent observations, without YouTube titles or assumed effects."""
from typing import Literal
from pydantic import BaseModel, Field, JsonValue

from app.intelligence.report_schemas import ReportRead


class VideoGoalRead(BaseModel):
    video_id: str
    format: str
    target_views: int | None
    status: Literal["pending", "insufficient_data", "reached", "below_target"]
    reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    first7: ReportRead
    first30: ReportRead


class ChoiceObservationRead(BaseModel):
    record_id: str
    record_family_id: str
    choice_id: str
    video_id: str
    kind: str
    role: str
    source: str
    policy_version: str | None
    value_hash: str
    selected_ids: list[str]
    values: dict[str, JsonValue] | None
    values_omitted: bool
    evaluation: VideoGoalRead


class ChoiceGroupRead(BaseModel):
    id: str
    character_preset_name: str
    format: str
    kind: str
    role: str
    source: str
    policy_version: str | None
    implementation_version: str | None = None
    option_values: dict[str, JsonValue]
    count: int
    judged_count: int
    sufficient: bool
    effect: Literal["unconfirmed"] = "unconfirmed"
    target_views: int | None
    median_views: float | None
    reached_count: int
    attainment_rate: float | None
    video_ids: list[str]
    observations: list[ChoiceObservationRead]


class ChoiceEvaluationsRead(BaseModel):
    source: Literal["independent_aggregation"] = "independent_aggregation"
    label: str = "独自集計：制作上の選択ごとの30日評価（効果未確認）"
    minimum_group_videos: int = 5
    window_days: Literal[30] = 30
    interim_days: Literal[7] = 7
    linked_videos: int = 0
    excluded_reasons: dict[str, int] = Field(default_factory=dict)
    groups: list[ChoiceGroupRead] = Field(default_factory=list)
    expires_at: str | None = None
