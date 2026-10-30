"""Filter already selected finalists once; never refill or relax existing gates."""

from collections import Counter
from app.publication.evaluate import policy_for, evaluate_candidate
from app.publication.storage import record_choice, persist_report, report_outcome, read_report


def apply_publication_decisions(selection, scored, *, settings, paths, job_id, source_duration, silence_segments=()):
    policy = policy_for(settings)
    if policy is None:
        return selection
    original = [*selection.normal_clips, *selection.shorts]
    candidates = original
    # Account for score-only rejects within the remaining requested slots. These
    # are decision evidence, never replacement outputs or a relaxed quality gate.
    reasons_by_id = {}
    for rejection in selection.rejected_candidates:
        reasons_by_id.setdefault(rejection.candidate_id, set()).update(rejection.reasons)
    ids = {id for id, reasons in reasons_by_id.items() if reasons and reasons <= {"low_final_score"}}
    ranked = sorted(
        (c for c in scored if c.id in ids and c.id not in {x.id for x in original}),
        key=lambda c: (
            -(c.final_score if c.final_score is not None else c.ai_score if c.ai_score is not None else c.rule_score or 0),
            c.id,
        ),
    )
    total = settings.get("totalClipCount")
    weak = []
    for kind, key in (("normal", "normalClipCount"), ("short", "shortCount")):
        limit = int(total if total is not None else settings.get(key, 0)) - sum(c.type == kind for c in original)
        weak.extend([c for c in ranked if c.type == kind][: max(0, limit)])
    if total is not None:
        weak = weak[: max(0, int(total) - len(original))]
    if weak:
        from app.candidates.select_candidates import record_candidate_hard_gates

        weak, _ = record_candidate_hard_gates(weak, settings=settings, silence_segments=silence_segments)
        candidates = [*original, *[c.model_copy(update={"below_quality_threshold": True}) for c in weak]]
    if not candidates:
        return selection
    previous = read_report(paths, job_id)
    prior = {d.candidate_id: d for d in previous.decisions} if previous else {}
    decisions = []
    for c in candidates:
        decision = evaluate_candidate(
            c, policy=policy, settings=settings, source_duration=source_duration, manual=c.id in settings.get("keptClipIds", [])
        )
        old = prior.get(c.id)
        if old and decision.source == "manual" and old.decision != "publish":
            decision.original_decision = old.original_decision or old.decision
            decision.reasons = ["MANUAL_OVERRIDE"]
        if (
            old
            and old.source == "manual"
            and old.type == c.type
            and (old.start, old.end) == (c.start, c.end)
            and decision.decision == "publish"
        ):
            decision = old
        decisions.append(decision)
        record_choice(selection, decision)
    decided = {d.candidate_id: d for d in decisions}
    selected = [c for c in candidates if decided[c.id].decision == "publish"]
    held = [c for c in candidates if decided[c.id].decision != "publish"]
    removed = Counter(c.type for c in held)
    selection = selection.model_copy(
        update={
            "normal_clips": [c for c in selected if c.type == "normal"],
            "shorts": [c for c in selected if c.type == "short"],
            "publication_decisions": decisions,
            "deferred_candidates": held,
            "publication_withheld_counts": dict(removed),
        }
    )
    refresh_publication_counts(selection, settings)
    persist_report(paths, job_id, selection, policy)
    return selection


def finish_without_publication(db, job, paths, selection, settings, source_duration):
    if not selection.publication_decisions or report_outcome(selection) != "no_publication":
        return False
    from app.jobs.clip_plan import build_clip_plan, mark_clip_plan_awaiting_review, write_clip_plan, clip_plan_output_path

    plan = build_clip_plan(job.id, selection, settings, source_duration=source_duration)
    mark_clip_plan_awaiting_review(plan, preview_clip_ids=[])
    write_clip_plan(plan, clip_plan_output_path(paths.job_outputs(job.id)))
    job.status, job.progress, job.current_step = "completed", 100, "投稿なし（素材が弱いため見送り）"
    job.error_code = job.error_message = None
    db.commit()
    return True


def refresh_publication_counts(selection, settings):
    selected = [*selection.normal_clips, *selection.shorts]
    counts = Counter(c.type for c in selected)
    reasons = {key: value for key, value in selection.shortfall_reasons.items() if key not in {"weak_material_skip", "publication_unknown"}}
    for outcome, key in (("skip", "weak_material_skip"), ("unknown", "publication_unknown")):
        count = sum(d.decision == outcome for d in selection.publication_decisions)
        if count:
            reasons[key] = count
    selection.selected_above_threshold_count = sum(c.below_quality_threshold is not True for c in selected)
    selection.selected_below_threshold_backfill_count = sum(c.below_quality_threshold is True for c in selected)
    selection.shortfall_reasons = reasons
    if selection.requested_total is not None:
        if "insufficient_strong_candidates" in reasons:
            remaining = max(0, selection.requested_total - len(selected) - len(selection.deferred_candidates))
            if remaining:
                reasons["insufficient_strong_candidates"] = remaining
            else:
                reasons.pop("insufficient_strong_candidates")
        selection.selected_total = len(selected)
        selection.selected_by_type = {k: counts[k] for k in ("normal", "short")}
        selection.minimum_shortfall = {
            k: max(0, int(settings.get(key, 0)) - counts[k]) for k, key in (("normal", "minNormalClipCount"), ("short", "minShortCount"))
        }
        selection.unfilled_requested_counts = {"total": max(0, selection.requested_total - len(selected)), **selection.minimum_shortfall}

    else:
        selection.unfilled_requested_counts = {
            kind: max(0, int(settings.get(key, 0)) - counts[kind]) for kind, key in (("normal", "normalClipCount"), ("short", "shortCount"))
        }


def include_codex_weak_evidence(selection, scored, weak_candidates, settings):
    """Do not select weak Codex proposals; keep their validated evidence for a zero result."""
    if policy_for(settings) is None or not weak_candidates:
        return selection, scored
    from app.candidates.select_candidates import CandidateRejection

    selection = selection.model_copy(
        update={
            "rejected_candidates": [
                *selection.rejected_candidates,
                *[CandidateRejection(candidateId=c.id, type=c.type, reasons=["low_final_score"]) for c in weak_candidates],
            ]
        }
    )
    return selection, [*scored, *weak_candidates]
