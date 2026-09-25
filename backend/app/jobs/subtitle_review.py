import json
import math
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle, SubtitleStyleOverride, TextFontPreset
from app.candidates.select_candidates import CandidateSelection
from app.overlay_text import normalize_overlay_text
from app.posting_metadata import (
    NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
    PostMetadataSource,
    YouTubeTitleCandidate,
    ensure_publication_title_suffix,
    strip_normal_publication_title_suffix,
)
from app.render.subtitles_ass import (
    DEFAULT_NORMAL_HEIGHT,
    DEFAULT_NORMAL_WIDTH,
    ResolvedTextStyle,
    SubtitleLayout,
    SubtitleRenderSettings,
    resolve_clip_text_style,
    split_subtitle_text,
)
from app.render.title_policy import short_overlay_title_expected
from app.schemas import ShortLayout, ShortOverlayTitleMode


SUBTITLE_REVIEW_FILENAME = "subtitle_review.json"
SUBTITLE_REVIEW_SUMMARY_FILENAME = "subtitle_review_summary.json"
REVIEWED_TRANSCRIPT_FILENAME = "reviewed_transcript_segments.json"
SUBTITLE_REVIEW_PREVIEW_DIRNAME = "subtitle_review_previews"
_STYLE_UNSET = object()

SubtitleReviewState = Literal["awaiting_review", "render_queued", "rendering", "completed"]
SubtitleReviewPreviewState = Literal["queued", "rendering", "ready", "failed"]


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class SubtitleReviewSegment(BaseModel):
    id: str
    index: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    original_text: str = Field(alias="originalText")
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    edited: bool = False
    affected_clip_ids: list[str] = Field(default_factory=list, alias="affectedClipIds")
    source_indices: list[int] = Field(default_factory=list, alias="sourceIndices")
    preserve_segmentation: bool = Field(default=False, alias="preserveSegmentation")
    single_line: bool = Field(default=False, alias="singleLine")

    model_config = ConfigDict(populate_by_name=True)


class ResolvedClipTextStyle(BaseModel):
    font_preset: TextFontPreset | None = Field(alias="fontPreset")
    font_name: str = Field(alias="fontName")
    font_size: int = Field(ge=1, alias="fontSize")
    primary_color: str = Field(
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="primaryColor",
    )
    outline_color: str = Field(
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="outlineColor",
    )
    outline_width: int = Field(ge=0, alias="outlineWidth")
    outer_outline_color: str = Field(default="#FFFFFF", alias="outerOutlineColor")
    outer_outline_width: int = Field(default=0, ge=0, alias="outerOutlineWidth")
    shadow: int = Field(ge=0)
    bold: bool
    alignment: int = Field(ge=1, le=9)
    margin_x: int = Field(ge=0, alias="marginX")
    margin_v: int = Field(ge=0, alias="marginV")
    x_percent: float = Field(alias="xPercent")
    y_percent: float = Field(alias="yPercent")
    position_mode: Literal["explicit", "layout"] = Field(alias="positionMode")
    position_override: bool = Field(alias="positionOverride")

    model_config = ConfigDict(populate_by_name=True)


class PreviewFraming(BaseModel):
    framing_offset_x: float = Field(ge=-100, le=100)
    framing_offset_y: float = Field(ge=-100, le=100)
    framing_zoom: float = Field(ge=1, le=3)
    short_layout: ShortLayout | None = None


class SubtitleReviewClip(BaseModel):
    preview_framing: PreviewFraming | None = Field(default=None, alias="previewFraming")
    normal_title_suffix: str = Field(default=NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX, max_length=80, alias="normalTitleSuffix")
    id: str
    type: Literal["normal", "short"]
    title: str
    publication_title: str | None = Field(
        default=None,
        max_length=100,
        alias="publicationTitle",
    )
    original_title: str | None = Field(default=None, alias="originalTitle")
    title_edited: bool = Field(default=False, alias="titleEdited")
    hook_text: str = Field(default="", alias="hookText")
    hook_duration_seconds: float = Field(default=3.0, ge=1, le=8, alias="hookDurationSeconds")
    hook_scene_start: float | None = Field(default=None, ge=0, alias="hookSceneStart")
    hook_scene_end: float | None = Field(default=None, ge=0, alias="hookSceneEnd")
    thumbnail_kicker: str = Field(default="", max_length=40, alias="thumbnailKicker")
    thumbnail_line1: str = Field(default="", max_length=60, alias="thumbnailLine1")
    thumbnail_line2: str = Field(default="", max_length=60, alias="thumbnailLine2")
    thumbnail_frame_seconds: float | None = Field(
        default=None,
        ge=0,
        alias="thumbnailFrameSeconds",
    )
    title_candidates: list[YouTubeTitleCandidate] = Field(
        default_factory=list,
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
    title_style: ClipTextStyle | None = Field(default=None, alias="titleStyle")
    hook_style: ClipTextStyle | None = Field(default=None, alias="hookStyle")
    subtitle_style: ClipTextStyle | None = Field(default=None, alias="subtitleStyle")
    subtitle_styles: list[SubtitleStyleOverride] = Field(default_factory=list, alias="subtitleStyles")
    framing_offset_x: float = Field(default=0.0, ge=-100, le=100, alias="framingOffsetX")
    framing_offset_y: float = Field(default=0.0, ge=-100, le=100, alias="framingOffsetY")
    framing_zoom: float = Field(default=1.0, ge=1.0, le=3.0, alias="framingZoom")
    short_layout: ShortLayout | None = Field(default=None, alias="shortLayout")
    resolved_title_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedTitleStyle",
    )
    resolved_hook_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedHookStyle",
    )
    resolved_subtitle_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedSubtitleStyle",
    )
    resolved_default_title_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedDefaultTitleStyle",
    )
    resolved_default_hook_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedDefaultHookStyle",
    )
    resolved_default_subtitle_style: ResolvedClipTextStyle | None = Field(
        default=None,
        alias="resolvedDefaultSubtitleStyle",
    )
    subtitle_max_chars_per_line: int | None = Field(
        default=None,
        ge=1,
        alias="subtitleMaxCharsPerLine",
    )
    subtitle_max_lines: int | None = Field(
        default=None,
        ge=1,
        alias="subtitleMaxLines",
    )
    subtitle_min_duration_seconds: float | None = Field(
        default=None,
        ge=0,
        alias="subtitleMinDurationSeconds",
    )
    subtitle_max_duration_seconds: float | None = Field(
        default=None,
        gt=0,
        alias="subtitleMaxDurationSeconds",
    )
    subtitle_min_gap_seconds: float | None = Field(
        default=None,
        ge=0,
        alias="subtitleMinGapSeconds",
    )
    preview_width: int | None = Field(default=None, ge=1, alias="previewWidth")
    preview_height: int | None = Field(default=None, ge=1, alias="previewHeight")
    overlay_title_expected: bool = Field(default=False, alias="overlayTitleExpected")
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    preview_video_url: str | None = Field(default=None, alias="previewVideoUrl")
    preview_state: SubtitleReviewPreviewState = Field(default="queued", alias="previewState")
    preview_spec_hash: str | None = Field(default=None, alias="previewSpecHash")
    preview_error: str | None = Field(default=None, alias="previewError")
    live_preview_video_url: str | None = Field(
        default=None,
        alias="livePreviewVideoUrl",
    )
    live_preview_spec_hash: str | None = Field(
        default=None,
        alias="livePreviewSpecHash",
    )
    segment_ids: list[str] = Field(default_factory=list, alias="segmentIds")
    confirmed: bool = False
    edited_segment_count: int = Field(default=0, ge=0, alias="editedSegmentCount")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_hook_scene(self) -> "SubtitleReviewClip":
        if self.type == "normal":
            self.publication_title = ensure_publication_title_suffix(
                self.publication_title or self.title,
                clip_type=self.type,
                suffix=self.normal_title_suffix,
            )
            self.title_candidates = [
                candidate.model_copy(
                    update={
                        "title": ensure_publication_title_suffix(
                            candidate.title,
                            clip_type=self.type,
                            suffix=self.normal_title_suffix,
                        )
                    }
                )
                for candidate in self.title_candidates
            ]
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
        if (
            self.thumbnail_frame_seconds is not None
            and self.thumbnail_frame_seconds > self.duration + 0.001
        ):
            raise ValueError("thumbnail frame must stay within the selected clip")
        hook_start = self.hook_scene_start
        hook_end = self.hook_scene_end
        if (hook_start is None) != (hook_end is None):
            raise ValueError("hook scene requires both start and end")
        if hook_start is None or hook_end is None:
            return self
        if not 0.5 <= hook_end - hook_start <= 3.0:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        if hook_start < self.start - 0.001 or hook_end > self.end + 0.001:
            raise ValueError("hook scene must stay within the selected clip")
        return self


