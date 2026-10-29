"""Small bounded operational updates from 30-day observations, never generated code."""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, update
from app.intelligence.models import Channel, ProductionAggregate, ImprovementTrial
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion, ChoicePolicyDecision
from app.intelligence.choice_policy_schema import ChoicePolicyValues, changed_values, IMPROVEMENT, REGRESSION
from app.intelligence.choice_policy_evidence import policy_cohorts, pure, option_change
from app.intelligence.production_dimensions import MIN_GROUP_VIDEOS
from app.intelligence.evaluation_rules import GOALS


def identity(channel_id, character, format):
    return hashlib.sha256(json.dumps([channel_id, character, format], ensure_ascii=False).encode()).hexdigest()


def decision(db, head, analysis_id, stamp, expiry, action, reason, to_id=None, evidence=None):
    row = ChoicePolicyDecision(id="decision_" + uuid4().hex, policy_id=head.id, analysis_id=analysis_id,
        action=action, reason=reason, from_id=head.current_id, to_id=to_id or head.current_id,
        evidence=evidence or {}, evidence_expires_at=expiry, created_at=stamp)
    db.add(row)
    if to_id:
        head.current_id = to_id
    return row


def evaluate_policy(db, head, cohorts, run, stamp, expiry, *, allow_update=True):
    current = db.get(ChoicePolicyVersion, head.current_id)
    events = list(db.scalars(select(ChoicePolicyDecision).where(ChoicePolicyDecision.policy_id == head.id)
                            .order_by(ChoicePolicyDecision.created_at.desc(), ChoicePolicyDecision.id.desc())))
    scope = [g for g in cohorts if (g["character_preset_name"], g["format"]) == (head.character, head.format)]
    last_update = next((e for e in events if e.action == "update" and e.to_id == current.id), None)
    stable_proof = None
    if current.previous_id and last_update:
        if not last_update.evidence or last_update.evidence_expires_at <= stamp:
            return decision(db, head, run.id, stamp, expiry, "hold", "EVIDENCE_EXPIRED")
        reference = last_update.evidence["before"]
        baseline = next((g for g in scope if (g["id"], g["band"]) == (reference["id"], reference["band"])), None)
        fresh = [g for g in scope if g["policy_version"] == current.id and
                 (g["kind"], g["role"], g["band"], g["implementation_version"]) ==
                 (reference["kind"], reference["role"], reference["band"], reference["implementation_version"])]
        judged = [g for g in fresh if pure(g, MIN_GROUP_VIDEOS)]
        if baseline and pure(baseline, MIN_GROUP_VIDEOS) and judged:
            observed = sorted(judged, key=lambda g: (-g["count"], g["id"]))[0]
            proof = {"before": baseline, "after": observed, "eligibility": "operational_observation_only"}
            if observed["median"] <= baseline["median"] * REGRESSION:
                return decision(db, head, run.id, stamp, expiry, "rollback", "REGRESSION_30_DAY", current.previous_id, proof)
            stable_proof = proof
        early = [g for g in fresh if g["source"] == "automatic" and not g["mixed"] and g["first7_count"] >= MIN_GROUP_VIDEOS]
        warning = bool(baseline and baseline["first7_count"] >= MIN_GROUP_VIDEOS and early and
                       min(g["first7_median"] for g in early) < baseline["first7_median"] * REGRESSION)
        if stable_proof is None:
            return decision(db, head, run.id, stamp, expiry, "warning" if warning else "hold",
                            "EARLY_7_DAY_DECLINE" if warning else "VERSION_30_DAY_PENDING",
                            evidence={"before": baseline, "after": early[0] if early else None})
        scope = [g for g in scope if g["policy_version"] == current.id]
    if not allow_update:
        return decision(db, head, run.id, stamp, expiry, "hold", "UPDATE_BUDGET_LIMIT")
    candidates = []
    for before in scope:
        for after in scope:
            if (before["band"], before["policy_version"], before["implementation_version"]) != (
                    after["band"], after["policy_version"], after["implementation_version"]):
                continue
            if not pure(before, MIN_GROUP_VIDEOS) or not pure(after, MIN_GROUP_VIDEOS):
                continue
            if set(before["video_ids"]) & set(after["video_ids"]):
                continue
            change = option_change(before, after)
            if not change or not before["median"] or after["median"] < before["median"] * IMPROVEMENT or after["rate"] < before["rate"]:
                continue
            key, target = change
            weights = ChoicePolicyValues.model_validate(current.values).weights
            if key not in weights:
                continue
            old = weights[key]
            value = min(2.0, round(old * 1.1, 8)) if target is None or target > old else max(.5, round(old * .9, 8))
            if target is not None:
                value = min(value, target) if target > old else max(value, target)
            if value == old:
                continue
            values = changed_values(current.values, key, value)
            signature = hashlib.sha256(json.dumps([before, after, key], sort_keys=True).encode()).hexdigest()
            if any((e.evidence and e.evidence.get("signature") == signature) or
                   (e.action == "rollback" and db.get(ChoicePolicyVersion, e.from_id).values == values) for e in events):
                continue
            candidates.append((-(after["median"] / before["median"]), key, after["id"], before, after, values, signature))
    if not candidates:
        reason = "MIXED_PROVENANCE" if any(g["mixed"] for g in scope) else "INSUFFICIENT_OR_UNCONFIRMED"
        return decision(db, head, run.id, stamp, expiry, "hold", "VERSION_NOT_WORSE" if stable_proof else reason,
                        evidence=stable_proof or {"groups": [g["id"] for g in scope], "minimum": MIN_GROUP_VIDEOS,
                            "cohorts": sorted(scope, key=lambda g: (-g["count"], g["id"]))[:20],
                            "omitted_cohorts": max(0, len(scope) - 20)})
    _, key, _, before, after, values, signature = min(candidates, key=lambda item: item[:3])
    version = ChoicePolicyVersion(id="policy_" + uuid4().hex, policy_id=head.id, previous_id=current.id, values=values, created_at=stamp)
    db.add(version)
    hints = [ref["group_id"] for h in (run.review or {}).get("performance_hints", []) for ref in h["evidence_groups"]
             if ref["group_id"] in {before["id"], after["id"]}]
    trials = list(db.scalars(select(ImprovementTrial.id).where(ImprovementTrial.channel_id == run.channel_id,
        ImprovementTrial.baseline_video_id.in_(before["video_ids"]), ImprovementTrial.target_video_id.in_(after["video_ids"]))))
    return decision(db, head, run.id, stamp, expiry, "update", "OBSERVATIONAL_CRITERIA_MET", version.id,
        {"key": key, "before": before, "after": after, "signature": signature,
         "hint_groups": hints, "trial_ids": trials, "eligibility": "operational_observation_only", "causal_effect": "unconfirmed"})


