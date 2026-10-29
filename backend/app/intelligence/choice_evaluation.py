"""Associate published choices with fixed-age observations; never infer causation."""
from collections import Counter, defaultdict
from datetime import UTC
import hashlib
import json
import math
from statistics import median

from sqlalchemy import select

from app.intelligence.dashboard_reports import fresh_video, missing_report, native_window, valid_stat
from app.intelligence.choice_options import bounded_values, choice_options
from app.intelligence.evaluation_rules import GOALS, PACIFIC, goal_target, initial_window
from app.intelligence.evaluation_schemas import ChoiceEvaluationsRead, VideoGoalRead
from app.intelligence.models import ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.production_catalog import read_families
from app.intelligence.production_dimensions import MIN_GROUP_VIDEOS
from app.intelligence.policy import statistical_expiry
from app.production_choices import value_hash

MAX_CHOICE_INPUT_CHARS = 40_000
MAX_CHOICE_INPUT_GROUPS = 30


def initial_report(video, rows, last, stamp, days):
    if video.published_at is None:
        return missing_report("PUBLICATION_UNAVAILABLE")
    start, end = initial_window(video.published_at, days)
    today = stamp.replace(tzinfo=UTC).astimezone(PACIFIC).date()
    if today <= end:
        return missing_report(f"FIRST{days}_NOT_READY", start, end)
    if last is None or end > last:
        return missing_report("REPORT_NOT_RETURNED", start, end)
    return native_window(rows, f"first{days}", start, end, expected_format=video.format)


def evaluate_video_goal(video, rows, last, stamp):
    first7, first30 = (initial_report(video, rows, last, stamp, days) for days in (7, 30))
    target = goal_target(video.format)
    views = first30.metrics["views"].value
    missing = first30.reason or first30.metrics["views"].missingReason
    if not target:
        status, reason = "insufficient_data", "FORMAT_UNKNOWN"
    elif missing == "FIRST30_NOT_READY":
        status, reason = "pending", missing
    elif views is None or not math.isfinite(views) or views < 0 or missing:
        status, reason = "insufficient_data", missing or "INVALID_OBSERVATION"
    else:
        status, reason = ("reached" if views >= target else "below_target"), None
    matches = [row for row in rows if row.kind == "first30" and first30.observedAt == row.observed_at
               and (row.period_start, row.period_end) == (first30.start, first30.end)
               and row.values.get("views") == views and views is not None]
    evidence = [f"r:{max(matches, key=lambda row: row.id).id}:views"] if matches else []
    return VideoGoalRead(video_id=video.id, format=video.format, target_views=target,
                         status=status, reason=reason, evidence_ids=evidence, first7=first7, first30=first30)


def final_choices(record, *, as_of=None):
    # Do not attribute an unpublished recommendation and its manual replacement
    # to the same outcome. Preserve provenance; observed legacy values are last resort.
    def applied_time(choice):
        value = choice.appliedAt or choice.recordedAt
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    cutoff = as_of.astimezone(UTC).replace(tzinfo=None) if as_of is not None and as_of.tzinfo else as_of
    selected, observed = {}, {}
    for choice in sorted(record.choiceHistory, key=lambda c: (applied_time(c), c.id)):
        if cutoff is not None and applied_time(choice) > cutoff:
            continue
        if choice.scope == "clip" and choice.clipId and choice.clipId != record.selection.candidateId:
            continue
        roles = [key for key in ("titleStyle", "hookStyle", "subtitleStyle") if key in choice.values] \
            if choice.kind == "text_style" else []
        for role in roles or [""]:
            item = choice.model_copy(update={"values": {role: choice.values[role]}}) if role else choice
            key = (choice.kind, role)
            if choice.stage == "removed":
                selected.pop(key, None)
                observed.pop(key, None)
            elif choice.stage in {"applied", "published"}:
                if key in selected and choice.source in {"manual", "unrecorded"} and selected[key].values == item.values:
                    continue
                selected[key] = item
            elif choice.stage == "observed":
                observed[key] = item
    return [(key, selected.get(key) or observed[key]) for key in sorted(selected.keys() | observed.keys())]


