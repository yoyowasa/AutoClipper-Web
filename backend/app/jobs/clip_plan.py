from app.duration_rules import HOOK_SCENE_MIN_SECONDS, HOOK_SCENE_MAX_SECONDS, HOOK_SCENE_DURATION_ERROR
from app.clip_allocation import allocation_summary, allocate_selection, is_ai_allocation
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Sequence

from app.publication.models import PublicationDecision
from app.production_choices import ProductionChoice
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.transcript_postprocess import repair_known_transcript_artifact_text
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.duration_rules import NORMAL_MAX_SECONDS
from app.storage.json_io import write_json_atomic


CLIP_PLAN_FILENAME = "clip_plan.json"

ClipPlanState = Literal[
    "preparing",
    "manual_editing",
    "awaiting_review",
    "reselecting",
    "approved",
]


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class ClipPlanClip(BaseModel):
    publication_decision: Literal["publish", "skip", "unknown"] | None = Field(
        default=None, alias="publicationDecision", exclude_if=lambda v: v is None)
    longform_reason: str = Field(default="", alias="longformReason")
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
            raise ValueError("フック映像の開始と終了を両方指定してください。")
        if hook_start is None or hook_end is None:
            return self
        if hook_end <= hook_start:
            raise ValueError("フック映像の終了は開始より後にしてください。")
        if not HOOK_SCENE_MIN_SECONDS <= hook_end - hook_start <= HOOK_SCENE_MAX_SECONDS:
            raise ValueError(HOOK_SCENE_DURATION_ERROR)
        if hook_start < self.start - 0.001 or hook_end > self.end + 0.001:
            raise ValueError("フック映像は本編の範囲内で指定してください。")
        return self


class ClipPlanDocument(BaseModel):
    publication_decisions: list[PublicationDecision] = Field(default_factory=list, alias="publicationDecisions", exclude_if=lambda v: not v)
    choice_history: list[ProductionChoice] = Field(default_factory=list, alias="choiceHistory", exclude_if=lambda v: not v)
    requested_total: int | None = Field(default=None, alias="requestedTotal")
    selected_total: int | None = Field(default=None, alias="selectedTotal")
    selected_by_type: dict[str, int] = Field(default_factory=dict, alias="selectedByType")
    shortfall_reasons: dict[str, int] = Field(default_factory=dict, alias="shortfallReasons")
    minimum_shortfall: dict[str, int] = Field(default_factory=dict, alias="minimumShortfall")
    version: int = 3
    job_id: str = Field(alias="jobId")
    state: ClipPlanState = "preparing"
    revision: int = Field(default=1, ge=1)
    boundary_reedit: bool = Field(default=False, alias="boundaryReedit")
    subtitle_review_generation: str | None = Field(default=None, alias="subtitleReviewGeneration")
    review_entry_settings: dict[str, Any] | None = Field(default=None, alias="reviewEntrySettings")
    source_video_url: str = Field(alias="sourceVideoUrl")
    editor_video_url: str | None = Field(default=None, alias="editorVideoUrl")
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


def convert_clip_plan_clip_to_normal(
    document: ClipPlanDocument,
    clip_id: str,
) -> ClipPlanClip:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise ValueError("clip plan item not found")

    clip.type = "normal"
    clip.hook_scene_start = None
    clip.hook_scene_end = None
    document.settings = {
        **document.settings,
        "normalClipCount": sum(item.type == "normal" for item in document.clips),
        "shortCount": sum(item.type == "short" for item in document.clips),
    }
    document.updated_at = _utc_iso()
    return clip


def _candidate_title(candidate: Candidate, index: int) -> str:
    prefix = "通常切り抜き" if candidate.type == "normal" else "ショート"
    return (candidate.title or candidate.overlay_title or f"{prefix} {index:02d}").strip()


