"""Frozen job-local settings. No policy is generated or looked up in render loops."""
from sqlalchemy import select
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion
from app.intelligence.choice_policy_schema import ChoicePolicyValues, DEFAULT_WEIGHTS
from app.intelligence.models import ChannelConnection, Channel
from app.intelligence.production_catalog import normalize_title

SETTING = "_choicePolicies"


def freeze_job_policy(db, job):
    settings = dict(job.settings_json or {})
    if not settings.get("_choicePolicyEligible") or SETTING in settings:
        return
    policies, reasons = {}, {}
    if (settings.get("automationMode") == "auto" and settings.get("workflowMode") != "manual"
            and settings.get("usePerformanceHints", True)):
        heads = list(db.scalars(select(ChoicePolicyHead).join(ChannelConnection,
            ChannelConnection.channel_id == ChoicePolicyHead.channel_id).where(
                ChoicePolicyHead.character == settings.get("characterPresetName", ""), ChannelConnection.status == "connected")))
        for format in ("normal", "short"):
            matches = [h for h in heads if h.format == format]
            channel = normalize_title(settings.get("channelName"))
            if channel:
                matches = [h for h in matches if normalize_title(db.get(Channel, h.channel_id).name) == channel]
            if len(matches) == 1:
                version = db.get(ChoicePolicyVersion, matches[0].current_id)
                policies[format] = {"id": version.id, "channelId": matches[0].channel_id,
                                    **ChoicePolicyValues.model_validate(version.values).model_dump()}
            else:
                reasons[format] = "CHANNEL_AMBIGUOUS" if len(matches) > 1 else "NO_MATCHING_POLICY"
    else:
        reasons["all"] = "LEARNING_DISABLED" if not settings.get("usePerformanceHints", True) else "WORKFLOW_NOT_ELIGIBLE"
    job.settings_json = {**settings, SETTING: policies, "_choicePolicyReasons": reasons}
    db.commit()


def frozen_policy(settings, format):
    raw = settings.get(SETTING, {}).get(format)
    if not raw:
        return None
    values = ChoicePolicyValues.model_validate({"weights": raw["weights"]})
    return {"id": raw["id"], "weights": values.weights}


def weight(settings, format, key):
    policy = frozen_policy(settings, format)
    return policy["weights"][key] if policy else DEFAULT_WEIGHTS[key]


def inherit_rendered_policy_evidence(history, settings, *, clip_id, format):
    """Carry proven applied choices into matching renderer observations, never guess."""
    policy = frozen_policy(settings, format)
    if not policy:
        return
    for published in history:
        if (published.clipId != clip_id or published.stage != "published"
                or (published.policyVersion or "").startswith("policy_") and published.policyVersion != policy["id"]
                or (published.implementationVersion or published.policyVersion) != "existing-render-decisions-v1"):
            continue
        applied = [c for c in history if c.clipId == clip_id and c.kind == published.kind and c.stage == "applied"
                   and c.recordedAt <= published.recordedAt]
        if not applied:
            continue
        original = max(applied, key=lambda c: (c.recordedAt, c.id))
        if published.kind == "effects":
            if original.values.get("subtitleStyles", []) != published.values.get("subtitleStyles", []):
                continue
            for key in ("emphasisSignal", "emphasisTopicWeight", "emphasisNumberWeight", "emphasisReactionWeight"):
                if key in original.values:
                    published.values[key] = original.values[key]
            published.source = original.source
            published.implementationVersion = original.implementationVersion or original.policyVersion
        elif published.kind == "framing" and published.source != "fallback" and original.source in {"manual", "fallback"}:
            keys = ("shortLayout", "framingOffsetX", "framingOffsetY", "framingZoom")
            if all(published.values.get(k) == original.values.get(k) for k in keys):
                published.source = original.source
                published.policyVersion = original.policyVersion
                published.implementationVersion = original.implementationVersion


def record_policy_choices(history, settings, *, clip_id=None, format=None, counts=None):
    for choice in history:
        if choice.kind not in {"range", "title_hook", "framing", "text_style", "effects"}:
            continue
        if clip_id is not None and choice.clipId != clip_id:
            continue
        if choice.source not in {"automatic", "fallback"}:
            continue
        kind = format or choice.values.get("type")
        policy = frozen_policy(settings, kind) if kind in {"normal", "short"} else None
        if policy:
            if (choice.policyVersion or "").startswith("policy_") and choice.policyVersion != policy["id"]:
                continue
            if choice.policyVersion and not choice.policyVersion.startswith("policy_"):
                choice.implementationVersion = choice.implementationVersion or choice.policyVersion
            choice.policyVersion = policy["id"]
            if choice.kind == "range":
                choice.values.update(openingRankWeight=weight(settings, kind, "ranking.opening"),
                    audienceFamiliarity=settings.get("audienceFamiliarity", "known"),
                    allocationNormalWeight=weight(settings, kind, "allocation.normal"),
                    allocationShortWeight=weight(settings, kind, "allocation.short"))
                if counts and sum(counts.values()):
                    choice.values["allocationShare"] = round(counts.get(kind, 0) / sum(counts.values()), 6)


def choose_title_suggestion(artifact, settings, format):
    if not frozen_policy(settings, format):
        return artifact.recommended_suggestion_id
    ranked = sorted(artifact.suggestions, key=lambda item: (
        -weight(settings, format, f"title_hook.{item.intent}") if item.intent in {"factual", "engagement", "concise"} else -1,
        item.id != artifact.recommended_suggestion_id, item.id))
    return ranked[0].id
