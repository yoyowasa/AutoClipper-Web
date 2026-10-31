"""Deterministic decisions using existing textual evidence, never new AV inference."""

import math
import unicodedata
from app.duration_rules import selection_duration_rejection, effective_short_max
from app.intelligence.performance_hints import active_hint_uses
from app.production_choices import value_hash
from app.publication.models import PublicationDecision, PublicationEvidence, PublicationPolicy, POLICY_SETTING, HintReference

MANUAL_REASONS = {"manual_time_range", "manual_edit"}


def policy_for(settings):
    if settings.get("workflowMode") == "manual" or POLICY_SETTING not in settings:
        return None
    return PublicationPolicy.model_validate(settings[POLICY_SETTING])


def evaluate_candidate(candidate, *, policy, settings, source_duration, manual=False):
    evidence = PublicationEvidence(
        selectionReason=candidate.selection_reason,
        selectionRationale=candidate.reason,
        hardGatePassed=candidate.hard_gate_passed,
        hardGateReasons=list(candidate.hard_gate_evidence.get("reasons", [])),
        hardGateHash=value_hash(candidate.hard_gate_evidence),
    )
    for attr in ("final_score", "ai_score", "rule_score"):
        score = getattr(candidate, attr)
        if score is not None and math.isfinite(score):
            evidence.score, evidence.score_source = score, attr
            break
    text = unicodedata.normalize("NFKC", candidate.transcript_text or "")
    count = sum(c.isalnum() for c in text)
    evidence.transcript_characters = count
    evidence.characters_per_second = count / candidate.duration if candidate.duration > 0 else None
    evidence.transcript_hash = value_hash(text)
    evidence.hint_references = (
        [
            HintReference(**{key: hint[key] for key in ("analysisId", "generatedAt", "expiresAt")})
            for hint in active_hint_uses(settings.get("_performanceHints"), target="selection", format=candidate.type)
        ]
        if settings.get("usePerformanceHints", True)
        else []
    )
    is_manual = manual or candidate.selection_reason in MANUAL_REASONS or bool(candidate.clip_plan_boundary_adjusted)
    invalid = (
        candidate.start < 0
        or candidate.end > source_duration + 0.001
        or candidate.end <= candidate.start
        or abs(candidate.duration - (candidate.end - candidate.start)) > 0.001
        or selection_duration_rejection(
            candidate.type,
            candidate.duration,
            short_max=effective_short_max(settings),
            longform_reason=candidate.longform_reason,
            manual=is_manual,
        )
    )
    reasons, decision = [], "unknown"
    if invalid:
        reasons = ["RANGE_INVALID"]
    elif is_manual:
        decision, reasons = "publish", ["MANUAL_SELECTION"]
    elif not count:
        reasons = ["TRANSCRIPT_MISSING"]
    elif candidate.hard_gate_passed is None:
        reasons = ["QUALITY_EVIDENCE_MISSING"]
    elif candidate.hard_gate_passed is False and (not evidence.hard_gate_reasons or set(evidence.hard_gate_reasons) - {"model_rejected"}):
        reasons = ["EXISTING_GATE_REJECTED"]
    elif evidence.score is None:
        reasons = ["SCORE_MISSING"]
    elif not candidate.selection_reason:
        reasons = ["SELECTION_REASON_MISSING"]
    else:
        if evidence.score < policy.min_score:
            reasons.append("WEAK_SCORE")
        if evidence.characters_per_second < policy.min_characters_per_second:
            reasons.append("LOW_CONTENT_DENSITY")
        if candidate.should_use is False or candidate.below_quality_threshold is True:
            reasons.append("MODEL_REJECTED")
        decision = "skip" if reasons else "publish"
        reasons = reasons or ["CRITERIA_MET"]
    return PublicationDecision(
        candidateId=candidate.id,
        type=candidate.type,
        start=candidate.start,
        end=candidate.end,
        title=candidate.title or ("通常" if candidate.type == "normal" else "ショート"),
        decision=decision,
        source="manual" if is_manual else "automatic",
        policyVersion=policy.version,
        reasons=reasons,
        evidence=evidence,
    )
