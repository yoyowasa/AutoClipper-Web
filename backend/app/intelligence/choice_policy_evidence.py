"""Recorded options against fixed-age results; eligibility is not causal confirmation."""
import hashlib
import json
from statistics import median
from app.intelligence.choice_policy_schema import FRAMING_OPTIONS, INTENTS, REGRESSION
from app.intelligence.production_dimensions import MIN_GROUP_VIDEOS

# Provisional on first-7-day views with three videos; confirmed on first-30-day views with five.
PROVISIONAL_MIN_VIDEOS = 3
BASES = (("first30", MIN_GROUP_VIDEOS), ("first7", PROVISIONAL_MIN_VIDEOS))
JUDGED = {"reached", "below_target"}


def policy_cohorts(payload):
    """One cohort per character, format, item and recorded option value.

    Duration band, provenance and the version a video was made under do not split a cohort;
    they stay attached as attributes. A missing view count is left out, never counted as zero.
    """
    merged = {}
    for group in payload.get("groups", []):
        key = [group[k] for k in ("character_preset_name", "format", "kind", "role")] + [
            json.dumps(group["option_values"], ensure_ascii=False, sort_keys=True)]
        id = "options:" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:24]
        item = merged.setdefault(id, {"id": id, **{k: group[k] for k in (
            "character_preset_name", "format", "kind", "role", "option_values")},
            "group_ids": [], "sources": set(), "rows": {}, "versions": {}})
        item["group_ids"].append(group["id"])
        item["sources"].add(group["source"])
        for row in group["observations"]:
            item["rows"][row["video_id"]] = row
            item["versions"][row["video_id"]] = group["policy_version"]
    result = []
    for item in merged.values():
        rows, sources = item.pop("rows"), item.pop("sources")
        judged = {id: r for id, r in rows.items() if r["evaluation"]["status"] in JUDGED}
        first30 = {id: r["evaluation"]["first30"]["metrics"]["views"]["value"] for id, r in judged.items()}
        first7 = {id: r["evaluation"]["first7"]["metrics"]["views"]["value"] for id, r in rows.items()
                  if r["evaluation"]["first7"]["metrics"]["views"]["value"] is not None}
        result.append(item | {
            "group_ids": sorted(item["group_ids"]), "source": next(iter(sources)) if len(sources) == 1 else "mixed",
            "count": len(first30), "total_count": len(rows), "median": median(first30.values()) if first30 else None,
            "rate": sum(r["evaluation"]["status"] == "reached" for r in judged.values()) / len(judged) if judged else None,
            "first30_views": first30, "first7_views": first7,
            "first7_count": len(first7), "first7_median": median(first7.values()) if first7 else None,
            "video_ids": sorted(first30.keys() | first7.keys()),
            "observed_at": max((r["evaluation"]["first30"]["observedAt"] for r in judged.values()), default=None),
            "evidence_ids": sorted({id for r in judged.values() for id in r["evaluation"]["evidence_ids"]})})
    return sorted(result, key=lambda g: g["id"])


def compare(before, after):
    """Median views of two cohorts on the firmest basis both can support, or None while either is too small."""
    for basis, minimum in BASES:
        old, new = before[basis + "_views"], after[basis + "_views"]
        if len(old) >= minimum and len(new) >= minimum:
            return {"basis": basis, "before_count": len(old), "after_count": len(new),
                    "before_median": median(old.values()), "after_median": median(new.values())}
    return None


def judge_version(scope, current_id):
    """Videos made under this version against all other videos of the same character and format."""
    made = {id for cohort in scope for id, version in cohort["versions"].items() if version == current_id}
    for basis, minimum in BASES:
        views = {id: value for cohort in scope for id, value in cohort[basis + "_views"].items()}
        after = {id: value for id, value in views.items() if id in made}
        before = {id: value for id, value in views.items() if id not in made}
        if len(after) < minimum or len(before) < minimum:
            continue
        proof = {"basis": basis, "before_count": len(before), "after_count": len(after),
                 "before_median": median(before.values()), "after_median": median(after.values()),
                 "eligibility": "operational_observation_only"}
        if proof["after_median"] <= proof["before_median"] * REGRESSION:
            return "rollback", proof
        return "stable", proof
    return "pending", None


def option_change(before, after):
    """Only observed existing choices can nominate one allowlisted priority."""
    if (before["kind"], before["role"]) != (after["kind"], after["role"]):
        return None
    a, b = before["option_values"], after["option_values"]
    differences = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    kind, role = after["kind"], after["role"]
    if kind == "range" and differences == {"openingBand"}:
        bands = ("0-5", "5-10", "10-15")
        if (a.get("openingBand") in bands and b.get("openingBand") in bands and after["format"] == "short"
                and a.get("audienceFamiliarity") == "unknown"):
            return "ranking.opening", None if bands.index(b["openingBand"]) > bands.index(a["openingBand"]) else .5
    if kind == "range" and differences == {"allocationShare"}:
        return f"allocation.{after['format']}", None if b["allocationShare"] > a["allocationShare"] else .5
    if kind == "effects" and differences == {"emphasisSignal"} and b.get("emphasisSignal") in {"topic", "number", "reaction"}:
        return f"effects.{b['emphasisSignal']}", None
    if kind == "framing" and differences <= {"resolvedLayout", "shortLayout"}:
        option = b.get("resolvedLayout") or b.get("shortLayout")
        return (f"framing.{option}", None) if option in FRAMING_OPTIONS else None
    if kind == "title_hook" and differences == {"intent"} and b.get("intent") in INTENTS:
        return (f"title_hook.{b['intent']}", None)
    if kind == "text_style" and differences == {"bold"} and isinstance(b.get("bold"), bool):
        return (f"text_style.{role.removesuffix('Style')}.{'bold' if b['bold'] else 'regular'}", None)
    numeric = {"openingRankWeight": "ranking.opening", "allocationNormalWeight": "allocation.normal",
               "allocationShortWeight": "allocation.short", "emphasisTopicWeight": "effects.topic",
               "emphasisNumberWeight": "effects.number", "emphasisReactionWeight": "effects.reaction"}
    if len(differences) == 1:
        key = next(iter(differences))
        if key == "openingRankWeight" and a.get("audienceFamiliarity") != "unknown":
            return None
        expected_kind = "effects" if key.startswith("emphasis") else "range"
        if key in numeric and kind == expected_kind and isinstance(b.get(key), (float, int)) and not isinstance(b[key], bool):
            return numeric[key], b[key]
    return None
