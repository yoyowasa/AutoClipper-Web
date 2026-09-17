from typing import Any

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.candidates.used_ranges import USED_RANGES_SETTING, merge_ranges, used_ranges
from app.jobs.clip_plan import ClipPlanDocument


def target_count(settings: dict[str, Any], plan: ClipPlanDocument, kind: str) -> int:
    key = "normalClipCount" if kind == "normal" else "shortCount"
    return max(int(settings.get(key, 0)), sum(c.type == kind for c in plan.clips))


def prepare_kept_candidates(
    settings: dict[str, Any], plan: ClipPlanDocument | None, previous: CandidateSelection,
) -> tuple[dict[str, Any], list[Candidate]]:
    ids = set(settings.get("keptClipIds", []))
    if not ids or plan is None:
        return settings, []
    source = {c.id: c for c in [*previous.normal_clips, *previous.shorts]}
    kept = []
    for clip in plan.clips:
        if clip.id in ids:
            kept.append(source[clip.id].model_copy(update={
                "type": clip.type, "start": clip.start, "end": clip.end, "duration": clip.duration,
                "hook_scene_start": clip.hook_scene_start, "hook_scene_end": clip.hook_scene_end,
            }, deep=True))
    reduced = {**settings}
    for kind, key in [("normal", "normalClipCount"), ("short", "shortCount")]:
        reduced[key] = target_count(settings, plan, kind) - sum(c.type == kind and c.id in ids for c in plan.clips)
    # Kept scenes are always excluded from replacements, even when variety is OFF.
    reduced[USED_RANGES_SETTING] = merge_ranges([*used_ranges(settings), *[(c.start, c.end) for c in kept]])
    return reduced, kept


def merge_kept_candidates(
    selection: CandidateSelection, kept: list[Candidate], plan: ClipPlanDocument,
) -> CandidateSelection:
    if not kept:
        return selection
    by_id = {c.id: c for c in kept}
    updates: dict[str, Any] = {}
    missing = {}
    for kind, field, count_field in [("normal", "normal_clips", "requested_normal_count"),
                                     ("short", "shorts", "requested_short_count")]:
        fresh = iter(getattr(selection, field))
        result = []
        for clip in plan.clips:
            if clip.type == kind:
                candidate = by_id.get(clip.id) if clip.id in by_id else next(fresh, None)
                if candidate is not None:
                    result.append(candidate)
        requested = target_count(plan.settings, plan, kind)
        for candidate in fresh:
            if len(result) >= requested:
                break
            result.append(candidate)
        updates[field] = result
        updates[count_field] = requested
        missing[kind] = requested - len(result)
    updates["unfilled_requested_counts"] = missing
    return selection.model_copy(update=updates)
