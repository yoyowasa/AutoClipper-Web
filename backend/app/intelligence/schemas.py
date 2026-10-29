from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class OAuthStartRequest(BaseModel):
    channel_external_id: str = Field(alias="channelExternalId", pattern=r"^UC[A-Za-z0-9_-]{22}$")


class OAuthStartResponse(BaseModel):
    authorizationUrl: str


class SyncRunRead(BaseModel):
    id: str
    status: Literal["queued", "running", "success", "partial", "failed"]
    queuedAt: datetime
    finishedAt: datetime | None
    errorCode: str | None
    errorMessage: str | None
    requestedStart: date | None
    requestedEnd: date | None
    lastReportDate: date | None
    fetchedCount: int
    truncated: bool
    missingReportCount: int


class ChannelRead(BaseModel):
    id: int
    externalId: str
    name: str | None
    connectionStatus: Literal["connected", "reconnect_required"]
    errorMessage: str | None
    lastSyncAt: datetime | None
    latestRun: SyncRunRead | None


class YouTubeAutomationRead(BaseModel):
    enabled: bool
    syncHourUtc: int = Field(ge=0, le=23)
    analysisWeekday: int = Field(ge=0, le=6)
    timezone: Literal["UTC"] = "UTC"


class YouTubeConnectionsRead(BaseModel):
    clientConfigured: bool
    channels: list[ChannelRead]
    derivedAllowed: bool
    extendedStorage: bool
    reviewedAt: str
    policyReference: str
    automation: YouTubeAutomationRead | None = None
