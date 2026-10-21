"""Independent attribute partitions, anchored to character and output format."""

import hashlib
import json

MIN_GROUP_VIDEOS = 5
FIRST7_METRICS = ("views", "averageViewPercentage", "averageViewDuration", "likes", "subscribersGained")
FIXED_DIMENSIONS = {
    "all": ["all"], "hook_scene": ["yes", "no"], "hook_text": ["yes", "no"],
    "title_intent": ["unknown"], "post_metadata_source": ["unknown"],
    "opening_score": ["unknown", "0-5", "5-10", "10-15", "out_of_range"],
}
DURATION_BANDS = {"short": ["<30", "30-45", "45-60", "60-75", ">75"],
                  "normal": ["<3min", "3-6min", "6-10min", "10-20min", ">=20min"]}


def group_id(character: str, format: str, dimension: str, value: str) -> str:
    key = json.dumps([character, format, dimension, value], ensure_ascii=False)
    return "aggregate:" + hashlib.sha256(key.encode()).hexdigest()[:24]


def attributes(record) -> dict[str, str]:
    seconds = record.bodyDurationSeconds
    if record.type == "short":
        duration = "<30" if seconds < 30 else "30-45" if seconds < 45 else "45-60" if seconds < 60 else "60-75" if seconds <= 75 else ">75"
    else:
        duration = ("<3min" if seconds < 180 else "3-6min" if seconds < 360 else "6-10min" if seconds < 600
                    else "10-20min" if seconds < 1200 else ">=20min")
    opening = record.selection.openingScore
    score = ("unknown" if opening is None else "out_of_range" if not 0 <= opening <= 15 else
             "0-5" if opening < 5 else "5-10" if opening < 10 else "10-15")
    return {"all": "all", "duration": duration,
            "hook_scene": "yes" if record.hookSceneStart is not None and record.hookSceneEnd is not None else "no",
            "hook_text": "yes" if (record.hookText or "").strip() else "no",
            "title_intent": record.titleCandidates.intent or "unknown",
            "post_metadata_source": record.postMetadataSource or "unknown", "opening_score": score}
