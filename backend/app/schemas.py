from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.candidates.merge_boundaries import ClipTextStyle
from app.posting_metadata import (
    PostMetadataSource,
    YouTubePostingProfile,
    YouTubeTitleCandidate,
)


JobStatus = Literal[
    "uploaded",
    "queued",
    "probing",
    "awaiting_manual_edit",
    "extracting_audio",
    "transcribing",
    "correcting_subtitles",
    "detecting_scenes",
    "generating_candidates",
    "scoring_candidates",
    "selecting_clips",
    "reselecting_clips",
    "preparing_clip_review",
    "awaiting_clip_review",
    "preparing_subtitle_review",
    "awaiting_subtitle_review",
    "rendering_normal_clips",
    "rendering_shorts",
    "packaging_zip",
    "completed",
    "failed",
]

ExportType = Literal["normal", "short"]
ClipMode = Literal["low_cost", "fast", "high_quality"]
ClipProfile = Literal["auto", "talk", "gameplay", "lecture"]
WorkflowMode = Literal["automatic", "manual"]
AutomationMode = Literal["manual", "shadow", "guarded", "auto"]
ManualSubtitleMode = Literal["auto", "none", "manual"]
ShortLayout = Literal["auto", "face_tracking_crop", "center_crop", "blur_background"]
SelectionPolicy = Literal["fill_requested", "strict_quality"]
InitialSelectionProvider = Literal["legacy", "codex"]
ClipSelectionPreset = Literal[
    "auto",
    "highlights",
    "funny",
    "important",
    "emotional",
    "informative",
]
ShortOverlayTitleMode = Literal["auto", "always", "high_quality_only", "never"]
WhisperModelSize = Literal["base", "small", "medium", "large-v3", "turbo"]
TranscriptionLanguage = Literal["ja"]
TranscriptionDevice = Literal["auto", "cpu", "cuda"]
TranscriptionComputeType = Literal["auto", "int8", "float16", "int8_float16"]
SubtitleCorrectionMode = Literal["off", "openai"]
SubtitleCorrectionScope = Literal["all", "suspicious"]
SubtitleCorrectionReasoningEffort = Literal[
    "default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
]


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


class CompletedVideoReeditResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    export_id: str = Field(alias="exportId")
    matched_clip_id: str | None = Field(default=None, alias="matchedClipId")
    clip_type: Literal["normal", "short"] = Field(alias="clipType")
    title: str
    review_state: str = Field(alias="reviewState")


class ClipTimeRange(BaseModel):
    start_seconds: float | None = Field(default=None, ge=0, alias="startSeconds")
    end_seconds: float | None = Field(default=None, ge=0, alias="endSeconds")

    model_config = ConfigDict(populate_by_name=True)


