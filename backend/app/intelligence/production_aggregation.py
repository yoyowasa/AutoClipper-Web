"""Locally derived first-seven-day statistics, never averages of daily averages."""

from collections import Counter, defaultdict
import json
from statistics import median

from sqlalchemy import select

from app.intelligence.models import ProductionAggregate, ProductionLink, VideoDailyStat, YouTubeVideo
from app.intelligence.policy import statistical_expiry
from app.intelligence.production_catalog import read_families
from app.intelligence.production_dimensions import DURATION_BANDS, FIRST7_METRICS, FIXED_DIMENSIONS, MIN_GROUP_VIDEOS, attributes, group_id
from app.intelligence.video_formats import content_format
from app.intelligence.analysis_reports import REPORT_DEFAULTS
from app.models import AppPreference

MAX_AGGREGATE_INPUT_CHARS = 80_000


def first7_observations(db, channel_id, config, stamp):
    videos = {video.id: video for video in db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id))}
    observations = {}
    ambiguous_formats = defaultdict(set)
    for row in db.scalars(select(VideoDailyStat).where(VideoDailyStat.channel_id == channel_id,
            VideoDailyStat.kind == "first7", VideoDailyStat.expires_at > stamp).order_by(VideoDailyStat.observed_at, VideoDailyStat.id)):
        video = videos.get(row.video_id)
        if not video or video.availability != "available" or (row.period_end - row.period_start).days != 6:
            continue
        if (row.source != "youtube_analytics" or statistical_expiry(row.observed_at, config) <= stamp
                or row.definition_version != REPORT_DEFAULTS["definition_version"]
                or row.report_timezone != REPORT_DEFAULTS["report_timezone"]):
            continue
        official = content_format(row.dimensions.get("creatorContentType"))
        if row.dimensions.get("creatorContentType") and official == "unknown":
            continue
        format = official if official != "unknown" else video.format
        if format not in {"shorts", "long"} or (official != "unknown" and video.format not in {"unknown", official}):
            continue
        if video.format == "unknown":
            ambiguous_formats[row.video_id].add(format)
        if (row.video_id in observations and not any(row.values.get(metric) is not None for metric in FIRST7_METRICS)
                and "API_5XX" in row.missing_reasons.values()):
            continue
        observations[row.video_id] = {"video_id": row.video_id, "format": "short" if format == "shorts" else "normal",
            "values": {metric: row.values.get(metric) for metric in FIRST7_METRICS},
            "expires_at": min(row.expires_at, statistical_expiry(row.observed_at, config))}
    return {id: row for id, row in observations.items() if len(ambiguous_formats[id]) <= 1}


def build_production_aggregates(db, paths, config, channel_id, stamp) -> dict:
    observations = first7_observations(db, channel_id, config, stamp)
    families, issues = read_families(paths)
    baselines = {}
    for format in ("normal", "short"):
        items = [row for row in observations.values() if row["format"] == format]
        baselines[format] = {metric: {"count": len(values), "median": median(values) if values else None}
            for metric in FIRST7_METRICS for values in [[row["values"][metric] for row in items if row["values"][metric] is not None]]}
    groups, members = {}, defaultdict(list)

    def ensure(character, format, dimension, value):
        id = group_id(character, format, dimension, value)
        groups.setdefault(id, {"id": id, "character_preset_name": character, "format": format,
                               "dimension": dimension, "value": value})
        return id

    preset = db.get(AppPreference, "character_presets")
    characters = {item.get("name") for item in (preset.value_json if preset else {}).get("presets", []) if item.get("name")}
    linked, excluded, excluded_reasons = 0, 0, Counter()
    for link in db.scalars(select(ProductionLink).join(YouTubeVideo, ProductionLink.youtube_video_id == YouTubeVideo.id)
                          .where(YouTubeVideo.channel_id == channel_id)):
        linked += 1
        family, row = families.get(link.record_family_id), observations.get(link.youtube_video_id)
        if not family or family.ambiguous or family.latest.recordId != link.record_id:
            excluded += 1
            excluded_reasons["RECORD_UNAVAILABLE"] += 1
            continue
        record = family.latest
        character = record.characterPresetName or "未設定"
        characters.add(character)
        # A record's intended type is not proof of YouTube's actual format.
        if not row or row["format"] != record.type:
            excluded += 1
            excluded_reasons["FIRST7_UNAVAILABLE" if not row else "FORMAT_MISMATCH"] += 1
            continue
        for dimension, value in attributes(record).items():
            members[ensure(character, record.type, dimension, value)].append(row)
    for character in sorted(characters or {"未設定"}):
        for format in ("normal", "short"):
            for dimension, values in {**FIXED_DIMENSIONS, "duration": DURATION_BANDS[format]}.items():
                for value in values:
                    ensure(character, format, dimension, value)
    for id, group in groups.items():
        rows = members[id]
        metrics = {}
        for metric in FIRST7_METRICS:
            values = [row["values"][metric] for row in rows if row["values"][metric] is not None]
            value = median(values) if values else None
            base = baselines[group["format"]][metric]
            reason = ("MISSING_OBSERVATIONS" if value is None else "BASELINE_MISSING" if base["median"] is None else
                      "BASELINE_ZERO" if base["median"] == 0 else None)
            metrics[metric] = {"count": len(values), "median": value, "baseline_count": base["count"],
                "baseline_median": base["median"], "relative_to_channel_median": value / base["median"] if reason is None else None,
                "missing_reason": reason}
        sufficient = len(rows) >= MIN_GROUP_VIDEOS and metrics["views"]["count"] >= MIN_GROUP_VIDEOS
        group.update(count=len(rows), sufficient=sufficient, status="available" if sufficient else "insufficient_data",
                     metrics=metrics, video_ids=sorted(row["video_id"] for row in rows))
    expires = min((row["expires_at"] for row in observations.values()), default=statistical_expiry(stamp, config))
    return {"source": "independent_aggregation", "label": "独自集計（YouTube公式の集計ではありません）",
        "channel_id": channel_id, "generated_at": stamp.isoformat() + "Z", "expires_at": expires.isoformat() + "Z",
        "minimum_group_videos": MIN_GROUP_VIDEOS, "linked_videos": linked, "excluded_linked_videos": excluded,
        "excluded_reasons": dict(excluded_reasons),
        "record_issues": len(issues), "baselines": baselines, "groups": sorted(groups.values(), key=lambda group: group["id"])}


def save_production_aggregates(db, channel_id, payload, stamp):
    from datetime import datetime

    row = db.get(ProductionAggregate, channel_id)
    if row is None:
        row = ProductionAggregate(channel_id=channel_id)
        db.add(row)
    row.payload, row.generated_at = payload, stamp
    row.expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")).replace(tzinfo=None)


def aggregate_analysis_input(payload):
    sufficient = [group for group in payload["groups"] if group["sufficient"]]
    selected, size = [], 0
    for group in sorted(sufficient, key=lambda group: (-group["count"], group["id"])):
        compact = {**group, "video_ids": group["video_ids"][:100], "video_ids_omitted": max(0, group["count"] - 100)}
        chars = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
        if len(selected) < 40 and size + chars <= MAX_AGGREGATE_INPUT_CHARS:
            selected.append(compact)
            size += chars
    # Bound both axes; preserve real total counts and explicitly label sampled IDs.
    return {"source": payload["source"], "label": payload["label"], "linked_videos": payload["linked_videos"],
        "insufficient_groups": sum(not group["sufficient"] for group in payload["groups"]),
        "omitted_sufficient_groups": len(sufficient) - len(selected),
        "groups": selected}