def update_choice_policies(db, run, stamp):
    db.execute(update(Channel).where(Channel.id == run.channel_id).values(id=Channel.id))
    aggregate = db.get(ProductionAggregate, run.channel_id)
    if not aggregate or aggregate.expires_at <= stamp or not run.review or run.review.get("goals") != GOALS:
        db.rollback()
        return []
    payload = aggregate.payload.get("choice_evaluations", {})
    cohorts = policy_cohorts(db, payload, run.channel_id)
    scopes = {(g["character_preset_name"], g["format"]) for g in cohorts}
    scopes |= {(h.character, h.format) for h in db.scalars(select(ChoicePolicyHead).where(ChoicePolicyHead.channel_id == run.channel_id))}
    if not scopes:
        scopes = {("未設定", "normal"), ("未設定", "short")}
    results, updates = [], 0
    for character, format in sorted(scopes):
        key = identity(run.channel_id, character, format)
        if db.scalar(select(ChoicePolicyDecision.id).where(
                ChoicePolicyDecision.policy_id == key, ChoicePolicyDecision.analysis_id == run.id)):
            continue
        head = db.get(ChoicePolicyHead, key, populate_existing=True)
        if head is None:
            head = ChoicePolicyHead(id=key, channel_id=run.channel_id, character=character, format=format,
                                    current_id="policy_" + uuid4().hex)
            db.add(head)
            db.flush()
            db.add(ChoicePolicyVersion(id=head.current_id, policy_id=key, values=ChoicePolicyValues().model_dump(), created_at=stamp))
            db.flush()
        result = evaluate_policy(db, head, cohorts, run, stamp, aggregate.expires_at, allow_update=updates == 0)
        results.append(result)
        updates += result.action == "update"
    db.commit()
    return results


def record_policy_failure(db, run, stamp):
    from datetime import timedelta
    db.execute(update(Channel).where(Channel.id == run.channel_id).values(id=Channel.id))
    heads = list(db.scalars(select(ChoicePolicyHead).where(ChoicePolicyHead.channel_id == run.channel_id)))
    if not heads:
        for format in ("normal", "short"):
            head = ChoicePolicyHead(id=identity(run.channel_id, "未設定", format), channel_id=run.channel_id,
                character="未設定", format=format, current_id="policy_" + uuid4().hex)
            db.add(head)
            db.flush()
            db.add(ChoicePolicyVersion(id=head.current_id, policy_id=head.id, values=ChoicePolicyValues().model_dump(), created_at=stamp))
            heads.append(head)
    for head in heads:
        if not db.scalar(select(ChoicePolicyDecision.id).where(
                ChoicePolicyDecision.policy_id == head.id, ChoicePolicyDecision.analysis_id == run.id)):
            decision(db, head, run.id, stamp, stamp + timedelta(days=30), "hold", "EVALUATION_FAILED")
    db.commit()
