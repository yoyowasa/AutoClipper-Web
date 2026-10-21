"""Validate each hint against the actual derived groups, not Codex's counts."""

from collections import Counter
import re


def hint_issue(hint, groups, videos, counts: Counter) -> str | None:
    sentences = [part for part in re.split(r"[。！？!?]+", hint.text) if part.strip(' \n\t「」『』\"')]
    if not re.search(r"[ぁ-んァ-ヶ一-龠]", hint.text) or not 1 <= len(sentences) <= 2:
        return "HINT_TEXT_INVALID"
    ids = [ref.group_id for ref in hint.evidence_groups]
    if len(set(ids)) != len(ids) or any(id not in groups for id in ids):
        return "HINT_GROUP_UNKNOWN"
    sources = [groups[id] for id in ids]
    if any(not group["sufficient"] or group["count"] < 5 for group in sources):
        return "HINT_INSUFFICIENT_DATA"
    if any(ref.count != groups[ref.group_id]["count"] for ref in hint.evidence_groups):
        return "HINT_COUNT_MISMATCH"
    if any((group["character_preset_name"], group["format"]) != (hint.character_preset_name, hint.format) for group in sources):
        return "HINT_SCOPE_MISMATCH"
    allowed = set().union(*(group["video_ids"] for group in sources))
    if len(set(hint.video_ids)) != len(hint.video_ids) or not set(hint.video_ids) <= allowed:
        return "HINT_VIDEO_UNKNOWN"
    if any(video.get("title") and video["title"] in hint.text for video in videos.values()) or "http" in hint.text.lower():
        return "HINT_METADATA_QUOTED"
    key = (hint.character_preset_name, hint.format)
    if counts[key] >= 5:
        return "HINT_LIMIT_EXCEEDED"
    counts[key] += 1
    return None