class SubtitleReviewDocument(BaseModel):
    version: int = 1
    job_id: str = Field(alias="jobId")
    state: SubtitleReviewState = "awaiting_review"
    render_revision: int = Field(default=1, ge=1, alias="renderRevision")
    reopened_at: str | None = Field(default=None, alias="reopenedAt")
    reedit_source_job_id: str | None = Field(default=None, alias="reeditSourceJobId")
    reedit_source_clip_id: str | None = Field(default=None, alias="reeditSourceClipId")
    source_video_url: str = Field(alias="sourceVideoUrl")
    render_mode: str = Field(default="high_quality", alias="renderMode")
    short_max_duration: float = Field(default=75.0, gt=0, alias="shortMaxDuration")
    short_overlay_title_mode: ShortOverlayTitleMode = Field(
        default="auto",
        alias="shortOverlayTitleMode",
    )
    short_layout: ShortLayout = Field(default="auto", alias="shortLayout")
    short_top_banner_enabled: bool = Field(default=False, alias="shortTopBannerEnabled")
    short_bottom_banner_enabled: bool = Field(default=False, alias="shortBottomBannerEnabled")
    clips: list[SubtitleReviewClip] = Field(default_factory=list)
    segments: list[SubtitleReviewSegment] = Field(default_factory=list)
    confirmed_clip_count: int = Field(default=0, ge=0, alias="confirmedClipCount")
    total_clip_count: int = Field(default=0, ge=0, alias="totalClipCount")
    edited_segment_count: int = Field(default=0, ge=0, alias="editedSegmentCount")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


def subtitle_review_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / SUBTITLE_REVIEW_FILENAME


def subtitle_review_summary_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / SUBTITLE_REVIEW_SUMMARY_FILENAME


def reviewed_transcript_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / REVIEWED_TRANSCRIPT_FILENAME


def subtitle_review_source_path(output_dir: str | Path, document: SubtitleReviewDocument) -> Path:
    # Keep the original index space when a render replaces transcript_segments.json.
    digest = sha256(document.created_at.encode("utf-8")).hexdigest()[:16]
    return Path(output_dir) / f"subtitle_review_source_{digest}.json"


def subtitle_review_preview_path(output_dir: str | Path, clip_id: str) -> Path:
    digest = sha256(clip_id.encode("utf-8")).hexdigest()[:16]
    return Path(output_dir) / SUBTITLE_REVIEW_PREVIEW_DIRNAME / f"{digest}.mp4"


def subtitle_review_preview_url(job_id: str, clip_id: str) -> str:
    return f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/preview-video"


def _candidate_title(candidate: Candidate, index: int) -> str:
    prefix = "通常切り抜き" if candidate.type == "normal" else "ショート"
    return (candidate.overlay_title or candidate.title or f"{prefix} {index:02d}").strip()


def _candidate_publication_title(candidate: Candidate, suffix: str = NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX) -> str | None:
    title = (candidate.title or "").strip()
    if not title:
        return None
    return ensure_publication_title_suffix(title, clip_type=candidate.type, suffix=suffix)


def _segment_id(index: int) -> str:
    return f"segment_{index:05d}"


