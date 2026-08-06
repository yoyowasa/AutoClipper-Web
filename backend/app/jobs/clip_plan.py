import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.transcript_postprocess import repair_known_transcript_artifact_text
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection


CLIP_PLAN_FILENAME = "clip_plan.json"

ClipPlanState = Literal["preparing", "awaiting_review", "reselecting", "approved"]


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class ClipPlanClip(BaseModel):
    id: str
    type: Literal["normal", "short"]
    title: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    preview_video_url: str | None = Field(default=None, alias="previewVideoUrl")
    transcript_excerpt: str = Field(default="", alias="transcriptExcerpt")
    final_score: float | None = Field(default=None, alias="finalScore")
    rule_score: float | None = Field(default=None, alias="ruleScore")
    ai_score: float | None = Field(default=None, alias="aiScore")
    selection_reason: str | None = Field(default=None, alias="selectionReason")
    boundary_refined: bool = Field(default=False, alias="boundaryRefined")
    recommended_start: float | None = Field(
        default=None,
        ge=0,
        alias="recommendedStart",
    )
    recommended_end: float | None = Field(
        default=None,
        ge=0,
        alias="recommendedEnd",
    )
    manually_adjusted: bool = Field(default=False, alias="manuallyAdjusted")
    hook_scene_start: float | None = Field(
        default=None,
        ge=0,
        alias="hookSceneStart",
    )
    hook_scene_end: float | None = Field(
        default=None,
        ge=0,
        alias="hookSceneEnd",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_hook_scene(self) -> "ClipPlanClip":
        hook_start = self.hook_scene_start
        hook_end = self.hook_scene_end
        if (hook_start is None) != (hook_end is None):
            raise ValueError("hook scene requires both start and end")
        if hook_start is None or hook_end is None:
            return self
        if self.type != "short":
            raise ValueError("hook scene is only supported for short clips")
        if hook_end <= hook_start:
            raise ValueError("hook scene end must be greater than start")
        if not 0.5 <= hook_end - hook_start <= 3.0:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        if hook_start < self.start - 0.001 or hook_end > self.end + 0.001:
            raise ValueError("hook scene must stay within the selected clip")
        return self


class ClipPlanDocument(BaseModel):
    version: int = 3
    job_id: str = Field(alias="jobId")
    state: ClipPlanState = "preparing"
    revision: int = Field(default=1, ge=1)
    source_video_url: str = Field(alias="sourceVideoUrl")
    source_duration: float | None = Field(
        default=None,
        ge=0,
        alias="sourceDuration",
    )
    clips: list[ClipPlanClip] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


def clip_plan_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / CLIP_PLAN_FILENAME


def clip_plan_preview_url(job_id: str, clip_id: str) -> str:
    return f"/api/jobs/{job_id}/clip-plan/clips/{clip_id}/preview-video"


def _candidate_title(candidate: Candidate, index: int) -> str:
    prefix = "通常切り抜き" if candidate.type == "normal" else "ショート"
    return (candidate.title or candidate.overlay_title or f"{prefix} {index:02d}").strip()


def _repaired_artifact_text(text: str) -> str:
    return repair_known_transcript_artifact_text(text)


def _excerpt(text: str, limit: int = 360) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def build_clip_plan(
    job_id: str,
    selection: CandidateSelection,
    settings: dict[str, Any],
    *,
    revision: int = 1,
    source_duration: float | None = None,
) -> ClipPlanDocument:
    type_indices = {"normal": 0, "short": 0}
    clips: list[ClipPlanClip] = []
    for candidate in [*selection.normal_clips, *selection.shorts]:
        type_indices[candidate.type] += 1
        clips.append(
            ClipPlanClip(
                id=candidate.id,
                type=candidate.type,
                title=_repaired_artifact_text(
                    _candidate_title(candidate, type_indices[candidate.type])
                ),
                start=candidate.start,
                end=candidate.end,
                duration=candidate.duration,
                transcriptExcerpt=_excerpt(
                    _repaired_artifact_text(candidate.transcript_text)
                ),
                finalScore=candidate.final_score,
                ruleScore=candidate.rule_score,
                aiScore=candidate.ai_score,
                selectionReason=candidate.selection_reason,
                boundaryRefined=candidate.boundary_refined,
                recommendedStart=candidate.start,
                recommendedEnd=candidate.end,
                hookSceneStart=candidate.hook_scene_start,
                hookSceneEnd=candidate.hook_scene_end,
            )
        )
    now = _utc_iso()
    return ClipPlanDocument(
        jobId=job_id,
        state="preparing",
        revision=revision,
        sourceVideoUrl=f"/api/jobs/{job_id}/source-video",
        sourceDuration=source_duration,
        clips=clips,
        settings=settings,
        createdAt=now,
        updatedAt=now,
    )


def mark_clip_plan_awaiting_review(
    document: ClipPlanDocument,
    *,
    preview_clip_ids: Sequence[str],
) -> ClipPlanDocument:
    available = set(preview_clip_ids)
    for clip in document.clips:
        clip.preview_video_url = (
            clip_plan_preview_url(document.job_id, clip.id)
            if clip.id in available
            else None
        )
    document.state = "awaiting_review"
    document.updated_at = _utc_iso()
    return document


def mark_clip_plan_approved(document: ClipPlanDocument) -> ClipPlanDocument:
    document.state = "approved"
    document.updated_at = _utc_iso()
    return document


def update_clip_plan_boundary(
    document: ClipPlanDocument,
    clip_id: str,
    *,
    start: float,
    end: float,
    transcript_excerpt: str,
) -> ClipPlanDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    if end <= start:
        raise ValueError("end must be greater than start")

    if clip.recommended_start is None:
        clip.recommended_start = clip.start
    if clip.recommended_end is None:
        clip.recommended_end = clip.end
    clip.start = round(float(start), 3)
    clip.end = round(float(end), 3)
    clip.duration = round(clip.end - clip.start, 3)
    clip.transcript_excerpt = _excerpt(transcript_excerpt)
    clip.manually_adjusted = not (
        abs(clip.start - clip.recommended_start) < 0.001
        and abs(clip.end - clip.recommended_end) < 0.001
    )
    document.updated_at = _utc_iso()
    return document


def update_clip_plan_hook_scene(
    document: ClipPlanDocument,
    clip_id: str,
    *,
    start: float | None,
    end: float | None,
) -> ClipPlanDocument:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise KeyError(clip_id)
    if clip.type != "short":
        raise ValueError("hook scene is only supported for short clips")
    if (start is None) != (end is None):
        raise ValueError("hook scene requires both start and end")
    if start is not None and end is not None:
        if end <= start:
            raise ValueError("hook scene end must be greater than start")
        if not 0.5 <= end - start <= 3.0:
            raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
        if start < clip.start - 0.001 or end > clip.end + 0.001:
            raise ValueError("hook scene must stay within the selected clip")
        clip.hook_scene_start = round(float(start), 3)
        clip.hook_scene_end = round(float(end), 3)
    else:
        clip.hook_scene_start = None
        clip.hook_scene_end = None
    document.updated_at = _utc_iso()
    return document


def write_clip_plan(document: ClipPlanDocument, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            document.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def load_clip_plan(path: str | Path) -> ClipPlanDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    document = ClipPlanDocument.model_validate(payload)
    for clip in document.clips:
        clip.title = _repaired_artifact_text(clip.title)
        clip.transcript_excerpt = _repaired_artifact_text(clip.transcript_excerpt)
    return document
