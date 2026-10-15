from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecordSummary(BaseModel):
    familyId: str
    recordId: str
    publicationTitle: str
    type: Literal["normal", "short"]
    revision: int
    createdAt: datetime
    characterPresetName: str | None
    ambiguous: bool
    mode: Literal["auto", "manual", "manual_unlinked"] | None = None


class LinkedVideoRead(BaseModel):
    id: str
    channelId: int
    title: str | None
    publishedAt: datetime | None


class ProductionLinkRead(BaseModel):
    familyId: str
    recordId: str
    mode: Literal["auto", "manual"]
    linkedAt: datetime | None
    updatedAt: datetime
    record: RecordSummary | None
    video: LinkedVideoRead


class ProductionLinksRead(BaseModel):
    links: list[ProductionLinkRead]
    unlinkedRecords: list[RecordSummary]
    unlinkedVideos: list[LinkedVideoRead]
    linkedCount: int
    unlinkedRecordCount: int
    unlinkedVideoCount: int
    issues: list[dict[str, str]]


class ProductionLinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    youtubeVideoId: str | None = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