def convert_clip_plan_clip_to_short(document: ClipPlanDocument, clip_id: str) -> ClipPlanClip:
    clip = next((item for item in document.clips if item.id == clip_id), None)
    if clip is None:
        raise ValueError("clip plan item not found")
    if clip.type == "short":
        return clip
    clip.type = "short"
    clip.longform_reason = ""
    clip.hook_scene_start = None
    clip.hook_scene_end = None
    document.settings = {
        **document.settings,
        "normalClipCount": sum(item.type == "normal" for item in document.clips),
        "shortCount": sum(item.type == "short" for item in document.clips),
    }
    document.updated_at = _utc_iso()
    return clip


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
    editor_video_url: str | None = None,
) -> ClipPlanDocument:
    selection = selection if selection.requested_total is not None else allocate_selection(selection, settings)
    type_indices = {"normal": 0, "short": 0}
    clips: list[ClipPlanClip] = []
    decisions = {d.candidate_id:d for d in selection.publication_decisions}
    for candidate in [*selection.normal_clips, *selection.shorts, *selection.deferred_candidates]:
        type_indices[candidate.type] += 1
        clips.append(
            ClipPlanClip(
                publicationDecision=decisions[candidate.id].decision if candidate.id in decisions else None,
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
                longformReason=candidate.longform_reason if candidate.type == "normal" and candidate.duration > NORMAL_MAX_SECONDS else "",
                boundaryRefined=bool(candidate.boundary_refined),
                recommendedStart=candidate.start,
                recommendedEnd=candidate.end,
                hookSceneStart=candidate.hook_scene_start,
                hookSceneEnd=candidate.hook_scene_end,
            )
        )
    now = _utc_iso()
    return ClipPlanDocument(
        publicationDecisions=selection.publication_decisions,
        choiceHistory=selection.choice_history,
        **allocation_summary(selection),
        jobId=job_id,
        state="preparing",
        revision=revision,
        sourceVideoUrl=f"/api/jobs/{job_id}/source-video",
        editorVideoUrl=editor_video_url,
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
    document.boundary_reedit = False
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
    if clip.type != "normal" or clip.duration <= NORMAL_MAX_SECONDS:
        clip.longform_reason = ""
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
    if (start is None) != (end is None):
        raise ValueError("フック映像の開始と終了を両方指定してください。")
    if start is not None and end is not None:
        if end <= start:
            raise ValueError("フック映像の終了は開始より後にしてください。")
        if not HOOK_SCENE_MIN_SECONDS <= end - start <= HOOK_SCENE_MAX_SECONDS:
            raise ValueError(HOOK_SCENE_DURATION_ERROR)
        if start < clip.start - 0.001 or end > clip.end + 0.001:
            raise ValueError("フック映像は本編の範囲内で指定してください。")
        clip.hook_scene_start = round(float(start), 3)
        clip.hook_scene_end = round(float(end), 3)
    else:
        clip.hook_scene_start = None
        clip.hook_scene_end = None
    document.updated_at = _utc_iso()
    return document


def write_clip_plan(document: ClipPlanDocument, output_path: str | Path, *, choice_source="unrecorded") -> Path:
    from app.production_choice_capture import capture_document
    capture_document(document, Path(output_path), kind="plan", source=choice_source)
    if is_ai_allocation(document.settings):
        document.requested_total = int(document.settings['totalClipCount'])
        active = [c for c in document.clips if c.publication_decision not in {"skip", "unknown"}]
        document.selected_total = len(active)
        document.selected_by_type = {kind: sum(c.type == kind for c in active) for kind in ('normal', 'short')}
        document.minimum_shortfall = {
            kind: max(0, int(document.settings.get(key, 0)) - document.selected_by_type[kind])
            for kind, key in [('normal', 'minNormalClipCount'), ('short', 'minShortCount')]
        }
        reasons = {key: value for key, value in document.shortfall_reasons.items()
                   if key not in {'insufficient_strong_candidates', 'minimum_normal_shortfall', 'minimum_short_shortfall'}}
        shortage = max(0, document.requested_total - document.selected_total)
        if shortage:
            reasons['insufficient_strong_candidates'] = shortage
        for kind, count in document.minimum_shortfall.items():
            if count:
                reasons[f'minimum_{kind}_shortfall'] = count
        document.shortfall_reasons = reasons if shortage or any(document.minimum_shortfall.values()) else {}
    return write_json_atomic(
        Path(output_path),
        document.model_dump(by_alias=True, mode="json"),
    )


def load_clip_plan(path: str | Path) -> ClipPlanDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    document = ClipPlanDocument.model_validate(payload)
    for clip in document.clips:
        clip.title = _repaired_artifact_text(clip.title)
        clip.transcript_excerpt = _repaired_artifact_text(clip.transcript_excerpt)
    return document
