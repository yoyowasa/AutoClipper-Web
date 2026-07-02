from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
ClipMode = Literal["low_cost", "fast", "high_quality"]
ClipProfile = Literal["auto", "talk", "gameplay", "lecture"]
ShortLayout = Literal["auto", "face_tracking_crop", "center_crop", "blur_background"]
SelectionPolicy = Literal["fill_requested", "strict_quality"]
ShortOverlayTitleMode = Literal["auto", "always", "high_quality_only", "never"]


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


class JobSettings(BaseModel):
    mode: ClipMode = "high_quality"
    profile: ClipProfile = "auto"
    normal_clip_count: int = Field(default=2, ge=0, alias="normalClipCount")
    short_count: int = Field(default=3, ge=0, alias="shortCount")
    normal_min_duration: float = Field(default=90.0, gt=0, alias="normalMinDuration")
    normal_max_duration: float = Field(default=600.0, gt=0, alias="normalMaxDuration")
    short_min_duration: float = Field(default=20.0, gt=0, alias="shortMinDuration")
    short_max_duration: float = Field(default=75.0, gt=0, alias="shortMaxDuration")
    max_candidates: int = Field(default=1200, gt=0, alias="maxCandidates")
    max_raw_candidates_per_type: int = Field(default=250_000, gt=0, alias="maxRawCandidatesPerType")
    max_kept_candidates_per_type: int = Field(default=1200, gt=0, alias="maxKeptCandidatesPerType")
    max_candidates_per_time_bucket: int = Field(default=100, gt=0, alias="maxCandidatesPerTimeBucket")
    candidate_time_bucket_seconds: float = Field(default=300.0, gt=0, alias="candidateTimeBucketSeconds")
    max_candidate_generation_memory_mb: int = Field(default=12_000, gt=0, alias="maxCandidateGenerationMemoryMb")
    candidate_chunk_seconds: float = Field(default=600.0, gt=0, alias="candidateChunkSeconds")
    candidate_chunk_overlap_seconds: float = Field(default=75.0, ge=0, alias="candidateChunkOverlapSeconds")
    burn_subtitles: bool = Field(default=True, alias="burnSubtitles")
    max_chars_per_line_short: int = Field(default=16, ge=6, le=80, alias="maxCharsPerLineShort")
    max_chars_per_line_normal: int = Field(default=28, ge=8, le=100, alias="maxCharsPerLineNormal")
    max_lines: int = Field(default=2, ge=1, le=2, alias="maxLines")
    min_subtitle_duration: float = Field(default=1.1, gt=0, alias="minSubtitleDuration")
    max_subtitle_duration: float = Field(default=4.2, gt=0, alias="maxSubtitleDuration")
    min_gap_between_subtitles: float = Field(default=0.08, ge=0, alias="minGapBetweenSubtitles")
    normalize_audio: bool = Field(default=False, alias="normalizeAudio")
    short_layout: ShortLayout = Field(default="auto", alias="shortLayout")
    short_overlay_title_mode: ShortOverlayTitleMode = Field(default="auto", alias="shortOverlayTitleMode")
    selection_policy: SelectionPolicy = Field(default="fill_requested", alias="selectionPolicy")
    cross_type_overlap_dedupe: bool = Field(default=False, alias="crossTypeOverlapDedupe")
    use_openai_scoring: bool = Field(default=False, alias="useOpenAIScoring")
    openai_candidate_limit: int = Field(default=40, ge=0, alias="openaiCandidateLimit")
    openai_model: str = Field(default="gpt-5.5", min_length=1, alias="openaiModel")
    openai_fallback_to_rule_score: bool = Field(default=True, alias="openaiFallbackToRuleScore")
    ensure_selected_openai_scored: bool | None = Field(default=None, alias="ensureSelectedOpenAIScored")
    openai_finalist_scoring_limit: int | None = Field(default=None, ge=0, alias="openaiFinalistScoringLimit")
    enable_boundary_refinement: bool = Field(default=True, alias="enableBoundaryRefinement")
    boundary_leading_padding_seconds: float = Field(default=0.4, ge=0, alias="boundaryLeadingPaddingSeconds")
    boundary_trailing_padding_seconds: float = Field(default=0.6, ge=0, alias="boundaryTrailingPaddingSeconds")
    max_boundary_expansion_seconds: float = Field(default=3.0, ge=0, alias="maxBoundaryExpansionSeconds")
    allow_boundary_expansion_beyond_max_duration: bool = Field(
        default=False,
        alias="allowBoundaryExpansionBeyondMaxDuration",
    )
    e2e_fixture_transcript: bool = Field(default=False, alias="e2eFixtureTranscript")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="after")
    def validate_duration_ranges(self) -> "JobSettings":
        if self.normal_max_duration < self.normal_min_duration:
            raise ValueError("normalMaxDuration must be >= normalMinDuration")
        if self.short_max_duration < self.short_min_duration:
            raise ValueError("shortMaxDuration must be >= shortMinDuration")
        if self.max_subtitle_duration < self.min_subtitle_duration:
            raise ValueError("maxSubtitleDuration must be >= minSubtitleDuration")
        if self.ensure_selected_openai_scored is None:
            self.ensure_selected_openai_scored = self.mode == "high_quality"
        if self.openai_finalist_scoring_limit is None:
            requested_count = self.normal_clip_count + self.short_count
            self.openai_finalist_scoring_limit = requested_count + 2 if requested_count > 0 else 0
        return self


