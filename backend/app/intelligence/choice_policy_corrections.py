"""Learning from the human's own corrections, within the same bounded allowlist and steps."""
import hashlib
import json
from datetime import datetime
from statistics import median

from app.intelligence.choice_policy_schema import REGRESSION
from app.intelligence.production_dimensions import MIN_GROUP_VIDEOS

MIN_CORRECTION_RECORDS = MIN_GROUP_VIDEOS
SAMPLE_LIMIT = 20


def scope_corrections(corrections, character, format, since: datetime | None):
    """Mappable corrections for one character/format, newer than the last applied update."""
    return [item for item in corrections
            if (item["character_preset_name"], item["format"]) == (character, format) and item["key"]
            and (since is None or datetime.fromisoformat(item["applied_at"]) > since)]


def correction_candidate(items, weights, blocked):
    """The allowlisted option that most distinct recent records were corrected toward, at least five."""
    records = {}
    for item in items:
        records.setdefault((item["key"], item["target"]), {})[item["record_id"]] = item
    ranked = sorted(records.items(), key=lambda entry: (-len(entry[1]), entry[0][0], str(entry[0][1])))
    for (key, target), by_record in ranked:
        if len(by_record) < MIN_CORRECTION_RECORDS or key not in weights:
            continue
        chosen = sorted(by_record.values(), key=lambda item: (item["applied_at"], item["record_id"]))
        signature = hashlib.sha256(json.dumps(
            ["corrections", key, target, sorted(by_record)], ensure_ascii=False).encode()).hexdigest()
        if signature in blocked:
            continue
        return key, target, chosen, signature
    return None


def judge_correction_version(scope, current_id):
    """30-day views of videos made under this version against those made under any other version."""
    after, before = {}, {}
    for cohort in scope:
        if cohort["source"] not in ("automatic", "manual", "fallback") or cohort["band"] == "unknown":
            continue
        (after if cohort["policy_version"] == current_id else before).update(cohort["video_views"])
    if len(after) < MIN_GROUP_VIDEOS or len(before) < MIN_GROUP_VIDEOS:
        return "pending", None
    proof = {"before_count": len(before), "after_count": len(after),
             "before_median": median(before.values()), "after_median": median(after.values()),
             "eligibility": "operational_observation_only"}
    if proof["after_median"] <= proof["before_median"] * REGRESSION:
        return "rollback", proof
    return "stable", proof