class SubtitleStyleSnapshot(BaseModel):
    subtitle_font_name: str | None = Field(default=None, min_length=1, alias="subtitleFontName")
    subtitle_font_size: int | None = Field(default=None, ge=12, le=220, alias="subtitleFontSize")
    subtitle_outline: int | None = Field(default=None, ge=0, le=20, alias="subtitleOutline")
    subtitle_lower_margin: int | None = Field(default=None, ge=0, le=1600, alias="subtitleLowerMargin")
    subtitle_alignment: int | None = Field(default=None, ge=1, le=9, alias="subtitleAlignment")
    subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="subtitlePrimaryColor",
    )
    subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="subtitleOutlineColor",
    )
    short_subtitle_font_name: str | None = Field(
        default=None,
        min_length=1,
        alias="shortSubtitleFontName",
    )
    short_subtitle_font_size: int | None = Field(
        default=None,
        ge=20,
        le=220,
        alias="shortSubtitleFontSize",
    )
    short_subtitle_outline: int | None = Field(
        default=None,
        ge=0,
        le=20,
        alias="shortSubtitleOutline",
    )
    short_subtitle_lower_margin: int | None = Field(
        default=None,
        ge=0,
        le=1600,
        alias="shortSubtitleLowerMargin",
    )
    short_subtitle_alignment: int | None = Field(
        default=None,
        ge=1,
        le=9,
        alias="shortSubtitleAlignment",
    )
    short_subtitle_x_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="shortSubtitleXPercent",
    )
    short_subtitle_y_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="shortSubtitleYPercent",
    )
    short_subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="shortSubtitlePrimaryColor",
    )
    short_subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="shortSubtitleOutlineColor",
    )
    normal_subtitle_font_name: str | None = Field(
        default=None,
        min_length=1,
        alias="normalSubtitleFontName",
    )
    normal_subtitle_font_size: int | None = Field(
        default=None,
        ge=12,
        le=180,
        alias="normalSubtitleFontSize",
    )
    normal_subtitle_outline: int | None = Field(
        default=None,
        ge=0,
        le=20,
        alias="normalSubtitleOutline",
    )
    normal_subtitle_lower_margin: int | None = Field(
        default=None,
        ge=0,
        le=900,
        alias="normalSubtitleLowerMargin",
    )
    normal_subtitle_alignment: int | None = Field(
        default=None,
        ge=1,
        le=9,
        alias="normalSubtitleAlignment",
    )
    normal_subtitle_x_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="normalSubtitleXPercent",
    )
    normal_subtitle_y_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="normalSubtitleYPercent",
    )
    normal_subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="normalSubtitlePrimaryColor",
    )
    normal_subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="normalSubtitleOutlineColor",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubtitleStylePreset(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    saved_at: datetime = Field(alias="savedAt")
    style: SubtitleStyleSnapshot

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


SubtitleStylePresetSlots = tuple[
    SubtitleStylePreset | None,
    SubtitleStylePreset | None,
    SubtitleStylePreset | None,
]


class SubtitleStylePresetDocument(BaseModel):
    version: Literal[1] = 1
    slots: SubtitleStylePresetSlots = Field(default_factory=lambda: (None, None, None))

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class YouTubePostingProfileDocument(BaseModel):
    version: Literal[1] = 1
    profile: YouTubePostingProfile = Field(default_factory=YouTubePostingProfile)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class JobSettings(BaseModel):
    workflow_mode: WorkflowMode = Field(default="automatic", alias="workflowMode")
    automation_mode: AutomationMode = Field(default="manual", alias="automationMode")
    manual_edit_finalized: bool = Field(default=False, alias="manualEditFinalized")
    manual_subtitle_mode: ManualSubtitleMode = Field(
        default="auto",
        alias="manualSubtitleMode",
    )
    mode: ClipMode = "high_quality"
    profile: ClipProfile = "auto"
    normal_clip_count: int = Field(default=2, ge=0, le=12, alias="normalClipCount")
    short_count: int = Field(default=3, ge=0, le=24, alias="shortCount")
    normal_min_duration: float = Field(default=90.0, gt=0, alias="normalMinDuration")
    normal_max_duration: float = Field(default=600.0, gt=0, alias="normalMaxDuration")
    short_min_duration: float = Field(default=20.0, gt=0, alias="shortMinDuration")
    short_max_duration: float = Field(default=75.0, gt=0, alias="shortMaxDuration")
    normal_clip_selection_preset: ClipSelectionPreset = Field(
        default="auto",
        alias="normalClipSelectionPreset",
    )
    short_clip_selection_preset: ClipSelectionPreset = Field(
        default="auto",
        alias="shortClipSelectionPreset",
    )
    normal_clip_guidance: str = Field(default="", max_length=1000, alias="normalClipGuidance")
    short_clip_guidance: str = Field(default="", max_length=1000, alias="shortClipGuidance")
    normal_clip_time_ranges: list[ClipTimeRange] = Field(
        default_factory=list,
        max_length=12,
        alias="normalClipTimeRanges",
    )
    short_clip_time_ranges: list[ClipTimeRange] = Field(
        default_factory=list,
        max_length=24,
        alias="shortClipTimeRanges",
    )
    exclude_intro_outro: bool = Field(default=True, alias="excludeIntroOutro")
    exclude_promotional_content: bool = Field(default=False, alias="excludePromotionalContent")
    max_candidates: int = Field(default=1200, gt=0, alias="maxCandidates")
    max_raw_candidates_per_type: int = Field(default=250_000, gt=0, alias="maxRawCandidatesPerType")
    max_kept_candidates_per_type: int = Field(default=1200, gt=0, alias="maxKeptCandidatesPerType")
    max_candidates_per_time_bucket: int = Field(default=100, gt=0, alias="maxCandidatesPerTimeBucket")
    candidate_time_bucket_seconds: float = Field(default=300.0, gt=0, alias="candidateTimeBucketSeconds")
    max_candidates_per_start_bucket: int = Field(default=5, gt=0, alias="maxCandidatesPerStartBucket")
    candidate_start_bucket_seconds: float = Field(default=15.0, gt=0, alias="candidateStartBucketSeconds")
    max_candidate_generation_memory_mb: int = Field(default=12_000, gt=0, alias="maxCandidateGenerationMemoryMb")
    candidate_chunk_seconds: float = Field(default=600.0, gt=0, alias="candidateChunkSeconds")
    candidate_chunk_overlap_seconds: float = Field(default=75.0, ge=0, alias="candidateChunkOverlapSeconds")
    burn_subtitles: bool = Field(default=True, alias="burnSubtitles")
    require_clip_plan_review: bool = Field(default=False, alias="requireClipPlanReview")
    require_subtitle_review: bool = Field(default=False, alias="requireSubtitleReview")
    max_chars_per_line_short: int = Field(default=16, ge=6, le=80, alias="maxCharsPerLineShort")
    max_chars_per_line_normal: int = Field(default=28, ge=8, le=100, alias="maxCharsPerLineNormal")
    max_lines: int = Field(default=2, ge=1, le=2, alias="maxLines")
    min_subtitle_duration: float = Field(default=1.1, gt=0, alias="minSubtitleDuration")
    max_subtitle_duration: float = Field(default=4.2, gt=0, alias="maxSubtitleDuration")
    min_gap_between_subtitles: float = Field(default=0.08, ge=0, alias="minGapBetweenSubtitles")
    subtitle_font_name: str | None = Field(default=None, min_length=1, alias="subtitleFontName")
    subtitle_title_font_name: str | None = Field(default=None, min_length=1, alias="subtitleTitleFontName")
    subtitle_font_size: int | None = Field(default=None, ge=12, le=220, alias="subtitleFontSize")
    subtitle_title_font_size: int | None = Field(default=None, ge=12, le=220, alias="subtitleTitleFontSize")
    subtitle_outline: int | None = Field(default=None, ge=0, le=20, alias="subtitleOutline")
    subtitle_shadow: int | None = Field(default=None, ge=0, le=20, alias="subtitleShadow")
    subtitle_margin_x: int | None = Field(default=None, ge=0, le=1200, alias="subtitleMarginX")
    subtitle_lower_margin: int | None = Field(default=None, ge=0, le=1600, alias="subtitleLowerMargin")
    subtitle_top_margin: int | None = Field(default=None, ge=0, le=1600, alias="subtitleTopMargin")
    subtitle_alignment: int | None = Field(default=None, ge=1, le=9, alias="subtitleAlignment")
    subtitle_title_alignment: int | None = Field(default=None, ge=1, le=9, alias="subtitleTitleAlignment")
    subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="subtitlePrimaryColor",
    )
    subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="subtitleOutlineColor",
    )
    short_subtitle_font_name: str | None = Field(default=None, min_length=1, alias="shortSubtitleFontName")
    short_subtitle_font_size: int | None = Field(default=None, ge=20, le=220, alias="shortSubtitleFontSize")
    short_title_font_size: int | None = Field(default=None, ge=20, le=220, alias="shortTitleFontSize")
    short_subtitle_outline: int | None = Field(default=None, ge=0, le=20, alias="shortSubtitleOutline")
    short_subtitle_shadow: int | None = Field(default=None, ge=0, le=20, alias="shortSubtitleShadow")
    short_subtitle_margin_x: int | None = Field(default=None, ge=0, le=800, alias="shortSubtitleMarginX")
    short_subtitle_lower_margin: int | None = Field(default=None, ge=0, le=1600, alias="shortSubtitleLowerMargin")
    short_title_top_margin: int | None = Field(default=None, ge=0, le=1600, alias="shortTitleTopMargin")
    short_subtitle_alignment: int | None = Field(default=None, ge=1, le=9, alias="shortSubtitleAlignment")
    short_title_alignment: int | None = Field(default=None, ge=1, le=9, alias="shortTitleAlignment")
    short_subtitle_x_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="shortSubtitleXPercent",
    )
    short_subtitle_y_percent: float | None = Field(
        default=68.75,
        ge=5,
        le=95,
        alias="shortSubtitleYPercent",
    )
    short_subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="shortSubtitlePrimaryColor",
    )
    short_subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="shortSubtitleOutlineColor",
    )
    normal_subtitle_font_name: str | None = Field(default=None, min_length=1, alias="normalSubtitleFontName")
    normal_subtitle_font_size: int | None = Field(default=None, ge=12, le=180, alias="normalSubtitleFontSize")
    normal_title_font_size: int | None = Field(default=None, ge=12, le=180, alias="normalTitleFontSize")
    normal_subtitle_outline: int | None = Field(default=None, ge=0, le=20, alias="normalSubtitleOutline")
    normal_subtitle_shadow: int | None = Field(default=None, ge=0, le=20, alias="normalSubtitleShadow")
    normal_subtitle_margin_x: int | None = Field(default=None, ge=0, le=1200, alias="normalSubtitleMarginX")
    normal_subtitle_lower_margin: int | None = Field(default=None, ge=0, le=900, alias="normalSubtitleLowerMargin")
    normal_title_top_margin: int | None = Field(default=None, ge=0, le=900, alias="normalTitleTopMargin")
    normal_subtitle_alignment: int | None = Field(default=None, ge=1, le=9, alias="normalSubtitleAlignment")
    normal_title_alignment: int | None = Field(default=None, ge=1, le=9, alias="normalTitleAlignment")
    normal_subtitle_x_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="normalSubtitleXPercent",
    )
    normal_subtitle_y_percent: float | None = Field(
        default=None,
        ge=5,
        le=95,
        alias="normalSubtitleYPercent",
    )
    normal_subtitle_primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="normalSubtitlePrimaryColor",
    )
    normal_subtitle_outline_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="normalSubtitleOutlineColor",
    )
    normalize_audio: bool = Field(default=False, alias="normalizeAudio")
    short_layout: ShortLayout = Field(default="auto", alias="shortLayout")
    short_overlay_title_mode: ShortOverlayTitleMode = Field(default="auto", alias="shortOverlayTitleMode")
    short_top_banner_enabled: bool = Field(default=True, alias="shortTopBannerEnabled")
    short_bottom_banner_enabled: bool = Field(default=True, alias="shortBottomBannerEnabled")
    enable_transcript_post_processing: bool = Field(default=True, alias="enableTranscriptPostProcessing")
    transcript_normalize_unicode: bool = Field(default=True, alias="transcriptNormalizeUnicode")
    transcript_normalize_whitespace: bool = Field(default=True, alias="transcriptNormalizeWhitespace")
    transcript_normalize_punctuation: bool = Field(default=True, alias="transcriptNormalizePunctuation")
    use_default_transcript_dictionary: bool = Field(default=True, alias="useDefaultTranscriptDictionary")
    transcript_replacements: dict[str, str] = Field(default_factory=dict, alias="transcriptReplacements")
    whisper_model_size: WhisperModelSize = Field(default="base", alias="whisperModelSize")
    transcription_language: TranscriptionLanguage = Field(default="ja", alias="transcriptionLanguage")
    transcription_device: TranscriptionDevice = Field(default="cpu", alias="transcriptionDevice")
    transcription_compute_type: TranscriptionComputeType = Field(default="auto", alias="transcriptionComputeType")
    subtitle_correction_mode: SubtitleCorrectionMode = Field(default="off", alias="subtitleCorrectionMode")
    subtitle_correction_scope: SubtitleCorrectionScope = Field(default="all", alias="subtitleCorrectionScope")
    transcript_correction_glossary: list[str] = Field(
        default_factory=list,
        max_length=200,
        alias="transcriptCorrectionGlossary",
    )
    subtitle_correction_suspicion_threshold: float = Field(
        default=0.40,
        ge=0,
        le=1,
        alias="subtitleCorrectionSuspicionThreshold",
    )
    subtitle_correction_model: str = Field(default="gpt-5.5", min_length=1, alias="subtitleCorrectionModel")
    subtitle_correction_reasoning_effort: SubtitleCorrectionReasoningEffort = Field(
        default="default",
        alias="subtitleCorrectionReasoningEffort",
    )
    subtitle_correction_min_confidence: float = Field(default=0.9, ge=0, le=1, alias="subtitleCorrectionMinConfidence")
    subtitle_correction_batch_size: int = Field(default=40, ge=1, le=100, alias="subtitleCorrectionBatchSize")
    subtitle_correction_context_segments: int = Field(default=2, ge=0, le=10, alias="subtitleCorrectionContextSegments")
    subtitle_correction_fallback_enabled: bool = Field(default=True, alias="subtitleCorrectionFallbackEnabled")
    selection_policy: SelectionPolicy = Field(default="fill_requested", alias="selectionPolicy")
    cross_type_overlap_dedupe: bool = Field(default=False, alias="crossTypeOverlapDedupe")
    heatmap_interval_mode: bool = Field(default=False, alias="heatmapIntervalMode")
    initial_selection_provider: InitialSelectionProvider = Field(
        default="legacy",
        alias="initialSelectionProvider",
    )
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
    youtube_source_title: str = Field(
        default="",
        max_length=300,
        alias="youtubeSourceTitle",
    )
    youtube_source_url: str = Field(
        default="",
        max_length=500,
        alias="youtubeSourceUrl",
    )
    youtube_posting_profile: YouTubePostingProfile = Field(
        default_factory=YouTubePostingProfile,
        alias="youtubePostingProfile",
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @field_validator("transcription_language", mode="before")
    @classmethod
    def normalize_legacy_transcription_language(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {"auto", "ja"}:
            return "ja"
        return value

    @field_validator("youtube_source_title", "youtube_source_url", mode="before")
    @classmethod
    def normalize_youtube_source_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("youtube_source_url")
    @classmethod
    def validate_youtube_source_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("youtubeSourceUrl must be an absolute HTTP(S) URL")
        return value

    @model_validator(mode="after")
    def validate_duration_ranges(self) -> "JobSettings":
        if self.workflow_mode == "manual":
            self.automation_mode = "manual"
        elif self.automation_mode in {"shadow", "guarded", "auto"} and not (
            self.burn_subtitles
            and self.require_clip_plan_review
            and self.require_subtitle_review
        ):
            raise ValueError(
                f"automationMode {self.automation_mode} requires subtitle burn-in and both review stops"
            )
        if self.workflow_mode != "manual" and self.normal_clip_count + self.short_count <= 0:
            raise ValueError("at least one normal clip or short must be requested")
        if self.normal_max_duration < self.normal_min_duration:
            raise ValueError("normalMaxDuration must be >= normalMinDuration")
        if self.short_max_duration < self.short_min_duration:
            raise ValueError("shortMaxDuration must be >= shortMinDuration")
        if self.max_subtitle_duration < self.min_subtitle_duration:
            raise ValueError("maxSubtitleDuration must be >= minSubtitleDuration")
        self._validate_clip_time_ranges(
            self.normal_clip_time_ranges,
            requested_count=self.normal_clip_count,
            field_name="normalClipTimeRanges",
        )
        self._validate_clip_time_ranges(
            self.short_clip_time_ranges,
            requested_count=self.short_count,
            field_name="shortClipTimeRanges",
        )
        has_automatic_output = (self.normal_clip_count > 0 and not self.normal_clip_time_ranges) or (
            self.short_count > 0 and not self.short_clip_time_ranges
        )
        has_manual_ranges = bool(
            self.normal_clip_time_ranges or self.short_clip_time_ranges
        )
        if self.workflow_mode == "manual" or not has_automatic_output or has_manual_ranges:
            self.initial_selection_provider = "legacy"
            self.use_openai_scoring = False
            self.ensure_selected_openai_scored = False
        if self.initial_selection_provider == "codex":
            self.use_openai_scoring = False
            self.ensure_selected_openai_scored = False
        if self.ensure_selected_openai_scored is None:
            self.ensure_selected_openai_scored = self.mode == "high_quality"
        if self.openai_finalist_scoring_limit is None:
            requested_count = self.normal_clip_count + self.short_count
            self.openai_finalist_scoring_limit = requested_count + 2 if requested_count > 0 else 0
        return self

    @staticmethod
    def _validate_clip_time_ranges(
        ranges: list[ClipTimeRange],
        *,
        requested_count: int,
        field_name: str,
    ) -> None:
        if not ranges:
            return
        if len(ranges) != requested_count:
            raise ValueError(f"{field_name} must contain exactly {requested_count} ranges")
        seen: set[tuple[float, float]] = set()
        for index, clip_range in enumerate(ranges, start=1):
            if clip_range.start_seconds is None or clip_range.end_seconds is None:
                raise ValueError(f"{field_name}[{index}] requires both startSeconds and endSeconds")
            if clip_range.end_seconds <= clip_range.start_seconds:
                raise ValueError(f"{field_name}[{index}] endSeconds must be greater than startSeconds")
            key = (clip_range.start_seconds, clip_range.end_seconds)
            if key in seen:
                raise ValueError(f"{field_name}[{index}] duplicates an earlier range")
            seen.add(key)


class JobCreateRequest(BaseModel):
    video_id: str = Field(alias="videoId")
    settings: JobSettings = Field(default_factory=JobSettings)


class JobCreateResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus


class SubtitleReviewSegmentUpdateRequest(BaseModel):
    text: str = Field(max_length=4000)


class SubtitleReviewClipContentUpdateRequest(BaseModel):
    title: str = Field(max_length=80)
    hook_text: str = Field(default="", max_length=120, alias="hookText")
    hook_duration_seconds: float = Field(
        default=3.0,
        ge=1,
        le=8,
        alias="hookDurationSeconds",
    )
    title_style: ClipTextStyle | None = Field(default=None, alias="titleStyle")
    hook_style: ClipTextStyle | None = Field(default=None, alias="hookStyle")
    subtitle_style: ClipTextStyle | None = Field(default=None, alias="subtitleStyle")

    model_config = ConfigDict(populate_by_name=True)


class SubtitleReviewClipFramingUpdateRequest(BaseModel):
    framing_offset_x: float = Field(ge=-100, le=100, alias="framingOffsetX")
    framing_offset_y: float = Field(ge=-100, le=100, alias="framingOffsetY")
    framing_zoom: float = Field(ge=1.0, le=1.6, alias="framingZoom")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubtitleReviewClipSegmentUpdate(BaseModel):
    segment_id: str = Field(min_length=1, alias="segmentId")
    text: str = Field(max_length=4000)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubtitleReviewClipApplyRequest(SubtitleReviewClipContentUpdateRequest):
    publication_title: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        alias="publicationTitle",
    )
    hook_scene_start: float | None = Field(default=None, ge=0, alias="hookSceneStart")
    hook_scene_end: float | None = Field(default=None, ge=0, alias="hookSceneEnd")
    title_candidates: list[YouTubeTitleCandidate] = Field(
        default_factory=list,
        max_length=3,
        alias="titleCandidates",
    )
    recommended_title_id: str | None = Field(default=None, alias="recommendedTitleId")
    selected_title_id: str | None = Field(default=None, alias="selectedTitleId")
    youtube_description: str = Field(default="", max_length=2000, alias="youtubeDescription")
    youtube_hashtags: list[str] = Field(default_factory=list, max_length=12, alias="youtubeHashtags")
    youtube_tags: list[str] = Field(default_factory=list, max_length=40, alias="youtubeTags")
    description_evidence_segment_ids: list[str] = Field(
        default_factory=list,
        max_length=64,
        alias="descriptionEvidenceSegmentIds",
    )
    post_metadata_source: PostMetadataSource | None = Field(default=None, alias="postMetadataSource")
    post_metadata_revision_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        alias="postMetadataRevisionHash",
    )
    segments: list[SubtitleReviewClipSegmentUpdate] = Field(
        default_factory=list,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_unique_segments(self) -> "SubtitleReviewClipApplyRequest":
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("duplicate subtitle segment update")
        title_candidate_ids = [candidate.id for candidate in self.title_candidates]
        if len(title_candidate_ids) != len(set(title_candidate_ids)):
            raise ValueError("duplicate YouTube title candidate id")
        if self.recommended_title_id and self.recommended_title_id not in title_candidate_ids:
            raise ValueError("recommended title id is not in title candidates")
        if self.selected_title_id and self.selected_title_id not in title_candidate_ids:
            raise ValueError("selected title id is not in title candidates")
        if len(self.youtube_hashtags) != len(set(self.youtube_hashtags)):
            raise ValueError("duplicate YouTube hashtag")
        if any(not hashtag.startswith("#") for hashtag in self.youtube_hashtags):
            raise ValueError("YouTube hashtags must start with #")
        if len(self.youtube_tags) != len({tag.casefold() for tag in self.youtube_tags}):
            raise ValueError("duplicate YouTube tag")
        if len(",".join(self.youtube_tags)) > 500:
            raise ValueError("YouTube tags must be 500 characters or fewer")
        if len(self.description_evidence_segment_ids) != len(
            set(self.description_evidence_segment_ids)
        ):
            raise ValueError("duplicate description evidence segment id")
        hook_fields = {"hook_scene_start", "hook_scene_end"}
        supplied_hook_fields = self.model_fields_set.intersection(hook_fields)
        if supplied_hook_fields and supplied_hook_fields != hook_fields:
            raise ValueError("hook scene requires both start and end")
        if supplied_hook_fields:
            if (self.hook_scene_start is None) != (self.hook_scene_end is None):
                raise ValueError("hook scene requires both start and end")
            if self.hook_scene_start is not None and self.hook_scene_end is not None:
                duration = self.hook_scene_end - self.hook_scene_start
                if not 0.5 <= duration <= 3:
                    raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        return self

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubtitleReviewConvertToShortRequest(BaseModel):
    start_seconds: float | None = Field(default=None, ge=0, alias="startSeconds")
    end_seconds: float | None = Field(default=None, ge=0, alias="endSeconds")

    @model_validator(mode="after")
    def validate_range(self) -> "SubtitleReviewConvertToShortRequest":
        if (self.start_seconds is None) != (self.end_seconds is None):
            raise ValueError("startSeconds and endSeconds must be provided together")
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds <= self.start_seconds
        ):
            raise ValueError("endSeconds must be greater than startSeconds")
        return self

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TitleHookSuggestionRequest(BaseModel):
    segments: list[SubtitleReviewClipSegmentUpdate] = Field(
        default_factory=list,
        max_length=1000,
    )
    force_regenerate: bool = Field(
        default=False,
        alias="forceRegenerate",
        strict=True,
    )

    @model_validator(mode="after")
    def validate_unique_segments(self) -> "TitleHookSuggestionRequest":
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("duplicate subtitle segment update")
        return self

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubtitleReviewSettingsUpdateRequest(BaseModel):
    short_layout: ShortLayout | None = Field(default=None, alias="shortLayout")
    short_top_banner_enabled: bool = Field(alias="shortTopBannerEnabled", strict=True)
    short_bottom_banner_enabled: bool = Field(alias="shortBottomBannerEnabled", strict=True)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ClipPlanReselectionRequest(BaseModel):
    normal_clip_selection_preset: ClipSelectionPreset = Field(alias="normalClipSelectionPreset")
    short_clip_selection_preset: ClipSelectionPreset = Field(alias="shortClipSelectionPreset")
    normal_clip_guidance: str = Field(max_length=1000, alias="normalClipGuidance")
    short_clip_guidance: str = Field(max_length=1000, alias="shortClipGuidance")
    exclude_intro_outro: bool = Field(alias="excludeIntroOutro")
    exclude_promotional_content: bool = Field(alias="excludePromotionalContent")
    selection_policy: SelectionPolicy = Field(alias="selectionPolicy")
    use_openai_scoring: bool = Field(alias="useOpenAIScoring")
    heatmap_interval_mode: bool | None = Field(
        default=None,
        alias="heatmapIntervalMode",
        strict=True,
    )

    model_config = ConfigDict(populate_by_name=True)


class ClipPlanBoundaryUpdateRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "ClipPlanBoundaryUpdateRequest":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if self.end - self.start < 1:
            raise ValueError("clip duration must be at least 1 second")
        return self


class ClipPlanTypeUpdateRequest(BaseModel):
    type: Literal["normal"]

    model_config = ConfigDict(extra="forbid")


class ManualClipCreateRequest(BaseModel):
    type: Literal["normal", "short"]
    title: str = Field(default="", max_length=120)
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "ManualClipCreateRequest":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if self.end - self.start < 1:
            raise ValueError("clip duration must be at least 1 second")
        return self


class ManualClipUpdateRequest(BaseModel):
    type: Literal["normal", "short"] | None = None
    title: str | None = Field(default=None, max_length=120)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self) -> "ManualClipUpdateRequest":
        if all(
            value is None
            for value in (self.type, self.title, self.start, self.end)
        ):
            raise ValueError("at least one manual clip field is required")
        if self.start is not None and self.end is not None:
            if self.end <= self.start:
                raise ValueError("end must be greater than start")
            if self.end - self.start < 1:
                raise ValueError("clip duration must be at least 1 second")
        return self


class ClipPlanHookSceneUpdateRequest(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "ClipPlanHookSceneUpdateRequest":
        if (self.start is None) != (self.end is None):
            raise ValueError("hook scene requires both start and end")
        if self.start is None or self.end is None:
            return self
        if self.end <= self.start:
            raise ValueError("hook scene end must be greater than start")
        if not 0.5 <= self.end - self.start <= 3:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        return self


class ClipPlanActionResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus


class SubtitleReviewFinalizeResponse(BaseModel):
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
    title_candidates: list[YouTubeTitleCandidate] = Field(
        default_factory=list,
        alias="titleCandidates",
    )
    recommended_title_id: str | None = Field(default=None, alias="recommendedTitleId")
    selected_title_id: str | None = Field(default=None, alias="selectedTitleId")
    youtube_description: str = Field(default="", alias="youtubeDescription")
    youtube_hashtags: list[str] = Field(default_factory=list, alias="youtubeHashtags")
    youtube_tags: list[str] = Field(default_factory=list, alias="youtubeTags")
    description_evidence_segment_ids: list[str] = Field(
        default_factory=list,
        alias="descriptionEvidenceSegmentIds",
    )
    post_metadata_source: PostMetadataSource | None = Field(default=None, alias="postMetadataSource")
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
    can_reopen_for_editing: bool = Field(alias="canReopenForEditing")
    audit_summary: JobAuditSummary | None = Field(default=None, alias="auditSummary")
    normal_clips: list[ResultExportItem] = Field(alias="normalClips")
    shorts: list[ResultExportItem]


class StorageStatusResponse(BaseModel):
    storage_bytes: int = Field(alias="storageBytes")
    storage_limit_bytes: int = Field(alias="storageLimitBytes")
    disk_free_bytes: int = Field(alias="diskFreeBytes")
    disk_total_bytes: int = Field(alias="diskTotalBytes")
    disk_free_percent: float = Field(alias="diskFreePercent")
    warning: bool
    reasons: list[str]
    cleanup_eligible_jobs: int = Field(alias="cleanupEligibleJobs")
    cleanup_eligible_videos: int = Field(alias="cleanupEligibleVideos")


class StorageCleanupResponse(BaseModel):
    removed_jobs: int = Field(alias="removedJobs")
    removed_videos: int = Field(alias="removedVideos")
    removed_files: int = Field(alias="removedFiles")
    reclaimed_bytes: int = Field(alias="reclaimedBytes")
    errors: list[str]
