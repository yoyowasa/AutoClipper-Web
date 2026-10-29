"""Equal-age, equal-band observations; eligibility is not causal confirmation."""
from collections import defaultdict
from statistics import median
from sqlalchemy import select
from app.intelligence.models import YouTubeVideo
from app.intelligence.dashboard_reports import duration_band
from app.intelligence.choice_policy_schema import FRAMING_OPTIONS, INTENTS


def policy_cohorts(db, payload, channel_id):
    videos = {v.id: v for v in db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id))}
    controlled = {"range", "title_hook", "framing", "text_style", "effects"}
    mixed = {o["video_id"] for g in payload.get("groups", []) if g["kind"] != "publication"
             for o in g["observations"] if o["source"] == "manual" or
             o["source"] == "unrecorded" and g["kind"] in controlled}
    result = []
    for group in payload.get("groups", []):
        by_band = defaultdict(dict)
        for row in group["observations"]:
            video = videos.get(row["video_id"])
            if video is not None:
                band = duration_band(video.duration_seconds, video.format)
                by_band[band][video.id] = row
        for band, observations in by_band.items():
            all_rows = list(observations.values())
            rows = [r for r in all_rows if r["evaluation"]["status"] in {"reached", "below_target"}]
            values = [r["evaluation"]["first30"]["metrics"]["views"]["value"] for r in rows]
            first7 = [r["evaluation"]["first7"]["metrics"]["views"]["value"] for r in all_rows
                      if r["evaluation"]["first7"]["metrics"]["views"]["value"] is not None]
            result.append({k: group[k] for k in ("id", "character_preset_name", "format", "kind", "role", "source",
                                                 "policy_version", "option_values")} | {
                "band": band, "count": len(rows), "total_count": len(all_rows),
                "implementation_version": group.get("implementation_version") or (
                    group["policy_version"] if not (group["policy_version"] or "").startswith("policy_") else None),
                "mixed": bool(set(observations) & mixed), "median": median(values) if values else None,
                "rate": sum(r["evaluation"]["status"] == "reached" for r in rows) / len(rows) if rows else None,
                "video_ids": sorted(r["video_id"] for r in rows),
                "observed_at": max((r["evaluation"]["first30"]["observedAt"] for r in rows), default=None),
                "evidence_ids": sorted({id for r in rows for id in r["evaluation"]["evidence_ids"]}),
                "first7_count": len(first7), "first7_median": median(first7) if first7 else None})
    return result


def pure(cohort, minimum):
    return (cohort["source"] == "automatic" and not cohort["mixed"] and cohort["band"] != "unknown"
            and cohort["policy_version"] and cohort["implementation_version"]
            and cohort["count"] >= minimum and cohort["median"] is not None
            and len(cohort["evidence_ids"]) >= minimum)


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
