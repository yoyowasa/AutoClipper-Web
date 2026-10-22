"""Read models keep missing observations distinct from measured zeroes."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MetricRead(BaseModel):
    value: float | None = None
    missingReason: str | None = None
    observedSubtotal: float | None = None


class ReportRead(BaseModel):
    source: Literal["youtube_analytics", "independent_aggregation"] = "youtube_analytics"
    start: date | None = None
    end: date | None = None
    observedAt: datetime | None = None
    metrics: dict[str, MetricRead]
    reason: str | None = None
    returned: int | None = None
    expected: int | None = None
    format: str = "unknown"


class DashboardVideoRead(BaseModel):
    id: str
    title: str | None
    publishedAt: datetime | None
    durationSeconds: float | None
    format: str
    durationBand: str
    current: ReportRead
    first7: ReportRead
    production: dict[str, Any] | None = None
    productionMissing: str | None = None
    aggregateGroupIds: list[str] = Field(default_factory=list)


class DashboardRead(BaseModel):
    channelId: int
    format: Literal["all", "shorts", "long"]
    lastReportDate: date | None
    syncRunId: str | None
    current: ReportRead
    previous: ReportRead
    daily: list[ReportRead]
    videos: list[DashboardVideoRead]
    excludedMetadataCount: int
    unknownFormatCount: int
    scopeNote: str


class EvidenceVideosRead(BaseModel):
    analysisId: str
    evidenceVideos: dict[str, list[str]]
