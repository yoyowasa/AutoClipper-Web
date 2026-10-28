"""Read models keep missing observations distinct from measured zeroes."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from app.intelligence.evaluation_schemas import VideoGoalRead
from app.intelligence.report_schemas import MetricRead as MetricRead, ReportRead as ReportRead


class DashboardVideoRead(BaseModel):
    id: str
    title: str | None
    publishedAt: datetime | None
    durationSeconds: float | None
    format: str
    durationBand: str
    current: ReportRead
    first7: ReportRead
    goal: VideoGoalRead | None = None
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
