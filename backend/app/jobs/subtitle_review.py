import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection


SUBTITLE_REVIEW_FILENAME = "subtitle_review.json"
SUBTITLE_REVIEW_SUMMARY_FILENAME = "subtitle_review_summary.json"
REVIEWED_TRANSCRIPT_FILENAME = "reviewed_transcript_segments.json"
SUBTITLE_REVIEW_PREVIEW_DIRNAME = "subtitle_review_previews"

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
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    preview_video_url: str | None = Field(default=None, alias="previewVideoUrl")
    segment_ids: list[str] = Field(default_factory=list, alias="segmentIds")
    confirmed: bool = False
    edited_segment_count: int = Field(default=0, ge=0, alias="editedSegmentCount")

    model_config = ConfigDict(populate_by_name=True)


class SubtitleReviewDocument(BaseModel):
    version: int = 1
    job_id: str = Field(alias="jobId")
    state: SubtitleReviewState = "awaiting_review"
    source_video_url: str = Field(alias="sourceVideoUrl")
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


def apply_reviewed_text(
    transcript_segments: Sequence[TranscriptSegment],
    document: SubtitleReviewDocument,
) -> list[TranscriptSegment]:
    reviewed_text = {segment.index: segment.text for segment in document.segments}
    return [
        segment.model_copy(update={"text": reviewed_text.get(index, segment.text)})
        for index, segment in enumerate(transcript_segments)
    ]


def write_subtitle_review_summary(
    document: SubtitleReviewDocument,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": True,
        "state": document.state,
        "total_clip_count": document.total_clip_count,
        "confirmed_clip_count": document.confirmed_clip_count,
        "reviewed_segment_count": len(document.segments),
        "edited_segment_count": document.edited_segment_count,
        "edited_segment_indices": [segment.index for segment in document.segments if segment.edited],
        "timestamps_changed": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
