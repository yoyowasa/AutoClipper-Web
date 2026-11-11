"""Small bounded operational updates from 7-day (provisional) and 30-day (confirmed) observations, never generated code."""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, update
from app.intelligence.models import Channel, ProductionAggregate, ImprovementTrial
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion, ChoicePolicyDecision
from app.intelligence.choice_policy_schema import ChoicePolicyValues, changed_values, next_weight, IMPROVEMENT
from app.intelligence.choice_policy_evidence import policy_cohorts, compare, judge_version, option_change, PROVISIONAL_MIN_VIDEOS
from app.intelligence.choice_policy_corrections import scope_corrections, correction_candidate, SAMPLE_LIMIT
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


def evaluate_policy(db, head, cohorts, run, stamp, expiry, *, allow_update=True, corrections=()):
    current = db.get(ChoicePolicyVersion, head.current_id)
    events = list(db.scalars(select(ChoicePolicyDecision).where(ChoicePolicyDecision.policy_id == head.id)
                            .order_by(ChoicePolicyDecision.created_at.desc(), ChoicePolicyDecision.id.desc())))
    scope = [g for g in cohorts if (g["character_preset_name"], g["format"]) == (head.character, head.format)]
    last_update = next((e for e in events if e.action == "update" and e.to_id == current.id), None)
    stable_proof = None
    if current.previous_id:
        # One change at a time: the version in use is judged on its own videos before anything else moves.
        verdict, stable_proof = judge_version(scope, current.id)
        if verdict == "rollback":
            reason = "REGRESSION_30_DAY" if stable_proof["basis"] == "first30" else "REGRESSION_7_DAY"
            return decision(db, head, run.id, stamp, expiry, "rollback", reason, current.previous_id, stable_proof)
        if verdict == "pending":
            return decision(db, head, run.id, stamp, expiry, "hold", "VERSION_RESULT_PENDING",
                            evidence={"minimum": PROVISIONAL_MIN_VIDEOS})
    if not allow_update:
        return decision(db, head, run.id, stamp, expiry, "hold", "UPDATE_BUDGET_LIMIT")
    weights = ChoicePolicyValues.model_validate(current.values).weights
    candidates = []
    for before in scope:
        for after in scope:
            change = option_change(before, after)
            if not change or set(before["video_ids"]) & set(after["video_ids"]):
                continue
            result = compare(before, after)
            if not result or not result["before_median"] or result["after_median"] < result["before_median"] * IMPROVEMENT:
                continue
            key, target = change
            if key not in weights:
                continue
            value = next_weight(weights[key], target)
            if value == weights[key]:
                continue
            values = changed_values(current.values, key, value)
            basis = result["basis"]
            signature = hashlib.sha256(json.dumps(
                [key, basis, before[basis + "_views"], after[basis + "_views"]], sort_keys=True).encode()).hexdigest()
            if any((e.evidence and e.evidence.get("signature") == signature) or
                   (e.action == "rollback" and db.get(ChoicePolicyVersion, e.from_id).values == values) for e in events):
                continue
            ratio = result["after_median"] / result["before_median"]
            candidates.append(((basis != "first30", -ratio, key, after["id"]), key, before, after, values, signature, result))
    if not candidates:
        learned = learn_from_corrections(db, head, current, last_update, events, corrections, run, stamp, expiry)
        if learned is not None:
            return learned
        reason = "INSUFFICIENT_OR_UNCONFIRMED"
        return decision(db, head, run.id, stamp, expiry, "hold", "VERSION_NOT_WORSE" if stable_proof else reason,
                        evidence=stable_proof or {"groups": [g["id"] for g in scope], "minimum": PROVISIONAL_MIN_VIDEOS,
                            "cohorts": sorted(scope, key=lambda g: (-g["first7_count"], g["id"]))[:20],
                            "omitted_cohorts": max(0, len(scope) - 20)})
    _, key, before, after, values, signature, result = min(candidates, key=lambda item: item[0])
    version = ChoicePolicyVersion(id="policy_" + uuid4().hex, policy_id=head.id, previous_id=current.id, values=values, created_at=stamp)
    db.add(version)
    groups = set(before["group_ids"]) | set(after["group_ids"])
    hints = [ref["group_id"] for h in (run.review or {}).get("performance_hints", []) for ref in h["evidence_groups"]
             if ref["group_id"] in groups]
    trials = list(db.scalars(select(ImprovementTrial.id).where(ImprovementTrial.channel_id == run.channel_id,
        ImprovementTrial.baseline_video_id.in_(before["video_ids"]), ImprovementTrial.target_video_id.in_(after["video_ids"]))))
    confirmed = result["basis"] == "first30"
    return decision(db, head, run.id, stamp, expiry, "update",
        "OBSERVATIONAL_CRITERIA_MET" if confirmed else "PROVISIONAL_7_DAY_CRITERIA_MET", version.id,
        {"key": key, **result, "before": before, "after": after, "signature": signature,
         "hint_groups": hints, "trial_ids": trials, "eligibility": "operational_observation_only", "causal_effect": "unconfirmed"})


def learn_from_corrections(db, head, current, last_update, events, corrections, run, stamp, expiry):
    """Without a results comparison, the human's repeated corrections can still move one allowlisted weight."""
    since = last_update.created_at if last_update else None
    items = scope_corrections(corrections, head.character, head.format, since)
    weights = ChoicePolicyValues.model_validate(current.values).weights
    blocked = {e.evidence.get("signature") for e in events if e.evidence}
    found = correction_candidate(items, weights, blocked)
    if found is None:
        return None
    key, target, chosen, signature = found
    value = next_weight(weights[key], target)
    if value == weights[key]:
        return None
    values = changed_values(current.values, key, value)
    if any(e.action == "rollback" and db.get(ChoicePolicyVersion, e.from_id).values == values for e in events):
        return None
    version = ChoicePolicyVersion(id="policy_" + uuid4().hex, policy_id=head.id, previous_id=current.id, values=values, created_at=stamp)
    db.add(version)
    return decision(db, head, run.id, stamp, expiry, "update", "HUMAN_CORRECTIONS", version.id,
        {"source": "human_corrections", "key": key, "signature": signature, "count": len(chosen),
         "corrections": [{k: item[k] for k in ("record_id", "video_id", "kind", "role", "before", "after", "applied_at")}
                         for item in chosen[-SAMPLE_LIMIT:]],
         "eligibility": "operational_observation_only", "causal_effect": "unconfirmed"})


def update_choice_policies(db, run, stamp):
    db.execute(update(Channel).where(Channel.id == run.channel_id).values(id=Channel.id))
    aggregate = db.get(ProductionAggregate, run.channel_id)
    if not aggregate or aggregate.expires_at <= stamp or not run.review or run.review.get("goals") != GOALS:
        db.rollback()
        return []
    payload = aggregate.payload.get("choice_evaluations", {})
    cohorts = policy_cohorts(payload)
    corrections = payload.get("corrections", [])
    scopes = {(g["character_preset_name"], g["format"]) for g in cohorts}
    scopes |= {(c["character_preset_name"], c["format"]) for c in corrections if c["key"]}
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
        result = evaluate_policy(db, head, cohorts, run, stamp, aggregate.expires_at, allow_update=updates == 0,
                                 corrections=corrections)
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
