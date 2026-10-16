from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.analysis_schema import Review


class AnalysisStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    syncBefore: Literal["auto", "always", "never"] = "auto"


class ValidationIssueRead(BaseModel):
    code: str
    loc: list[str | int]


class ValidationReportRead(BaseModel):
    excludedFindings: int = 0
    excludedProposals: int = 0
    reasonCounts: dict[str, int] = Field(default_factory=dict)
    issues: list[ValidationIssueRead] = Field(default_factory=list)
    fatal: bool = False


class AnalysisRunRead(BaseModel):
    id: str
    status: Literal["queued", "running", "success", "failed", "expired"]
    queuedAt: datetime
    startedAt: datetime | None
    finishedAt: datetime | None
    expiresAt: datetime
    errorCode: str | None
    errorMessage: str | None
    model: str
    reasoning: str
    requestId: str | None
    syncBefore: str
    syncRunId: str | None
    review: Review | None
    validation: ValidationReportRead | None = None


class AnalysisHistoryRead(BaseModel):
    latestRun: AnalysisRunRead | None
    latestResult: AnalysisRunRead | None
    history: list[AnalysisRunRead]
