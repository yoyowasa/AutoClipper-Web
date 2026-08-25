from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.clip_plan import ClipPlanClip, ClipPlanDocument


MANUAL_WORKFLOW_MODE = "manual"
MANUAL_SUBTITLE_MODES = {"auto", "none", "manual"}
MAX_MANUAL_NORMAL_CLIPS = 12
MAX_MANUAL_SHORTS = 24


def is_manual_workflow(settings: dict[str, Any]) -> bool:
    return settings.get("workflowMode", settings.get("workflow_mode")) == MANUAL_WORKFLOW_MODE


def manual_edit_is_finalized(settings: dict[str, Any]) -> bool:
    return bool(
        settings.get(
            "manualEditFinalized",
            settings.get("manual_edit_finalized", False),
        )
    )


def manual_subtitle_mode(settings: dict[str, Any]) -> str:
    value = settings.get(
        "manualSubtitleMode",
        settings.get("manual_subtitle_mode", "auto"),
    )
    return str(value) if value in MANUAL_SUBTITLE_MODES else "auto"


def touch_manual_document(document: ClipPlanDocument) -> None:
    document.revision += 1
    document.updated_at = datetime.now(UTC).isoformat()


def validate_manual_clip_counts(clips: Sequence[ClipPlanClip]) -> None:
    normal_count = sum(clip.type == "normal" for clip in clips)
    short_count = sum(clip.type == "short" for clip in clips)
    if normal_count > MAX_MANUAL_NORMAL_CLIPS:
        raise ValueError(f"manual normal clips must not exceed {MAX_MANUAL_NORMAL_CLIPS}")
    if short_count > MAX_MANUAL_SHORTS:
        raise ValueError(f"manual shorts must not exceed {MAX_MANUAL_SHORTS}")


def apply_manual_clip_metadata(
    candidates: Sequence[Candidate],
    settings: dict[str, Any],
) -> list[Candidate]:
    raw_metadata = settings.get("manualClipMetadata", [])
    metadata = [item for item in raw_metadata if isinstance(item, dict)]
    by_type = {
        "normal": [item for item in metadata if item.get("type") == "normal"],
        "short": [item for item in metadata if item.get("type") == "short"],
    }
    type_indices = {"normal": 0, "short": 0}
    updated_candidates: list[Candidate] = []
    for candidate in candidates:
        index = type_indices[candidate.type]
        type_indices[candidate.type] += 1
        if index >= len(by_type[candidate.type]):
            updated_candidates.append(candidate)
            continue
        item = by_type[candidate.type][index]
        payload = candidate.model_dump()
        payload.update(
            {
                "id": str(item.get("id") or candidate.id),
                "title": str(item.get("title") or "").strip() or candidate.title,
                "hook_scene_start": item.get("hookSceneStart"),
                "hook_scene_end": item.get("hookSceneEnd"),
            }
        )
        updated_candidates.append(Candidate.model_validate(payload))
    return updated_candidates


def build_manual_selection(
    normal_candidates: Sequence[Candidate],
    short_candidates: Sequence[Candidate],
) -> CandidateSelection:
    return CandidateSelection(
        normalClips=list(normal_candidates),
        shorts=list(short_candidates),
        selectionPolicy="fill_requested",
        requestedNormalCount=len(normal_candidates),
        requestedShortCount=len(short_candidates),
        hardGatePassedCount=len(normal_candidates) + len(short_candidates),
        normalHardGatePassedCount=len(normal_candidates),
        shortHardGatePassedCount=len(short_candidates),
        selectedAboveThresholdCount=len(normal_candidates) + len(short_candidates),
        selectedClusters={"normal": [], "short": []},
        unfilledRequestedCounts={"normal": 0, "short": 0},
    )


def manual_plan_settings(
    document: ClipPlanDocument,
    settings: dict[str, Any],
) -> dict[str, Any]:
    validate_manual_clip_counts(document.clips)
    normal_clips = [clip for clip in document.clips if clip.type == "normal"]
    shorts = [clip for clip in document.clips if clip.type == "short"]
    payload = dict(settings)
    subtitle_mode = manual_subtitle_mode(payload)

    payload.update(
        {
            "workflowMode": MANUAL_WORKFLOW_MODE,
            "manualEditFinalized": True,
            "normalClipCount": len(normal_clips),
            "shortCount": len(shorts),
            "normalClipTimeRanges": [
                {
                    "startSeconds": clip.start,
                    "endSeconds": clip.end,
                }
                for clip in normal_clips
            ],
            "shortClipTimeRanges": [
                {
                    "startSeconds": clip.start,
                    "endSeconds": clip.end,
                }
                for clip in shorts
            ],
            "manualClipMetadata": [
                {
                    "id": clip.id,
                    "type": clip.type,
                    "title": clip.title,
                    "startSeconds": clip.start,
                    "endSeconds": clip.end,
                    "hookSceneStart": clip.hook_scene_start,
                    "hookSceneEnd": clip.hook_scene_end,
                }
                for clip in document.clips
            ],
            "heatmapIntervalMode": False,
            "requireClipPlanReview": False,
            "useOpenAIScoring": False,
            "ensureSelectedOpenAIScored": False,
        }
    )
    if subtitle_mode == "none":
        payload["burnSubtitles"] = False
        payload["requireSubtitleReview"] = True
    elif subtitle_mode == "manual":
        payload["burnSubtitles"] = True
        payload["requireSubtitleReview"] = True
    return payload
