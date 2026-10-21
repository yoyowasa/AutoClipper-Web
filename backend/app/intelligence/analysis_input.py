"""Bounded, report-oriented evidence; no duplicate metric/metadata maps in the prompt."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.intelligence.analysis_budget import fit_analysis_budget
from app.intelligence.analysis_cohort import select_video_cohort
from app.intelligence.analysis_reports import REPORT_DEFAULTS, native_report, reports_for_video, within_input_period
from app.intelligence.models import Channel, ChannelConnection, ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.policy import statistical_expiry
from app.intelligence.production_catalog import read_families
from app.intelligence.production_aggregation import aggregate_analysis_input, build_production_aggregates
from app.storage.paths import StoragePaths

UNITS = {"estimatedMinutesWatched": "分", "averageViewDuration": "秒", "averageViewPercentage": "%",
         "subscribersGained": "人", "subscribersLost": "人"}
FORMATS = {"shorts": "shorts", "long": "videoondemand", "live": "live", "unknown": "unknown"}


@dataclass
class AnalysisContext:
    payload: dict
    evidence: dict
    videos: dict
    expires_at: datetime
    aggregates: dict | None = None

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _production(record) -> dict:
    hook_length = (record.hookSceneEnd - record.hookSceneStart
                   if record.hookSceneStart is not None and record.hookSceneEnd is not None else None)
    return {"recordId": record.recordId, "bodyDurationSeconds": record.bodyDurationSeconds,
        **({"performanceHints": [hint.model_dump(by_alias=True, mode="json") for hint in record.performanceHints]}
           if record.performanceHints else {}),
        "completedDurationSeconds": record.completedDurationSeconds, "hookSceneDuration": hook_length,
        "hasHookScene": hook_length is not None, "hookText": record.hookText,
        "titleCandidates": record.titleCandidates.model_dump(), "postMetadataSource": record.postMetadataSource,
        "selection": record.selection.model_dump(include={"candidateId", "reason", "selectionReason", "longformReason",
            "topicKey", "openingScore", "score", "finalScore"}), "characterPresetName": record.characterPresetName}


def _expand_evidence(payload, expires):
    """Server-only ID index for existing validation; never duplicated into the prompt."""
    evidence = {}
    pairs = [(None, report) for report in payload["channel_reports"]]
    for video in payload["videos"]:
        pairs.extend((video["id"], report) for report in video["reports"])
        if "production" in video:
            production = video["production"]
            evidence[production["id"]] = {"id": production["id"], "video_id": video["id"], "source": "production_record",
                                           "kind": "production", "value": production["value"], "metric": "production"}
    for video_id, report in pairs:
        meta = {**REPORT_DEFAULTS, **{key: value for key, value in report.items() if key not in {"id", "values", "missing"}},
                "video_id": video_id, "expires_at": expires.isoformat() + "Z"}
        for metric, value in report["values"].items():
            id = report["id"] + ":" + metric
            evidence[id] = {"id": id, "value": value, "metric": metric, **meta}
    return evidence


def build_analysis_input(db: Session, paths: StoragePaths, config: Settings, channel_id: int,
                         review_id: str, stamp: datetime) -> AnalysisContext:
    channel, connection = db.get(Channel, channel_id), db.get(ChannelConnection, channel_id)
    if not channel or not connection or connection.status != "connected":
        raise ValueError("OWN_OAUTH_REQUIRED")
    if not config.youtube_derived_allowed:
        raise ValueError("DERIVED_NOT_ALLOWED")
    batch = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel_id, SyncRun.status.in_(["success", "partial"]))
                      .order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()).limit(1))
    if not batch or not batch.last_report_date:
        raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
    cutoff, last = stamp - timedelta(days=30), batch.last_report_date
    start = max(batch.requested_start or last - timedelta(days=59), last - timedelta(days=59))
    expiry = [stamp + timedelta(days=30)]
    if channel.name:
        if not channel.metadata_updated_at or channel.metadata_updated_at <= cutoff:
            raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
        expiry.append(channel.metadata_updated_at + timedelta(days=30))
    videos, public_views, entities = {}, {}, {}
    for video in db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id).order_by(YouTubeVideo.id)):
        if video.availability != "available" or not video.metadata_updated_at or video.metadata_updated_at <= cutoff:
            continue
        expiry.append(video.metadata_updated_at + timedelta(days=30))
        entities[video.id] = video
        videos[video.id] = {"id": video.id, "title": video.title,
                            "published_at": str(video.published_at) if video.published_at else None,
                            "duration_seconds": video.duration_seconds, "format": FORMATS.get(video.format, "unknown")}
        value = (video.public_statistics or {}).get("values", {}).get("views")
        if value is not None and video.public_observed_at and statistical_expiry(video.public_observed_at, config) > stamp:
            public_views[video.id] = value
    videos, scope = select_video_cohort(videos, public_views, last)
    rows_by_video, channel_reports = defaultdict(list), []
    for row in db.scalars(select(VideoDailyStat).where(VideoDailyStat.channel_id == channel_id,
                         VideoDailyStat.expires_at > stamp,
                         or_(VideoDailyStat.video_id.is_(None), VideoDailyStat.video_id.in_(videos)),
                         VideoDailyStat.kind.in_(["daily", "current", "previous", "video_period", "first7", "video_format", "video_day"]),
                         or_(VideoDailyStat.kind == "first7", VideoDailyStat.period_start >= min(start, last - timedelta(days=55))))
                         .order_by(VideoDailyStat.id)):
        if not within_input_period(row, last, start):
            continue
        expiry.append(row.expires_at)
        if row.video_id:
            rows_by_video[row.video_id].append(row)
        elif row.kind in {"daily", "current", "previous"}:
            channel_reports.append(native_report(row))
    duplicate_reports = 0
    for id, video in videos.items():
        video["reports"], duplicates = reports_for_video(id, rows_by_video[id], start, last)
        duplicate_reports += duplicates
        entity = entities[id]
        if entity.public_observed_at and statistical_expiry(entity.public_observed_at, config) > stamp:
            public = entity.public_statistics or {}
            values = public.get("values", {})
            video["reports"].append({"id": "p:" + id, "kind": "public", "source": "youtube_public",
                "definition_version": "youtube-public", "observed_at": entity.public_observed_at.isoformat() + "Z",
                "values": {key: value for key, value in values.items() if value is not None},
                "missing": {key: public.get("missingReasons", {}).get(key, "UNAVAILABLE")
                            for key, value in values.items() if value is None}})
            expiry.append(statistical_expiry(entity.public_observed_at, config))
    families, issues = read_families(paths)
    for link in db.scalars(select(ProductionLink).where(ProductionLink.youtube_video_id.in_(videos))):
        family = families.get(link.record_family_id)
        if not family or family.ambiguous or family.latest.recordId != link.record_id:
            videos[link.youtube_video_id]["production_missing"] = "PRODUCTION_RECORD_UNAVAILABLE"
            continue
        record = family.latest
        id = "production:" + record.recordId
        videos[link.youtube_video_id].update(production_evidence_id=id, production={"id": id, "value": _production(record)})
    payload = {"review_id": review_id, "channel": {"id": channel.id, "name": channel.name},
        "batch": {"run_id": batch.id, "last_report_date": str(last), "status": batch.status},
        "videos": list(videos.values()), "channel_reports": channel_reports, "report_defaults": REPORT_DEFAULTS,
        "metric_units": UNITS, "input_scope": scope, "deduplicated_reports": duplicate_reports,
        "format_videos": {format: [id for id, video in videos.items() if video["format"] == format]
                          for format in ("shorts", "videoondemand", "live", "unknown")},
        "missing_reports": [{key: value for key, value in item.items() if key != "requests"} for item in batch.missing_reports],
        "production_record_issues": len(issues),
        "unavailable_reports": ["format_channel_aggregates", "traffic_sources", "retention", "impressions", "CTR", "swipe_rate"],
        "improvement_plans": []}
    aggregates = build_production_aggregates(db, paths, config, channel_id, stamp)
    expiry.append(datetime.fromisoformat(aggregates["expires_at"].replace("Z", "+00:00")).replace(tzinfo=None))
    payload["production_aggregates"] = aggregate_analysis_input(aggregates)
    fit_analysis_budget(payload)
    evidence = _expand_evidence(payload, min(expiry))
    for group in payload["production_aggregates"]["groups"]:
        evidence[group["id"]] = {"id": group["id"], "video_id": None, "source": "independent_aggregation",
                                 "value": group, "format": group["format"]}
    if not any(item["source"] == "youtube_analytics" for item in evidence.values()):
        raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
    return AnalysisContext(payload, evidence, {video["id"]: video for video in payload["videos"]}, min(expiry), aggregates)
