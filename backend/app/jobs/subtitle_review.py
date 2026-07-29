import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.candidates.select_candidates import CandidateSelection
from app.jobs.hook_scene import hook_scene_newly_exceeds_short_limit


SUBTITLE_REVIEW_FILENAME = "subtitle_review.json"
SUBTITLE_REVIEW_SUMMARY_FILENAME = "subtitle_review_summary.json"
REVIEWED_TRANSCRIPT_FILENAME = "reviewed_transcript_segments.json"
SUBTITLE_REVIEW_PREVIEW_DIRNAME = "subtitle_review_previews"
_STYLE_UNSET = object()

SubtitleReviewState = Literal["awaiting_review", "render_queued", "rendering", "completed"]


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

    model_config = ConfigDict(populate_by_name=True)


class SubtitleReviewClip(BaseModel):
    id: str
    type: Literal["normal", "short"]
    title: str
    original_title: str | None = Field(default=None, alias="originalTitle")
    title_edited: bool = Field(default=False, alias="titleEdited")
    hook_text: str = Field(default="", alias="hookText")
    hook_duration_seconds: float = Field(default=3.0, ge=1, le=8, alias="hookDurationSeconds")
    hook_scene_start: float | None = Field(default=None, ge=0, alias="hookSceneStart")
    hook_scene_end: float | None = Field(default=None, ge=0, alias="hookSceneEnd")
    title_style: ClipTextStyle | None = Field(default=None, alias="titleStyle")
    hook_style: ClipTextStyle | None = Field(default=None, alias="hookStyle")
    subtitle_style: ClipTextStyle | None = Field(default=None, alias="subtitleStyle")
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    preview_video_url: str | None = Field(default=None, alias="previewVideoUrl")
    segment_ids: list[str] = Field(default_factory=list, alias="segmentIds")
    confirmed: bool = False
    edited_segment_count: int = Field(default=0, ge=0, alias="editedSegmentCount")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_hook_scene(self) -> "SubtitleReviewClip":
        hook_start = self.hook_scene_start
        hook_end = self.hook_scene_end
        if (hook_start is None) != (hook_end is None):
            raise ValueError("hook scene requires both start and end")
        if hook_start is None or hook_end is None:
            return self
        if self.type != "short":
            raise ValueError("hook scene is only supported for short clips")
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
    source_video_url: str = Field(alias="sourceVideoUrl")
    short_max_duration: float = Field(default=75.0, gt=0, alias="shortMaxDuration")
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


def subtitle_review_preview_path(output_dir: str | Path, clip_id: str) -> Path:
    digest = sha256(clip_id.encode("utf-8")).hexdigest()[:16]
    return Path(output_dir) / SUBTITLE_REVIEW_PREVIEW_DIRNAME / f"{digest}.mp4"


def subtitle_review_preview_url(job_id: str, clip_id: str) -> str:
    return f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/preview-video"


def _candidate_title(candidate: Candidate, index: int) -> str:
    prefix = "通常切り抜き" if candidate.type == "normal" else "ショート"
    return (candidate.title or candidate.overlay_title or f"{prefix} {index:02d}").strip()


def _segment_id(index: int) -> str:
    return f"segment_{index:05d}"


def _overlaps(segment: TranscriptSegment, candidate: Candidate) -> bool:
    return segment.end > candidate.start and segment.start < candidate.end


