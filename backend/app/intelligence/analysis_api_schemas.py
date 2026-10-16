from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.intelligence.analysis_schema import Review


class AnalysisStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    syncBefore: Literal["auto", "always", "never"] = "auto"


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


class AnalysisHistoryRead(BaseModel):
    latestRun: AnalysisRunRead | None
    latestResult: AnalysisRunRead | None
    history: list[AnalysisRunRead]
