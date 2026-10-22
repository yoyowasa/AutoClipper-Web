from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.dashboard_schemas import ReportRead

TrialMetric = Literal["engagedViews", "views", "averageViewPercentage", "averageViewDuration", "subscribersGained"]


class TrialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    baselineVideoId: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    targetVideoId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{11}$")
    changeNote: str = Field(min_length=1, max_length=1000)
    keepFixed: str = Field(max_length=1000)
    primaryMetric: TrialMetric
    rejectionCondition: str = Field(min_length=1, max_length=1000)
    resultCheck: str = Field(max_length=1200)
    status: Literal["active", "closed"] = "active"
    expectedUpdatedAt: datetime


class TrialVideoRead(BaseModel):
    id: str
    title: str | None
    publishedAt: datetime | None
    format: str
    durationBand: str
    first7: ReportRead


class TrialRead(BaseModel):
    id: str
    channelId: int
    analysisId: str
    proposalId: str
    baselineVideoId: str
    targetVideoId: str | None
    changeNote: str
    keepFixed: str
    primaryMetric: TrialMetric
    rejectionCondition: str
    resultCheck: str
    status: Literal["active", "closed"]
    createdAt: datetime
    registeredAt: datetime
    updatedAt: datetime
    baseline: TrialVideoRead | None
    target: TrialVideoRead | None
    comparisonIssues: list[str]
    direction: Literal["increase", "decrease", "same"] | None
    recordedAfterPublication: bool
    causalVerdict: str = "公開時期・題材・流入・視聴者が異なるため、変更の効果とは断定できません。"
