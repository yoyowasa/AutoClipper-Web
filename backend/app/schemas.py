from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal[
    "uploaded",
    "queued",
    "probing",
    "extracting_audio",
    "transcribing",
    "detecting_scenes",
    "generating_candidates",
    "scoring_candidates",
    "selecting_clips",
    "rendering_normal_clips",
    "rendering_shorts",
    "packaging_zip",
    "completed",
    "failed",
]

ExportType = Literal["normal", "short"]


class VideoRead(BaseModel):
    id: str
    original_filename: str
    stored_path: str
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoUploadResponse(BaseModel):
    video_id: str = Field(alias="videoId")
    filename: str


class JobCreateRequest(BaseModel):
    video_id: str = Field(alias="videoId")
    settings: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus


class JobError(BaseModel):
    code: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    status: JobStatus
    progress: int
    current_step: str = Field(alias="currentStep")
    details: dict[str, Any] = Field(default_factory=dict)
    error: JobError | None


class ExportItemRead(BaseModel):
    id: str
    job_id: str
    video_id: str
    candidate_id: str | None
    type: ExportType
    title: str
    duration: float
    score: float
    video_path: str
    subtitle_path: str | None
    metadata_path: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResultExportItem(BaseModel):
    id: str
    type: ExportType
    title: str
    duration: float
    score: float
    video_url: str = Field(alias="videoUrl")
    download_url: str = Field(alias="downloadUrl")


class JobResultsResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    zip_download_url: str = Field(alias="zipDownloadUrl")
    normal_clips: list[ResultExportItem] = Field(alias="normalClips")
    shorts: list[ResultExportItem]
