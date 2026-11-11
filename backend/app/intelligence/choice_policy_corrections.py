"""Learning from the human's own corrections, within the same bounded allowlist and steps."""
import hashlib
import json
from datetime import datetime

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

