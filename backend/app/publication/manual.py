"""Explicit human restoration via the existing boundary-edit worker."""

from app.publication.evaluate import policy_for, evaluate_candidate
from app.publication.storage import record_choice


def restore_for_boundary(selection, clip_id):
    candidate = next((c for c in selection.deferred_candidates if c.id == clip_id), None)
    if candidate is None:
        return False
    collection = selection.normal_clips if candidate.type == "normal" else selection.shorts
    collection.append(candidate)
    selection.deferred_candidates = [c for c in selection.deferred_candidates if c.id != clip_id]
    return True


def record_manual_adoption(selection, document, candidate, *, settings, source_duration, silence_segments):
    from app.candidates.select_candidates import record_candidate_hard_gates

    # Explicit adoption replaces the model vote, not the physical/textual checks.
    candidate = candidate.model_copy(update={"should_use": True, "below_quality_threshold": False})
    checked, rejected = record_candidate_hard_gates([candidate], settings=settings, silence_segments=silence_segments)
    if rejected:
        raise ValueError("採用する範囲が既存の必須条件を満たしていません。範囲・字幕の根拠を確認してください。")
    candidate = checked[0]
    policy = policy_for(settings)
    old = next(d for d in selection.publication_decisions if d.candidate_id == candidate.id)
    decision = evaluate_candidate(candidate, policy=policy, settings=settings, source_duration=source_duration, manual=True)
    if decision.decision != "publish":
        raise ValueError("採用する範囲が尺・元動画の条件に合っていません。")
    decision.reasons = ["MANUAL_OVERRIDE"]
    decision.original_decision = old.original_decision or old.decision
    selection.publication_decisions = [decision if d.candidate_id == candidate.id else d for d in selection.publication_decisions]
    document.publication_decisions = selection.publication_decisions
    next(c for c in document.clips if c.id == candidate.id).publication_decision = "publish"
    kind = old.type
    selection.publication_withheld_counts[kind] = max(0, selection.publication_withheld_counts.get(kind, 0) - 1)
    record_choice(selection, decision)
    document.choice_history = selection.choice_history
    from app.publication.pipeline import refresh_publication_counts

    refresh_publication_counts(selection, settings)
    return candidate
