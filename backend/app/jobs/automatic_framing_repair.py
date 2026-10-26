"""One bounded retry of an automatic crop; all final quality gates still apply."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.candidates.select_candidates import CandidateSelection
from app.jobs.quality_gate import QualityGateDecision
from app.jobs.subtitle_review import SubtitleReviewDocument
from app.production_choices import ChoiceCandidate, append_choice
from app.render.render_short import ShortRenderBatchResult


FRAMING_REPAIR_POLICY = "safe_full_frame_v1"
FRAMING_REPAIR_MAX_ATTEMPTS = 1
VISUAL_CHECK = "post_render.visual_framing_layout"


def repair_automatic_short_framing(
    *, db: Session, document: SubtitleReviewDocument, selection: CandidateSelection,
    decision: QualityGateDecision, result: ShortRenderBatchResult,
    render_shorts: Callable[..., ShortRenderBatchResult],
) -> tuple[ShortRenderBatchResult, dict | None]:
    """Only unpublished outputs are passed here (including rerender staging).

    The caller owns the document lock and persists the changed document/selection.
    Existing/manual jobs and non-framing failures never enter this retry.
    """
    if decision.mode != "auto" or not document.subtitle_only_auto:
        return result, None
    visual = next((check for check in decision.checks if check.code == VISUAL_CHECK), None)
    if visual is None or visual.outcome == "pass" or any(
        check.outcome != "pass" for check in decision.checks if check.code != VISUAL_CHECK
    ):
        return result, None
    rejected = {
        item["clipId"]: item
        for key in ("failures", "unknown")
        for item in visual.evidence.get(key, [])
        if isinstance(item, dict) and isinstance(item.get("clipId"), str)
        and item.get("strategy") != "blur_background"
        and item.get("reason") != "rendered_overlay_contract_mismatch"
    }
    eligible = {
        clip.id: clip for clip in document.clips
        if clip.id in rejected and clip.type == "short"
        and clip.automatic_decision_state == "ready"
        and "framing" not in clip.manual_decision_fields
    }
    exported = {export.candidate_id for export in result.exports}
    targets = [candidate for candidate in selection.shorts if candidate.id in eligible and candidate.id in exported]
    if not targets:
        return result, None
    updates = {"short_layout": "blur_background", "framing_offset_x": 0.0,
               "framing_offset_y": 0.0, "framing_zoom": 1.0, "automatic_crop": None}
    for candidate in targets:
        clip = eligible[candidate.id]
        previous = rejected[clip.id]
        content = next((item.values for item in reversed(document.choice_history)
                        if item.clipId == clip.id and item.kind == "framing" and item.values.get("contentPreferredLayout")), {})
        content = {key: content[key] for key in (
            "contentPreferredLayout", "highlightType", "framingEvidenceIds", "framingDecisionRevision", "framingReason",
        ) if key in content}
        for key, value in updates.items():
            setattr(clip, key, value)
        # The old preview is no longer a representation of the repaired framing.
        clip.preview_state = "stale"
        clip.preview_deferred = True
        clip.preview_video_url = clip.preview_spec_hash = None
        clip.live_preview_video_url = clip.live_preview_spec_hash = None
        append_choice(
            document.choice_history, kind="framing", clipId=clip.id, stage="applied", source="fallback",
            policyVersion=FRAMING_REPAIR_POLICY, inputRevision=str(document.render_revision),
            reason=("内容に基づく画角を選びましたが、完成検査のため全体表示に置換しました。 " if content else "")
            + f"automatic_framing_repair:{previous.get('reason', 'tracking_crop_containment_unverified')}",
            candidates=[ChoiceCandidate(
                id="original_crop", values={"resolvedLayout": previous.get("strategy")},
                outcome="rejected", reason=previous.get("reason"),
            )],
            values={"shortLayout": "blur_background", "resolvedLayout": "blur_background",
                    "framingOffsetX": 0, "framingOffsetY": 0, "framingZoom": 1, **content},
        )
    target_ids = {candidate.id for candidate in targets}
    selection.shorts = [
        candidate.model_copy(update=updates) if candidate.id in target_ids else candidate
        for candidate in selection.shorts
    ]
    indices = {candidate.id: index for index, candidate in enumerate(selection.shorts, 1)}
    repaired = render_shorts(
        selected_candidates=[candidate for candidate in selection.shorts if candidate.id in target_ids],
        output_indices=indices,
    )
    # Replacement files use the same unpublished paths. Never unlink them while
    # removing superseded rows; canonical published exports are not in result.
    for export in result.exports:
        if export.candidate_id in target_ids:
            db.delete(export)
    db.commit()
    combined = ShortRenderBatchResult(
        exports=sorted(
            [export for export in result.exports if export.candidate_id not in target_ids] + repaired.exports,
            key=lambda export: indices[export.candidate_id],
        ),
        failures=[*result.failures, *repaired.failures],
    )
    return combined, {
        "policy": FRAMING_REPAIR_POLICY, "maxAttempts": FRAMING_REPAIR_MAX_ATTEMPTS,
        "attemptedClipIds": [candidate.id for candidate in targets],
        "before": visual.model_dump(mode="json", by_alias=True),
        "replacementExportIds": [export.id for export in repaired.exports],
        "failedClipIds": [failure.candidate_id for failure in repaired.failures],
    }


def record_framing_recheck(decision: QualityGateDecision, repair: dict) -> None:
    check = next((check for check in decision.checks if check.code == VISUAL_CHECK), decision.checks[0])
    check.evidence["automaticFramingRepair"] = {
        **repair, "afterOutcome": check.outcome, "finalRoute": decision.route,
    }