def _review_segments_for_source(
    index: int,
    segment: TranscriptSegment,
    affected_clip_ids: list[str],
    layouts: dict[str, SubtitleLayout],
) -> list[SubtitleReviewSegment]:
    base = {
        "index": index,
        "confidence": segment.confidence,
        "affectedClipIds": affected_clip_ids,
    }
    if segment.preserve_segmentation or segment.single_line or not segment.text.strip():
        return [
            SubtitleReviewSegment(
                id=_segment_id(index),
                start=segment.start,
                end=segment.end,
                originalText=segment.text,
                text=segment.text,
                preserveSegmentation=segment.preserve_segmentation,
                singleLine=segment.single_line,
                **base,
            )
        ]

    active_layouts = [layouts[clip_id] for clip_id in affected_clip_ids]
    max_chars = min(layout.max_chars_per_line * layout.max_lines for layout in active_layouts)
    max_duration = min(layout.max_subtitle_duration for layout in active_layouts)
    min_duration = max(layout.min_subtitle_duration for layout in active_layouts)
    duration = max(0.01, segment.end - segment.start)
    # Rendering already wraps ordinary subtitle segments.  Splitting every
    # segment at the render limit would turn normal ASR output into many tiny
    # review rows and needlessly rewrite its timing.  Normalize only clear ASR
    # outliers (for example the 20-30 second text walls seen in the clip view).
    if len(segment.text.strip()) <= max_chars * 2:
        return [
            SubtitleReviewSegment(
                id=_segment_id(index),
                start=segment.start,
                end=segment.end,
                originalText=segment.text,
                text=segment.text,
                preserveSegmentation=False,
                singleLine=False,
                **base,
            )
        ]
    chunks = split_subtitle_text(segment.text, max_chars)
    minimum_count = max(1, math.ceil(duration / max_duration))
    if len(chunks) < minimum_count and len(segment.text.strip()) >= minimum_count * 4:
        chunks = split_subtitle_text(segment.text, max(4, math.ceil(len(segment.text.strip()) / minimum_count)))
    maximum_count = max(1, int(duration // min_duration))
    if len(chunks) > maximum_count:
        chunks = split_subtitle_text(segment.text, max(max_chars, math.ceil(len(segment.text.strip()) / maximum_count)))
    if len(chunks) <= 1:
        return [
            SubtitleReviewSegment(
                id=_segment_id(index),
                start=segment.start,
                end=segment.end,
                originalText=segment.text,
                text=segment.text,
                preserveSegmentation=False,
                singleLine=False,
                **base,
            )
        ]

    total_weight = sum(max(1, len(chunk)) for chunk in chunks)
    cursor = segment.start
    review_segments: list[SubtitleReviewSegment] = []
    for part, chunk in enumerate(chunks):
        end = segment.end if part == len(chunks) - 1 else min(
            segment.end,
            cursor + duration * max(1, len(chunk)) / total_weight,
        )
        review_segments.append(
            SubtitleReviewSegment(
                id=f"{_segment_id(index)}_part_{part + 1}",
                start=round(cursor, 3),
                end=round(end, 3),
                originalText=chunk,
                text=chunk,
                sourceIndices=[index],
                preserveSegmentation=True,
                singleLine=False,
                **base,
            )
        )
        cursor = end
    return review_segments


def _overlaps(segment: TranscriptSegment, candidate: Candidate) -> bool:
    if segment.clip_id is not None and segment.clip_id != candidate.id:
        return False
    return segment.end > candidate.start and segment.start < candidate.end


def build_manual_subtitle_segments(
    selection: CandidateSelection,
) -> list[TranscriptSegment]:
    """Create one independent editable segment for every manually selected clip."""
    return [
        TranscriptSegment(
            start=candidate.start,
            end=candidate.end,
            text="",
            confidence=1.0,
            clipId=candidate.id,
        )
        for candidate in [*selection.normal_clips, *selection.shorts]
    ]


def _refresh_counts(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    edited_by_id = {segment.id: segment.edited for segment in document.segments}
    for clip in document.clips:
        clip.edited_segment_count = sum(1 for segment_id in clip.segment_ids if edited_by_id.get(segment_id, False))
    document.confirmed_clip_count = sum(1 for clip in document.clips if clip.confirmed)
    document.total_clip_count = len(document.clips)
    document.edited_segment_count = sum(1 for segment in document.segments if segment.edited)
    document.updated_at = _utc_iso()
    return document


def refresh_review_overlay_title_expectations(
    document: SubtitleReviewDocument,
    *,
    render_mode: str | None,
) -> SubtitleReviewDocument:
    for clip in document.clips:
        clip.overlay_title_expected = bool(
            clip.title
            and (
                clip.type == "normal"
                or (
                    clip.type == "short"
                    and short_overlay_title_expected(
                        render_mode=render_mode,
                        stored_mode=document.short_overlay_title_mode,
                        top_banner_enabled=document.short_top_banner_enabled,
                        title_manually_reviewed=clip.title_edited,
                    )
                )
            )
        )
    return document


def _resolved_style_model(style: ResolvedTextStyle) -> ResolvedClipTextStyle:
    return ResolvedClipTextStyle(
        fontPreset=style.font_preset,
        fontName=style.font_name,
        fontSize=style.font_size,
        primaryColor=style.primary_color,
        outlineColor=style.outline_color,
        outlineWidth=style.outline_width,
        outerOutlineWidth=style.outer_outline_width,
        outerOutlineColor=style.outer_outline_color,
        shadow=style.shadow,
        bold=style.bold,
        alignment=style.alignment,
        marginX=style.margin_x,
        marginV=style.margin_v,
        xPercent=style.x_percent,
        yPercent=style.y_percent,
        positionMode=style.position_mode,
        positionOverride=style.position_override,
    )


def refresh_review_render_contract(
    document: SubtitleReviewDocument,
    *,
    render_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    render_mode: str | None = None,
) -> tuple[SubtitleReviewDocument, bool]:
    normalized_render_mode = str(render_mode or "high_quality")
    changed = (
        "render_mode" not in document.model_fields_set
        or document.render_mode != normalized_render_mode
    )
    document.render_mode = normalized_render_mode

    for clip in document.clips:
        layout = (
            SubtitleLayout.short(render_settings)
            if clip.type == "short"
            else SubtitleLayout.normal(
                width=source_width or DEFAULT_NORMAL_WIDTH,
                height=source_height or DEFAULT_NORMAL_HEIGHT,
                settings=render_settings,
            )
        )
        resolved_subtitle_style = _resolved_style_model(
            resolve_clip_text_style(
                clip.subtitle_style,
                layout,
                role="subtitle",
            )
        )
        resolved_default_subtitle_style = _resolved_style_model(
            resolve_clip_text_style(None, layout, role="subtitle")
        )
        resolved_title_style = _resolved_style_model(
            resolve_clip_text_style(
                clip.title_style,
                layout,
                role="title",
            )
        )
        resolved_hook_style = _resolved_style_model(
            resolve_clip_text_style(
                clip.hook_style,
                layout,
                role="hook",
            )
        )
        resolved_default_title_style = _resolved_style_model(
            resolve_clip_text_style(None, layout, role="title")
        )
        resolved_default_hook_style = _resolved_style_model(
            resolve_clip_text_style(None, layout, role="hook")
        )
        next_values = {
            "resolved_title_style": resolved_title_style,
            "resolved_hook_style": resolved_hook_style,
            "resolved_subtitle_style": resolved_subtitle_style,
            "resolved_default_title_style": resolved_default_title_style,
            "resolved_default_hook_style": resolved_default_hook_style,
            "resolved_default_subtitle_style": resolved_default_subtitle_style,
            "subtitle_max_chars_per_line": layout.max_chars_per_line,
            "subtitle_max_lines": layout.max_lines,
            "subtitle_min_duration_seconds": layout.min_subtitle_duration,
            "subtitle_max_duration_seconds": layout.max_subtitle_duration,
            "subtitle_min_gap_seconds": layout.min_gap_between_subtitles,
            "preview_width": layout.width,
            "preview_height": layout.height,
        }
        for field_name, value in next_values.items():
            if (
                field_name not in clip.model_fields_set
                or getattr(clip, field_name) != value
            ):
                changed = True
            setattr(clip, field_name, value)

    expected_before = [clip.overlay_title_expected for clip in document.clips]
    refresh_review_overlay_title_expectations(
        document,
        render_mode=normalized_render_mode,
    )
    if expected_before != [clip.overlay_title_expected for clip in document.clips]:
        changed = True
    return document, changed


def build_subtitle_review(
    job_id: str,
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    *,
    short_max_duration: float = 75.0,
    render_mode: str | None = "high_quality",
    short_overlay_title_mode: ShortOverlayTitleMode = "auto",
    short_layout: ShortLayout = "auto",
    short_top_banner_enabled: bool = False,
    short_bottom_banner_enabled: bool = False,
    render_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
) -> SubtitleReviewDocument:
    selected_candidates = [*selection.normal_clips, *selection.shorts]
    affected_clips: dict[int, list[str]] = {}
    type_indices: dict[str, int] = {"normal": 0, "short": 0}

    for candidate in selected_candidates:
        indices = [
            index
            for index, segment in enumerate(transcript_segments)
            if _overlaps(segment, candidate)
        ]
        for index in indices:
            affected_clips.setdefault(index, []).append(candidate.id)

    layouts = {
        candidate.id: (
            SubtitleLayout.short(render_settings)
            if candidate.type == "short"
            else SubtitleLayout.normal(
                width=source_width or DEFAULT_NORMAL_WIDTH,
                height=source_height or DEFAULT_NORMAL_HEIGHT,
                settings=render_settings,
            )
        )
        for candidate in selected_candidates
    }
    segments = [
        review_segment
        for index, segment in enumerate(transcript_segments)
        if index in affected_clips
        for review_segment in _review_segments_for_source(
            index,
            segment,
            affected_clips[index],
            layouts,
        )
    ]

    normal_title_suffix = (render_settings or {}).get("normalTitleSuffix")
    if normal_title_suffix is None:
        normal_title_suffix = NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX
    clips: list[SubtitleReviewClip] = []
    for candidate in selected_candidates:
        type_indices[candidate.type] += 1
        clips.append(
            SubtitleReviewClip(
                id=candidate.id,
                type=candidate.type,
                title=_candidate_title(candidate, type_indices[candidate.type]),
                publicationTitle=_candidate_publication_title(candidate, normal_title_suffix),
                normalTitleSuffix=normal_title_suffix,
                originalTitle=_candidate_title(candidate, type_indices[candidate.type]),
                hookText=candidate.hook_text or "",
                hookDurationSeconds=candidate.hook_duration_seconds or 3.0,
                hookSceneStart=candidate.hook_scene_start,
                hookSceneEnd=candidate.hook_scene_end,
                thumbnailKicker=getattr(candidate, "thumbnail_kicker", ""),
                thumbnailLine1=getattr(candidate, "thumbnail_line1", ""),
                thumbnailLine2=getattr(candidate, "thumbnail_line2", ""),
                thumbnailFrameSeconds=getattr(candidate, "thumbnail_frame_seconds", None),
                titleCandidates=candidate.title_candidates,
                recommendedTitleId=candidate.recommended_title_id,
                selectedTitleId=candidate.selected_title_id,
                youtubeDescription=candidate.youtube_description or "",
                youtubeHashtags=candidate.youtube_hashtags,
                youtubeTags=candidate.youtube_tags,
                descriptionEvidenceSegmentIds=candidate.description_evidence_segment_ids,
                postMetadataSource=candidate.post_metadata_source,
                postMetadataRevisionHash=candidate.post_metadata_revision_hash,
                titleStyle=candidate.title_style,
                hookStyle=candidate.hook_style,
                subtitleStyle=candidate.subtitle_style,
                subtitleStyles=candidate.subtitle_styles,
                framingOffsetX=candidate.framing_offset_x,
                framingOffsetY=candidate.framing_offset_y,
                framingZoom=candidate.framing_zoom,
                shortLayout=candidate.short_layout,
                start=candidate.start,
                end=candidate.end,
                duration=candidate.duration,
                segmentIds=[
                    segment.id
                    for segment in segments
                    if candidate.id in segment.affected_clip_ids
                ],
            )
        )
    now = _utc_iso()
    document = _refresh_counts(
        SubtitleReviewDocument(
            jobId=job_id,
            sourceVideoUrl=f"/api/jobs/{job_id}/source-video",
            renderMode=str(render_mode or "high_quality"),
            shortMaxDuration=short_max_duration,
            shortOverlayTitleMode=short_overlay_title_mode,
            shortLayout=short_layout,
            shortTopBannerEnabled=short_top_banner_enabled,
            shortBottomBannerEnabled=short_bottom_banner_enabled,
            clips=clips,
            segments=segments,
            createdAt=now,
            updatedAt=now,
        )
    )
    document, _changed = refresh_review_render_contract(
        document,
        render_mode=render_mode,
        render_settings=render_settings,
        source_width=source_width,
        source_height=source_height,
    )
    return document


def write_subtitle_review(document: SubtitleReviewDocument, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(document.model_dump(by_alias=True, mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def load_subtitle_review(path: str | Path) -> SubtitleReviewDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return SubtitleReviewDocument.model_validate(payload)


def update_review_segment(
    document: SubtitleReviewDocument,
    segment_id: str,
    text: str,
) -> SubtitleReviewDocument:
    segment = next((item for item in document.segments if item.id == segment_id), None)
    if segment is None:
        raise KeyError(segment_id)
    if segment.text == text:
        return _refresh_counts(document)

    segment.text = text
    segment.edited = text != segment.original_text
    affected = set(segment.affected_clip_ids)
    for clip in document.clips:
        if clip.id in affected:
            clip.confirmed = False
    return _refresh_counts(document)


def update_review_render_settings(
    document: SubtitleReviewDocument,
    *,
    render_mode: str | None,
    short_overlay_title_mode: ShortOverlayTitleMode,
    short_layout: ShortLayout,
    short_top_banner_enabled: bool,
    short_bottom_banner_enabled: bool,
    render_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
) -> SubtitleReviewDocument:
    document.short_overlay_title_mode = short_overlay_title_mode
    document.short_layout = short_layout
    document.short_top_banner_enabled = short_top_banner_enabled
    document.short_bottom_banner_enabled = short_bottom_banner_enabled
    document, _changed = refresh_review_render_contract(
        document,
        render_mode=render_mode,
        render_settings=render_settings,
        source_width=source_width,
        source_height=source_height,
    )
    return _refresh_counts(document)


def update_review_clip_content(
    document: SubtitleReviewDocument,
    clip_id: str,
    *,
    title: str,
    publication_title: str | None | object = _STYLE_UNSET,
    hook_text: str = "",
    hook_duration_seconds: float = 3.0,
    title_style: ClipTextStyle | None | object = _STYLE_UNSET,
    hook_style: ClipTextStyle | None | object = _STYLE_UNSET,
    subtitle_style: ClipTextStyle | None | object = _STYLE_UNSET,
    subtitle_styles: list[SubtitleStyleOverride] | object = _STYLE_UNSET,
    title_candidates: Sequence[YouTubeTitleCandidate] | object = _STYLE_UNSET,
    recommended_title_id: str | None | object = _STYLE_UNSET,
    selected_title_id: str | None | object = _STYLE_UNSET,
    youtube_description: str | object = _STYLE_UNSET,
    youtube_hashtags: Sequence[str] | object = _STYLE_UNSET,
    youtube_tags: Sequence[str] | object = _STYLE_UNSET,
    description_evidence_segment_ids: Sequence[str] | object = _STYLE_UNSET,
    post_metadata_source: PostMetadataSource | None | object = _STYLE_UNSET,
    post_metadata_revision_hash: str | None | object = _STYLE_UNSET,
    thumbnail_kicker: str | object = _STYLE_UNSET,
    thumbnail_line1: str | object = _STYLE_UNSET,
    thumbnail_line2: str | object = _STYLE_UNSET,
    thumbnail_frame_seconds: float | None | object = _STYLE_UNSET,
) -> SubtitleReviewDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)

    normalized_title = normalize_overlay_text(title)
    normalized_hook = normalize_overlay_text(hook_text)
    if len(normalized_title) > 80:
        raise ValueError("title must be 80 characters or fewer")
    next_publication_title = clip.publication_title
    if publication_title is _STYLE_UNSET:
        current_derived_title = ensure_publication_title_suffix(
            clip.title,
            clip_type=clip.type,
            suffix=clip.normal_title_suffix,
        )
        if (
            clip.publication_title is None
            or clip.publication_title == clip.title
            or clip.publication_title == current_derived_title
        ):
            next_publication_title = (
                " ".join(normalized_title.split())
                if normalized_title
                else clip.publication_title
            )
    else:
        next_publication_title = (
            " ".join(publication_title.split()).strip()
            if isinstance(publication_title, str)
            else None
        )
        if next_publication_title and len(next_publication_title) > 100:
            raise ValueError("publication title must be 100 characters or fewer")
    if not next_publication_title:
        next_publication_title = " ".join(normalized_title.split()) or None
    if not next_publication_title:
        raise ValueError("publication title must not be empty")
    if clip.type == "normal":
        next_publication_title = ensure_publication_title_suffix(
            next_publication_title,
            clip_type=clip.type,
            suffix=clip.normal_title_suffix,
        )
    elif next_publication_title:
        next_publication_title = ensure_publication_title_suffix(
            next_publication_title,
            clip_type=clip.type,
            suffix=clip.normal_title_suffix,
        )
    if len(normalized_hook) > 120:
        raise ValueError("hook text must be 120 characters or fewer")
    if not 1 <= hook_duration_seconds <= 8:
        raise ValueError("hook duration must be between 1 and 8 seconds")
    next_title_style = clip.title_style if title_style is _STYLE_UNSET else title_style
    next_hook_style = clip.hook_style if hook_style is _STYLE_UNSET else hook_style
    next_subtitle_style = (
        clip.subtitle_style if subtitle_style is _STYLE_UNSET else subtitle_style
    )
    next_subtitle_styles = (
        clip.subtitle_styles if subtitle_styles is _STYLE_UNSET else list(subtitle_styles)
    )
    valid_ranges = {
        (segment.start, segment.end)
        for segment in document.segments if segment.id in clip.segment_ids
    }
    override_ranges = [(item.start, item.end) for item in next_subtitle_styles]
    if len(set(override_ranges)) != len(override_ranges) or any(
        pair not in valid_ranges for pair in override_ranges
    ):
        raise ValueError("subtitle style must target a unique segment in this clip")
    next_title_candidates = (
        clip.title_candidates
        if title_candidates is _STYLE_UNSET
        else [YouTubeTitleCandidate.model_validate(item) for item in title_candidates]
    )
    next_title_candidates = [
        candidate.model_copy(
            update={
                "title": ensure_publication_title_suffix(
                    candidate.title,
                    clip_type=clip.type,
                    suffix=clip.normal_title_suffix,
                )
            }
        )
        for candidate in next_title_candidates
    ]
    next_recommended_title_id = (
        clip.recommended_title_id
        if recommended_title_id is _STYLE_UNSET
        else recommended_title_id
    )
    next_selected_title_id = (
        clip.selected_title_id if selected_title_id is _STYLE_UNSET else selected_title_id
    )
    next_youtube_description = (
        clip.youtube_description
        if youtube_description is _STYLE_UNSET
        else str(youtube_description).strip()
    )
    next_youtube_hashtags = (
        clip.youtube_hashtags
        if youtube_hashtags is _STYLE_UNSET
        else [str(hashtag).strip() for hashtag in youtube_hashtags if str(hashtag).strip()]
    )
    next_youtube_tags = (
        clip.youtube_tags
        if youtube_tags is _STYLE_UNSET
        else [str(tag).strip() for tag in youtube_tags if str(tag).strip()]
    )
    next_description_evidence_segment_ids = (
        clip.description_evidence_segment_ids
        if description_evidence_segment_ids is _STYLE_UNSET
        else [
            str(segment_id).strip()
            for segment_id in description_evidence_segment_ids
            if str(segment_id).strip()
        ]
    )
    next_post_metadata_source = (
        clip.post_metadata_source
        if post_metadata_source is _STYLE_UNSET
        else post_metadata_source
    )
    next_post_metadata_revision_hash = (
        clip.post_metadata_revision_hash
        if post_metadata_revision_hash is _STYLE_UNSET
        else post_metadata_revision_hash
    )
    next_thumbnail_kicker = (
        clip.thumbnail_kicker
        if thumbnail_kicker is _STYLE_UNSET
        else " ".join(str(thumbnail_kicker).split()).strip()
    )
    next_thumbnail_line1 = (
        clip.thumbnail_line1
        if thumbnail_line1 is _STYLE_UNSET
        else " ".join(str(thumbnail_line1).split()).strip()
    )
    next_thumbnail_line2 = (
        clip.thumbnail_line2
        if thumbnail_line2 is _STYLE_UNSET
        else " ".join(str(thumbnail_line2).split()).strip()
    )
    next_thumbnail_frame_seconds = (
        clip.thumbnail_frame_seconds
        if thumbnail_frame_seconds is _STYLE_UNSET
        else (
            None
            if thumbnail_frame_seconds is None
            else round(float(thumbnail_frame_seconds), 3)
        )
    )
    title_candidate_ids = [candidate.id for candidate in next_title_candidates]
    if len(title_candidate_ids) != len(set(title_candidate_ids)):
        raise ValueError("duplicate YouTube title candidate id")
    if next_recommended_title_id and next_recommended_title_id not in title_candidate_ids:
        raise ValueError("recommended title id is not in title candidates")
    if next_selected_title_id and next_selected_title_id not in title_candidate_ids:
        raise ValueError("selected title id is not in title candidates")
    if len(next_youtube_description) > 2000:
        raise ValueError("YouTube description must be 2000 characters or fewer")
    if len(next_youtube_hashtags) > 12:
        raise ValueError("YouTube hashtags must contain 12 items or fewer")
    if len(next_youtube_hashtags) != len(set(next_youtube_hashtags)):
        raise ValueError("duplicate YouTube hashtag")
    if any(not hashtag.startswith("#") for hashtag in next_youtube_hashtags):
        raise ValueError("YouTube hashtags must start with #")
    if len(next_youtube_tags) > 40:
        raise ValueError("YouTube tags must contain 40 items or fewer")
    if len(next_youtube_tags) != len({tag.casefold() for tag in next_youtube_tags}):
        raise ValueError("duplicate YouTube tag")
    if len(",".join(next_youtube_tags)) > 500:
        raise ValueError("YouTube tags must be 500 characters or fewer")
    if len(next_description_evidence_segment_ids) != len(
        set(next_description_evidence_segment_ids)
    ):
        raise ValueError("duplicate description evidence segment id")
    if len(next_thumbnail_kicker) > 40:
        raise ValueError("thumbnail kicker must be 40 characters or fewer")
    if len(next_thumbnail_line1) > 60 or len(next_thumbnail_line2) > 60:
        raise ValueError("thumbnail title line must be 60 characters or fewer")
    if (
        next_thumbnail_frame_seconds is not None
        and not 0 <= next_thumbnail_frame_seconds <= clip.duration
    ):
        raise ValueError("thumbnail frame must stay within the selected clip")

    changed = (
        clip.title != normalized_title
        or clip.publication_title != next_publication_title
        or clip.hook_text != normalized_hook
        or clip.hook_duration_seconds != hook_duration_seconds
        or clip.title_style != next_title_style
        or clip.hook_style != next_hook_style
        or clip.subtitle_style != next_subtitle_style
        or clip.subtitle_styles != next_subtitle_styles
        or clip.title_candidates != next_title_candidates
        or clip.recommended_title_id != next_recommended_title_id
        or clip.selected_title_id != next_selected_title_id
        or clip.youtube_description != next_youtube_description
        or clip.youtube_hashtags != next_youtube_hashtags
        or clip.youtube_tags != next_youtube_tags
        or clip.description_evidence_segment_ids != next_description_evidence_segment_ids
        or clip.post_metadata_source != next_post_metadata_source
        or clip.post_metadata_revision_hash != next_post_metadata_revision_hash
        or clip.thumbnail_kicker != next_thumbnail_kicker
        or clip.thumbnail_line1 != next_thumbnail_line1
        or clip.thumbnail_line2 != next_thumbnail_line2
        or clip.thumbnail_frame_seconds != next_thumbnail_frame_seconds
    )
    if not changed:
        return _refresh_counts(document)

    original_title = clip.original_title or clip.title
    clip.original_title = original_title
    clip.title = normalized_title
    clip.publication_title = next_publication_title
    clip.title_edited = normalized_title != original_title
    clip.hook_text = normalized_hook
    clip.hook_duration_seconds = round(hook_duration_seconds, 3)
    clip.title_style = next_title_style if isinstance(next_title_style, ClipTextStyle) else None
    clip.hook_style = next_hook_style if isinstance(next_hook_style, ClipTextStyle) else None
    clip.subtitle_style = (
        next_subtitle_style if isinstance(next_subtitle_style, ClipTextStyle) else None
    )
    clip.title_candidates = next_title_candidates
    clip.subtitle_styles = next_subtitle_styles
    clip.recommended_title_id = next_recommended_title_id
    clip.selected_title_id = next_selected_title_id
    clip.youtube_description = next_youtube_description
    clip.youtube_hashtags = next_youtube_hashtags
    clip.youtube_tags = next_youtube_tags
    clip.description_evidence_segment_ids = next_description_evidence_segment_ids
    clip.post_metadata_source = next_post_metadata_source
    clip.post_metadata_revision_hash = next_post_metadata_revision_hash
    clip.thumbnail_kicker = next_thumbnail_kicker
    clip.thumbnail_line1 = next_thumbnail_line1
    clip.thumbnail_line2 = next_thumbnail_line2
    clip.thumbnail_frame_seconds = next_thumbnail_frame_seconds
    clip.confirmed = False
    return _refresh_counts(document)


def update_review_clip_framing(
    document: SubtitleReviewDocument,
    clip_id: str,
    *,
    framing_offset_x: float,
    framing_offset_y: float,
    framing_zoom: float,
) -> SubtitleReviewDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    if clip.type != "short":
        raise ValueError("framing can only be changed for short clips")
    if not -100 <= framing_offset_x <= 100 or not -100 <= framing_offset_y <= 100:
        raise ValueError("framing offsets must be between -100 and 100")
    if not 1.0 <= framing_zoom <= 3.0:
        raise ValueError("framing zoom must be between 1.0 and 3.0")

    next_x = round(float(framing_offset_x), 2)
    next_y = round(float(framing_offset_y), 2)
    next_zoom = round(float(framing_zoom), 3)
    if (
        clip.framing_offset_x == next_x
        and clip.framing_offset_y == next_y
        and clip.framing_zoom == next_zoom
    ):
        return _refresh_counts(document)

    clip.framing_offset_x = next_x
    clip.framing_offset_y = next_y
    clip.framing_zoom = next_zoom
    clip.confirmed = False
    return _refresh_counts(document)


def update_review_hook_scene(
    document: SubtitleReviewDocument,
    clip_id: str,
    *,
    start: float | None,
    end: float | None,
) -> SubtitleReviewDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    if (start is None) != (end is None):
        raise ValueError("hook scene requires both start and end")
    if start is not None and end is not None:
        hook_duration = end - start
        if not 0.5 <= hook_duration <= 3.0:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        if start < clip.start - 0.001 or end > clip.end + 0.001:
            raise ValueError("hook scene must stay within the selected clip")
        # The configured short maximum is a selection target. Once a short is in
        # subtitle review, a manual hook-scene edit may take the finished duration
        # slightly past that target. The hook itself remains bounded to 0.5-3s and
        # must stay inside the selected clip.

    if clip.hook_scene_start == start and clip.hook_scene_end == end:
        return _refresh_counts(document)
    clip.hook_scene_start = start
    clip.hook_scene_end = end
    clip.confirmed = False
    return _refresh_counts(document)


def confirm_review_clip(document: SubtitleReviewDocument, clip_id: str) -> SubtitleReviewDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    clip.confirmed = True
    return _refresh_counts(document)


def queue_review_render(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    if document.confirmed_clip_count != document.total_clip_count:
        raise ValueError("all clips must be confirmed before rendering")
    document.state = "render_queued"
    return _refresh_counts(document)


def queue_auto_review_render(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    """Queue an auto-gated document without forging human confirmations."""
    if document.state != "awaiting_review":
        raise ValueError("subtitle review is not awaiting automated rendering")
    document.state = "render_queued"
    return _refresh_counts(document)


def mark_review_rendering(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    document.state = "rendering"
    return _refresh_counts(document)


def mark_review_completed(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    document.state = "completed"
    return _refresh_counts(document)


def reopen_completed_review(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    if document.state != "completed":
        raise ValueError("subtitle review is not completed")
    document.state = "awaiting_review"
    document.render_revision += 1
    document.reopened_at = _utc_iso()
    for clip in document.clips:
        clip.confirmed = False
    return _refresh_counts(document)


def convert_review_clip_to_short(
    document: SubtitleReviewDocument,
    clip_id: str,
    *,
    start: float,
    end: float,
) -> SubtitleReviewDocument:
    """Convert the only clip in an isolated re-edit job to a short draft."""
    if document.reedit_source_job_id is None:
        raise ValueError("clip conversion is available only in an isolated re-edit job")
    if len(document.clips) != 1:
        raise ValueError("isolated re-edit job must contain exactly one clip")
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    if clip.type != "normal":
        raise ValueError("only a normal clip can be converted to a short")
    if start < clip.start - 0.001 or end > clip.end + 0.001 or end <= start:
        raise ValueError("short range must stay within the source normal clip")

    retained_hook = bool(
        clip.hook_scene_start is not None
        and clip.hook_scene_end is not None
        and clip.hook_scene_start >= start - 0.001
        and clip.hook_scene_end <= end + 0.001
    )
    hook_duration = 0.0
    if retained_hook and clip.hook_scene_start is not None and clip.hook_scene_end is not None:
        hook_duration = clip.hook_scene_end - clip.hook_scene_start
    if end - start + hook_duration > document.short_max_duration + 0.001:
        raise ValueError(
            f"short duration must not exceed {document.short_max_duration:g} seconds"
        )

    clip.type = "short"
    clip.thumbnail_kicker = ""
    clip.thumbnail_line1 = ""
    clip.thumbnail_line2 = ""
    clip.thumbnail_frame_seconds = None
    if clip.publication_title:
        clip.publication_title = strip_normal_publication_title_suffix(
            clip.publication_title, suffix=clip.normal_title_suffix
        )
    clip.start = start
    clip.end = end
    clip.duration = end - start
    if not retained_hook:
        clip.hook_scene_start = None
        clip.hook_scene_end = None

    retained_segments = sorted(
        (
            segment
            for segment in document.segments
            if segment.end > start and segment.start < end
        ),
        key=lambda segment: segment.index,
    )
    for segment in retained_segments:
        segment.affected_clip_ids = [clip_id]
    document.segments = retained_segments
    clip.segment_ids = [segment.id for segment in retained_segments]

    had_post_metadata = bool(
        clip.title_candidates
        or clip.recommended_title_id
        or clip.selected_title_id
        or clip.youtube_description
        or clip.youtube_hashtags
        or clip.description_evidence_segment_ids
        or clip.post_metadata_source
        or clip.post_metadata_revision_hash
    )
    clip.title_candidates = []
    clip.recommended_title_id = None
    clip.selected_title_id = None
    clip.youtube_description = ""
    clip.youtube_hashtags = []
    clip.youtube_tags = []
    clip.description_evidence_segment_ids = []
    clip.post_metadata_revision_hash = None
    if had_post_metadata:
        clip.post_metadata_source = "manual"

    # Keep the user's saved text styles. Only resolved values are rebuilt for 9:16.
    clip.resolved_title_style = None
    clip.resolved_hook_style = None
    clip.resolved_subtitle_style = None
    clip.resolved_default_title_style = None
    clip.resolved_default_hook_style = None
    clip.resolved_default_subtitle_style = None
    clip.preview_state = "queued"
    clip.preview_spec_hash = None
    clip.preview_error = None
    clip.preview_video_url = None
    clip.live_preview_spec_hash = None
    clip.live_preview_video_url = None
    clip.confirmed = False
    return _refresh_counts(document)


def restore_review_after_render_failure(
    document: SubtitleReviewDocument,
) -> SubtitleReviewDocument:
    document.state = "awaiting_review"
    return _refresh_counts(document)


def apply_reviewed_text(
    transcript_segments: Sequence[TranscriptSegment],
    document: SubtitleReviewDocument,
) -> list[TranscriptSegment]:
    if any(s.preserve_segmentation or s.source_indices or s.single_line for s in document.segments):
        replaced = {i for s in document.segments for i in (s.source_indices or [s.index])}
        output = [s for i, s in enumerate(transcript_segments) if i not in replaced]
        for segment in document.segments:
            source_index = (segment.source_indices or [segment.index])[0]
            source = transcript_segments[source_index]
            output.append(source.model_copy(update={
                "start": segment.start, "end": segment.end, "text": segment.text,
                "preserve_segmentation": segment.preserve_segmentation,
                "single_line": segment.single_line,
            }))
        return sorted(output, key=lambda s: (s.start, s.end))
    reviewed_text = {segment.index: segment.text for segment in document.segments}
    return [
        segment.model_copy(update={"text": reviewed_text.get(index, segment.text)})
        for index, segment in enumerate(transcript_segments)
    ]


def apply_reviewed_clip_content(
    selection: CandidateSelection,
    document: SubtitleReviewDocument,
) -> CandidateSelection:
    reviewed_by_id = {clip.id: clip for clip in document.clips}

    def update_candidate(candidate: Candidate) -> Candidate:
        clip = reviewed_by_id.get(candidate.id)
        if clip is None:
            return candidate
        publication_title = ensure_publication_title_suffix(
            clip.publication_title or clip.title,
            clip_type=clip.type,
            suffix=clip.normal_title_suffix,
        )
        overlay_title = (
            clip.title
            if (
                clip.publication_title is not None
                or clip.title_edited
                or candidate.type == "normal"
            )
            else (candidate.overlay_title or clip.title)
        )
        updates: dict[str, object] = {
            "title": publication_title,
            "overlay_title": overlay_title,
        }
        if (
            clip.title_edited
            or publication_title != candidate.title
            or (
                candidate.overlay_title is not None
                and overlay_title != candidate.overlay_title
            )
        ):
            updates["title_source"] = "manual_review"
        updates["hook_text"] = clip.hook_text or None
        updates["hook_duration_seconds"] = clip.hook_duration_seconds
        updates["hook_scene_start"] = clip.hook_scene_start
        updates["hook_scene_end"] = clip.hook_scene_end
        updates["thumbnail_kicker"] = clip.thumbnail_kicker
        updates["thumbnail_line1"] = clip.thumbnail_line1
        updates["thumbnail_line2"] = clip.thumbnail_line2
        updates["thumbnail_frame_seconds"] = clip.thumbnail_frame_seconds
        updates["title_candidates"] = clip.title_candidates
        updates["recommended_title_id"] = clip.recommended_title_id
        updates["selected_title_id"] = clip.selected_title_id
        updates["youtube_description"] = clip.youtube_description or None
        updates["youtube_hashtags"] = clip.youtube_hashtags
        updates["youtube_tags"] = clip.youtube_tags
        updates["description_evidence_segment_ids"] = clip.description_evidence_segment_ids
        updates["post_metadata_source"] = clip.post_metadata_source
        updates["post_metadata_revision_hash"] = clip.post_metadata_revision_hash
        updates["hook_style"] = clip.hook_style
        updates["title_style"] = clip.title_style
        updates["subtitle_style"] = clip.subtitle_style
        updates["subtitle_styles"] = clip.subtitle_styles
        updates["framing_offset_x"] = clip.framing_offset_x
        updates["framing_offset_y"] = clip.framing_offset_y
        updates["framing_zoom"] = clip.framing_zoom
        updates["short_layout"] = clip.short_layout
        return candidate.model_copy(update=updates)

    return selection.model_copy(
        update={
            "normal_clips": [update_candidate(candidate) for candidate in selection.normal_clips],
            "shorts": [update_candidate(candidate) for candidate in selection.shorts],
        }
    )


def write_subtitle_review_summary(
    document: SubtitleReviewDocument,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": True,
        "state": document.state,
        "render_revision": document.render_revision,
        "reopened_at": document.reopened_at,
        "short_overlay_title_mode": document.short_overlay_title_mode,
        "short_layout": document.short_layout,
        "short_top_banner_enabled": document.short_top_banner_enabled,
        "short_bottom_banner_enabled": document.short_bottom_banner_enabled,
        "overlay_title_expected_by_clip": {
            clip.id: clip.overlay_title_expected for clip in document.clips
        },
        "total_clip_count": document.total_clip_count,
        "confirmed_clip_count": document.confirmed_clip_count,
        "reviewed_segment_count": len(document.segments),
        "edited_segment_count": document.edited_segment_count,
        "edited_segment_indices": [segment.index for segment in document.segments if segment.edited],
        "edited_title_clip_ids": [clip.id for clip in document.clips if clip.title_edited],
        "hook_clip_ids": [clip.id for clip in document.clips if clip.hook_text],
        "hook_scene_clip_ids": [
            clip.id
            for clip in document.clips
            if clip.hook_scene_start is not None and clip.hook_scene_end is not None
        ],
        "timestamps_changed": any(segment.source_indices for segment in document.segments),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