class JobCreateRequest(BaseModel):
    video_id: str = Field(alias="videoId")
    settings: JobSettings = Field(default_factory=JobSettings)


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
    candidate_id: str | None = Field(default=None, alias="candidateId")
    title: str
    title_source: str | None = Field(default=None, alias="titleSource")
    duration: float
    score: float
    final_score: float | None = Field(default=None, alias="finalScore")
    rule_score: float | None = Field(default=None, alias="ruleScore")
    ai_score: float | None = Field(default=None, alias="aiScore")
    selection_reason: str | None = Field(default=None, alias="selectionReason")
    below_quality_threshold: bool | None = Field(default=None, alias="belowQualityThreshold")
    quality_warning: str | None = Field(default=None, alias="qualityWarning")
    openai_score_source: str | None = Field(default=None, alias="openaiScoreSource")
    boundary_refined: bool | None = Field(default=None, alias="boundaryRefined")
    overlay_title_expected: bool | None = Field(default=None, alias="overlayTitleExpected")
    overlay_title_rendered: bool | None = Field(default=None, alias="overlayTitleRendered")
    start: float | None = None
    end: float | None = None
    original_start: float | None = Field(default=None, alias="originalStart")
    original_end: float | None = Field(default=None, alias="originalEnd")
    refined_start: float | None = Field(default=None, alias="refinedStart")
    refined_end: float | None = Field(default=None, alias="refinedEnd")
    resolution: dict[str, Any] | None = None
    audit_warnings: list[str] = Field(default_factory=list, alias="auditWarnings")
    subtitle_path: str | None = Field(default=None, alias="subtitlePath")
    subtitle_url: str | None = Field(default=None, alias="subtitleUrl")
    metadata_path: str | None = Field(default=None, alias="metadataPath")
    metadata_url: str | None = Field(default=None, alias="metadataUrl")
    video_url: str = Field(alias="videoUrl")
    download_url: str = Field(alias="downloadUrl")


class JobAuditSummary(BaseModel):
    available: bool = True
    generated_normal_count: int | None = Field(default=None, alias="generatedNormalCount")
    generated_short_count: int | None = Field(default=None, alias="generatedShortCount")
    clips_requiring_human_visual_inspection_count: int | None = Field(
        default=None,
        alias="clipsRequiringHumanVisualInspectionCount",
    )
    warnings_by_type: dict[str, dict[str, int]] = Field(default_factory=dict, alias="warningsByType")
    warning_counts: dict[str, int] = Field(default_factory=dict, alias="warningCounts")


class JobResultsResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    zip_download_url: str = Field(alias="zipDownloadUrl")
    audit_summary: JobAuditSummary | None = Field(default=None, alias="auditSummary")
    normal_clips: list[ResultExportItem] = Field(alias="normalClips")
    shorts: list[ResultExportItem]