def _refresh_counts(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    edited_by_id = {segment.id: segment.edited for segment in document.segments}
    for clip in document.clips:
        clip.edited_segment_count = sum(1 for segment_id in clip.segment_ids if edited_by_id.get(segment_id, False))
    document.confirmed_clip_count = sum(1 for clip in document.clips if clip.confirmed)
    document.total_clip_count = len(document.clips)
    document.edited_segment_count = sum(1 for segment in document.segments if segment.edited)
    document.updated_at = _utc_iso()
    return document


def build_subtitle_review(
    job_id: str,
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    *,
    short_max_duration: float = 75.0,
) -> SubtitleReviewDocument:
    selected_candidates = [*selection.normal_clips, *selection.shorts]
    clip_segment_indices: dict[str, list[int]] = {}
    affected_clips: dict[int, list[str]] = {}
    type_indices: dict[str, int] = {"normal": 0, "short": 0}

    for candidate in selected_candidates:
        indices = [
            index
            for index, segment in enumerate(transcript_segments)
            if _overlaps(segment, candidate)
        ]
        clip_segment_indices[candidate.id] = indices
        for index in indices:
            affected_clips.setdefault(index, []).append(candidate.id)

    clips: list[SubtitleReviewClip] = []
    for candidate in selected_candidates:
        type_indices[candidate.type] += 1
        clips.append(
            SubtitleReviewClip(
                id=candidate.id,
                type=candidate.type,
                title=_candidate_title(candidate, type_indices[candidate.type]),
                originalTitle=_candidate_title(candidate, type_indices[candidate.type]),
                hookText=candidate.hook_text or "",
                hookDurationSeconds=candidate.hook_duration_seconds or 3.0,
                hookSceneStart=candidate.hook_scene_start,
                hookSceneEnd=candidate.hook_scene_end,
                titleStyle=candidate.title_style,
                hookStyle=candidate.hook_style,
                subtitleStyle=candidate.subtitle_style,
                start=candidate.start,
                end=candidate.end,
                duration=candidate.duration,
                segmentIds=[
                    _segment_id(segment_index)
                    for segment_index in clip_segment_indices[candidate.id]
                ],
            )
        )
    segments = [
        SubtitleReviewSegment(
            id=_segment_id(index),
            index=index,
            start=segment.start,
            end=segment.end,
            originalText=segment.text,
            text=segment.text,
            confidence=segment.confidence,
            affectedClipIds=affected_clips[index],
        )
        for index, segment in enumerate(transcript_segments)
        if index in affected_clips
    ]
    now = _utc_iso()
    return _refresh_counts(
        SubtitleReviewDocument(
            jobId=job_id,
            sourceVideoUrl=f"/api/jobs/{job_id}/source-video",
            shortMaxDuration=short_max_duration,
            clips=clips,
            segments=segments,
            createdAt=now,
            updatedAt=now,
        )
    )


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


def update_review_clip_content(
    document: SubtitleReviewDocument,
    clip_id: str,
    *,
    title: str,
    hook_text: str = "",
    hook_duration_seconds: float = 3.0,
    title_style: ClipTextStyle | None | object = _STYLE_UNSET,
    hook_style: ClipTextStyle | None | object = _STYLE_UNSET,
    subtitle_style: ClipTextStyle | None | object = _STYLE_UNSET,
) -> SubtitleReviewDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)

    normalized_title = " ".join(title.split()).strip()
    normalized_hook = " ".join(hook_text.split()).strip()
    if not normalized_title:
        raise ValueError("title must not be empty")
    if len(normalized_title) > 80:
        raise ValueError("title must be 80 characters or fewer")
    if len(normalized_hook) > 120:
        raise ValueError("hook text must be 120 characters or fewer")
    if not 1 <= hook_duration_seconds <= 8:
        raise ValueError("hook duration must be between 1 and 8 seconds")
    if clip.type != "short" and normalized_hook:
        raise ValueError("hook text is only supported for short clips")
    if clip.type != "short" and (
        (title_style is not _STYLE_UNSET and title_style is not None)
        or (hook_style is not _STYLE_UNSET and hook_style is not None)
    ):
        raise ValueError("title and hook styles are only supported for short clips")

    next_title_style = clip.title_style if title_style is _STYLE_UNSET else title_style
    next_hook_style = clip.hook_style if hook_style is _STYLE_UNSET else hook_style
    next_subtitle_style = (
        clip.subtitle_style if subtitle_style is _STYLE_UNSET else subtitle_style
    )

    changed = (
        clip.title != normalized_title
        or clip.hook_text != normalized_hook
        or clip.hook_duration_seconds != hook_duration_seconds
        or clip.title_style != next_title_style
        or clip.hook_style != next_hook_style
        or clip.subtitle_style != next_subtitle_style
    )
    if not changed:
        return _refresh_counts(document)

    original_title = clip.original_title or clip.title
    clip.original_title = original_title
    clip.title = normalized_title
    clip.title_edited = normalized_title != original_title
    clip.hook_text = normalized_hook if clip.type == "short" else ""
    clip.hook_duration_seconds = round(hook_duration_seconds, 3)
    clip.title_style = next_title_style if isinstance(next_title_style, ClipTextStyle) else None
    clip.hook_style = next_hook_style if isinstance(next_hook_style, ClipTextStyle) else None
    clip.subtitle_style = (
        next_subtitle_style if isinstance(next_subtitle_style, ClipTextStyle) else None
    )
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
    if clip.type != "short":
        raise ValueError("hook scene is only supported for short clips")
    if (start is None) != (end is None):
        raise ValueError("hook scene requires both start and end")
    if start is not None and end is not None:
        hook_duration = end - start
        if not 0.5 <= hook_duration <= 3.0:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        if start < clip.start - 0.001 or end > clip.end + 0.001:
            raise ValueError("hook scene must stay within the selected clip")
        if hook_scene_newly_exceeds_short_limit(
            clip_duration=clip.duration,
            hook_duration=hook_duration,
            short_max_duration=document.short_max_duration,
        ):
            raise ValueError(
                "hook scene would exceed the configured short maximum duration"
            )

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


def restore_review_after_render_failure(
    document: SubtitleReviewDocument,
) -> SubtitleReviewDocument:
    document.state = "awaiting_review"
    return _refresh_counts(document)


def apply_reviewed_text(
    transcript_segments: Sequence[TranscriptSegment],
    document: SubtitleReviewDocument,
) -> list[TranscriptSegment]:
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
        updates: dict[str, object] = {
            "title": clip.title,
        }
        if clip.title_edited:
            updates["title_source"] = "manual_review"
            if candidate.type == "short":
                updates["overlay_title"] = clip.title
        if candidate.type == "short":
            updates["hook_text"] = clip.hook_text or None
            updates["hook_duration_seconds"] = clip.hook_duration_seconds
            updates["hook_scene_start"] = clip.hook_scene_start
            updates["hook_scene_end"] = clip.hook_scene_end
            updates["title_style"] = clip.title_style
            updates["hook_style"] = clip.hook_style
        updates["subtitle_style"] = clip.subtitle_style
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
        "timestamps_changed": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