def build_choice_evaluations(db, paths, config, channel_id, stamp, *, families=None):
    if families is None:
        families, _ = read_families(paths)
    batch = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel_id, SyncRun.status.in_(["success", "partial"]))
                      .order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()).limit(1))
    last = batch.last_report_date if batch else None
    videos = {v.id: v for v in db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id))}
    rows, expiries = defaultdict(list), []
    for row in db.scalars(select(VideoDailyStat).where(VideoDailyStat.channel_id == channel_id,
                          VideoDailyStat.kind.in_(["first7", "first30"]), VideoDailyStat.expires_at > stamp)):
        if valid_stat(row, config, stamp):
            rows[row.video_id].append(row)
            expiries.append(min(row.expires_at, statistical_expiry(row.observed_at, config)))
    groups, excluded, linked = {}, Counter(), 0
    for link in db.scalars(select(ProductionLink).where(ProductionLink.youtube_video_id.in_(videos))):
        linked += 1
        family, video = families.get(link.record_family_id), videos[link.youtube_video_id]
        if not family or family.ambiguous or family.latest.recordId != link.record_id:
            excluded["RECORD_UNAVAILABLE"] += 1
            continue
        record = family.latest
        if not fresh_video(video, stamp):
            excluded["METADATA_UNAVAILABLE"] += 1
            continue
        if {"normal": "long", "short": "shorts"}.get(record.type) != video.format:
            excluded["FORMAT_MISMATCH"] += 1
            continue
        evaluation = evaluate_video_goal(video, rows[video.id], last, stamp).model_dump(mode="json")
        choices = final_choices(record, as_of=video.published_at)
        if not choices:
            excluded["CHOICES_UNRECORDED"] += 1
        for (kind, role), choice in choices:
            options = choice_options(kind, role, choice.values)
            key = (record.characterPresetName or "未設定", record.type, kind, role, choice.source, choice.policyVersion,
                   json.dumps(options, ensure_ascii=False, sort_keys=True), choice.implementationVersion)
            id = "choice:" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:24]
            group = groups.setdefault(id, {"id": id, "character_preset_name": key[0], "format": key[1],
                "kind": kind, "role": role, "source": choice.source, "policy_version": choice.policyVersion,
                "option_values": options, "observations": []})
            group["implementation_version"] = choice.implementationVersion
            group["observations"].append({"record_id": record.recordId, "record_family_id": link.record_family_id,
                "choice_id": choice.id, "video_id": video.id, "kind": kind, "role": role, "source": choice.source,
                "policy_version": choice.policyVersion, "value_hash": value_hash(choice.values),
                **bounded_values(choice.values),
                "selected_ids": choice.selectedIds, "evaluation": evaluation})
    for group in groups.values():
        judged = {r["video_id"]: r for r in group["observations"] if r["evaluation"]["status"] in {"reached", "below_target"}}
        values = [r["evaluation"]["first30"]["metrics"]["views"]["value"] for r in judged.values()]
        reached = sum(r["evaluation"]["status"] == "reached" for r in judged.values())
        group.update(count=len({r["video_id"] for r in group["observations"]}), judged_count=len(judged),
            sufficient=len(judged) >= MIN_GROUP_VIDEOS and group["source"] != "unrecorded" and bool(group["policy_version"]),
            target_views=goal_target(group["format"]), median_views=median(values) if values else None,
            reached_count=reached, attainment_rate=reached / len(judged) if judged else None,
            video_ids=sorted({r["video_id"] for r in group["observations"]}))
    return ChoiceEvaluationsRead(minimum_group_videos=MIN_GROUP_VIDEOS, linked_videos=linked,
        excluded_reasons=dict(excluded), groups=sorted(groups.values(), key=lambda g: g["id"]),
        expires_at=min(expiries).isoformat() + "Z" if expiries else None).model_dump(mode="json")


def choice_evaluation_input(payload):
    # Keep root observations in the stored aggregate/API. Analysis gets bounded
    # summaries, with explicit sampling, rather than repeating each metric per choice.
    groups = sorted(payload["groups"], key=lambda g: (-g["judged_count"], g["id"]))
    compact, chars = [], 0
    for group in groups:
        judged = [row for row in group["observations"] if row["evaluation"]["status"] in {"reached", "below_target"}]
        ids = sorted({row["video_id"] for row in judged})
        item = {key: value for key, value in group.items() if key not in {"observations", "video_ids", "count"}} | {
            "count": group["judged_count"], "total_count": group["count"], "video_ids": ids[:20],
            "omitted_video_ids": max(0, len(ids) - 20),
            "observed_at": max((r["evaluation"]["first30"]["observedAt"] for r in judged), default=None)}
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        if len(compact) < MAX_CHOICE_INPUT_GROUPS and chars + size <= MAX_CHOICE_INPUT_CHARS:
            compact.append(item)
            chars += size
    return {"goals": GOALS, "source": payload["source"], "label": payload["label"],
        "minimum_group_videos": payload["minimum_group_videos"], "omitted_groups": len(groups) - len(compact),
        "groups": compact}


def analysis_choice_snapshot(record, *, as_of=None):
    result = []
    for (kind, role), choice in final_choices(record, as_of=as_of):
        result.append({"id": choice.id, "kind": kind, "role": role, "source": choice.source,
            "policy_version": choice.policyVersion, "value_hash": value_hash(choice.values),
            "selected_ids": choice.selectedIds[:20], **bounded_values(choice.values)})
    return result
