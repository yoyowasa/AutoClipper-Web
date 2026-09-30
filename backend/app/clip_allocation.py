"""Total-count allocation after quality checks, with legacy fixed-count compatibility."""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection


def is_ai_allocation(settings: Mapping[str, Any]) -> bool:
    return settings.get("totalClipCount") is not None and settings.get("clipAllocationMode", "ai") == "ai"


def confirmed_counts(settings: Mapping[str, Any]) -> dict[str, int]:
    return dict(
        settings.get(
            "_allocationConfirmedCounts",
            {
                "normal": len(settings.get("normalClipTimeRanges", [])),
                "short": len(settings.get("shortClipTimeRanges", [])),
            },
        )
    )


def candidate_pool_counts(settings: Mapping[str, Any]) -> tuple[int, int]:
    if not is_ai_allocation(settings):
        return int(settings.get("normalClipCount", 2)), int(settings.get("shortCount", 3))
    remaining = max(0, int(settings["totalClipCount"]) - sum(confirmed_counts(settings).values()))
    return min(24, remaining), min(24, remaining)


def allocation_summary(selection: CandidateSelection) -> dict[str, Any]:
    if selection.requested_total is None:
        return {}
    return {
        "requestedTotal": selection.requested_total,
        "selectedTotal": selection.selected_total,
        "selectedByType": selection.selected_by_type,
        "shortfallReasons": selection.shortfall_reasons,
        "minimumShortfall": selection.minimum_shortfall,
    }


def allocate_selection(
    selection: CandidateSelection, settings: Mapping[str, Any], *, confirmed: Sequence[Candidate] = ()
) -> CandidateSelection:
    if not is_ai_allocation(settings):
        return selection
    total = int(settings["totalClipCount"])
    confirmed_ranges = {(c.type, c.start, c.end) for c in confirmed}
    fixed = {
        c.id: c
        for c in [*selection.normal_clips, *selection.shorts]
        if c.selection_reason in {"manual_time_range", "manual_edit"} and (c.type, c.start, c.end) not in confirmed_ranges
    }
    fixed.update({c.id: c for c in confirmed})
    if len(fixed) > total:
        raise ValueError("手動・キープの本数が合計本数を超えています。")

    def rank(c: Candidate):
        confidence_score = c.ai_score if c.used_ai_score else None
        return (
            -(confidence_score if confidence_score is not None else c.final_score or c.rule_score or 0),
            -(c.final_score or c.rule_score or 0),
            c.start,
            c.end,
            c.type,
            c.id,
        )

    pool = sorted(
        {
            c.id: c
            for c in [*selection.normal_clips, *selection.shorts]
            if c.id not in fixed and c.should_use is not False and c.below_quality_threshold is not True and c.hard_gate_passed is not False
        }.values(),
        key=rank,
    )
    picked = list(fixed.values())
    picked_ids = set(fixed)
    minima = {"normal": int(settings.get("minNormalClipCount", 0)), "short": int(settings.get("minShortCount", 0))}
    for kind in ("normal", "short"):
        needed = max(0, minima[kind] - sum(c.type == kind for c in picked))
        for candidate in (c for c in pool if c.type == kind):
            if needed <= 0 or len(picked) >= total:
                break
            picked.append(candidate)
            picked_ids.add(candidate.id)
            needed -= 1
    for candidate in pool:
        if len(picked) >= total:
            break
        if candidate.id not in picked_ids:
            picked.append(candidate)
            picked_ids.add(candidate.id)
    counts = {kind: sum(c.type == kind for c in picked) for kind in minima}
    minimum_shortfall = {kind: max(0, minima[kind] - counts[kind]) for kind in minima}
    reasons = Counter(
        reason
        for _, _, reason in {(item.candidate_id, item.type, reason) for item in selection.rejected_candidates for reason in item.reasons}
    )
    if len(picked) < total:
        reasons["insufficient_strong_candidates"] = total - len(picked)
    for kind, count in minimum_shortfall.items():
        if count:
            reasons[f"minimum_{kind}_shortfall"] = count
    return selection.model_copy(
        update={
            "normal_clips": [c for c in picked if c.type == "normal"],
            "shorts": [c for c in picked if c.type == "short"],
            "requested_total": total,
            "selected_total": len(picked),
            "selected_by_type": counts,
            "shortfall_reasons": dict(reasons) if len(picked) < total or any(minimum_shortfall.values()) else {},
            "minimum_shortfall": minimum_shortfall,
            "requested_normal_count": counts["normal"],
            "requested_short_count": counts["short"],
            "unfilled_requested_counts": {"total": max(0, total - len(picked)), **minimum_shortfall},
        }
    )
