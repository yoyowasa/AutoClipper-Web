"""Shared, bounded hint contracts. Old jobs/records have no hints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HintGroupReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: str = Field(min_length=1, max_length=80)
    count: int = Field(ge=5)


class PerformanceHint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    character_preset_name: str = Field(min_length=1, max_length=80)
    format: Literal["normal", "short"]
    target: Literal["selection", "title_hook"]
    text: str = Field(min_length=1, max_length=400)
    evidence_groups: list[HintGroupReference] = Field(min_length=1, max_length=5)
    video_ids: list[str] = Field(min_length=5, max_length=20)
    confidence: Literal["low", "medium"] = "low"


class UsedPerformanceHint(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    analysis_id: str = Field(alias="analysisId", max_length=64)
    generated_at: datetime = Field(alias="generatedAt")
    expires_at: datetime = Field(alias="expiresAt")
    target: Literal["selection", "title_hook"]
    text: str = Field(min_length=1, max_length=400)
    format: Literal["normal", "short"]
