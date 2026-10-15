"""Bounded native evidence: never turn missing values into zero or re-average averages."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.models import Channel, ChannelConnection, ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.production_catalog import read_families
from app.intelligence.policy import statistical_expiry
from app.config import Settings
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

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def build_analysis_input(db: Session, paths: StoragePaths, config: Settings, channel_id: int,
                         review_id: str, stamp: datetime) -> AnalysisContext:
    channel = db.get(Channel, channel_id)
    connection = db.get(ChannelConnection, channel_id)
    if not channel or not connection or connection.status != "connected":
        raise ValueError("OWN_OAUTH_REQUIRED")
    if not config.youtube_derived_allowed:
        raise ValueError("DERIVED_NOT_ALLOWED")
    batch = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel_id, SyncRun.status.in_(["success", "partial"]))
                      .order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()).limit(1))
    if not batch or not batch.last_report_date:
        raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
    cutoff, last = stamp - timedelta(days=30), batch.last_report_date
    videos, expiry = {}, [stamp + timedelta(days=30)]
    if channel.name:
        if not channel.metadata_updated_at or channel.metadata_updated_at <= cutoff:
            raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
        expiry.append(channel.metadata_updated_at + timedelta(days=30))
    for video in db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id).order_by(YouTubeVideo.id)):
        if video.availability != "available" or not video.metadata_updated_at or video.metadata_updated_at <= cutoff:
            continue
        expires = video.metadata_updated_at + timedelta(days=30)
        expiry.append(expires)
        videos[video.id] = {"id": video.id, "title": video.title, "published_at": str(video.published_at),
                            "duration_seconds": video.duration_seconds, "format": FORMATS.get(video.format, "unknown")}
    evidence, groups, compact, missing, group_ids = {}, {}, {}, [], {}

    def add(id, value, meta, metric, expires):
        signature = json.dumps(meta, sort_keys=True)
        if signature not in group_ids:
            group_ids[signature] = "g" + str(len(groups) + 1)
        group = group_ids[signature]
        groups[group] = meta
        evidence[id] = {"id": id, "value": value, "metric": metric, "expires_at": expires.isoformat() + "Z", **meta}
        compact[id] = {"value": value, "group": group}
        expiry.append(expires)

    kinds = ["daily", "current", "previous", "video_period", "first7", "video_format"]
    for row in db.scalars(select(VideoDailyStat).where(VideoDailyStat.channel_id == channel_id,
                         VideoDailyStat.expires_at > stamp, VideoDailyStat.kind.in_(kinds)).order_by(VideoDailyStat.id)):
        if row.video_id and row.video_id not in videos:
            continue
        if row.kind == "daily" and not (batch.requested_start or last - timedelta(days=59)) <= row.period_start <= last:
            continue
        if (row.kind in {"current", "video_period", "video_format"}
                and (row.period_start, row.period_end) != (last - timedelta(days=27), last)):
            continue
        if row.kind == "previous" and (row.period_start, row.period_end) != (last - timedelta(days=55), last - timedelta(days=28)):
            continue
        meta = {"video_id": row.video_id, "source": row.source, "kind": row.kind, "period_start": str(row.period_start),
                "period_end": str(row.period_end), "observed_at": row.observed_at.isoformat() + "Z",
                "definition_version": row.definition_version, "dimensions": row.dimensions}
        # Share metadata across metrics instead of duplicating it in the prompt.
        group = "g" + str(len(groups) + 1)
        groups[group] = meta
        for metric, value in row.values.items():
            id = f"r:{row.id}:{metric}"
            if value is None:
                missing.append({"id": id, "group": group, "reason": row.missing_reasons.get(metric, "UNAVAILABLE")})
            else:
                evidence[id] = {"id": id, "value": value, "metric": metric,
                                "expires_at": row.expires_at.isoformat() + "Z", **meta}
                compact[id] = {"value": value, "group": group}
        expiry.append(row.expires_at)
    for video in db.scalars(select(YouTubeVideo).where(YouTubeVideo.id.in_(videos))):
        if not video.public_observed_at or statistical_expiry(video.public_observed_at, config) <= stamp:
            continue
        public = video.public_statistics or {}
        for metric, value in public.get("values", {}).items():
            if value is None:
                missing.append({"id": f"p:{video.id}:{metric}", "reason": public.get("missingReasons", {}).get(metric, "UNAVAILABLE")})
            else:
                add(f"p:{video.id}:{metric}", value, {"video_id": video.id, "source": "youtube_public", "kind": "public",
                    "period_start": None, "period_end": None, "observed_at": video.public_observed_at.isoformat() + "Z",
                    "definition_version": "youtube-public", "dimensions": {}}, metric, statistical_expiry(video.public_observed_at, config))
    families, issues = read_families(paths)
    for link in db.scalars(select(ProductionLink).where(ProductionLink.youtube_video_id.in_(videos))):
        family = families.get(link.record_family_id)
        if not family or family.ambiguous or family.latest.recordId != link.record_id:
            missing.append({"video_id": link.youtube_video_id, "reason": "PRODUCTION_RECORD_UNAVAILABLE"})
            continue
        record = family.latest
        hook_length = (record.hookSceneEnd - record.hookSceneStart
                       if record.hookSceneStart is not None and record.hookSceneEnd is not None else None)
        production = {"recordId": record.recordId, "bodyDurationSeconds": record.bodyDurationSeconds,
            "completedDurationSeconds": record.completedDurationSeconds, "hookSceneDuration": hook_length,
            "hasHookScene": hook_length is not None, "hookText": record.hookText,
            "titleCandidates": record.titleCandidates.model_dump(), "postMetadataSource": record.postMetadataSource,
            "selection": record.selection.model_dump(include={"candidateId", "reason", "selectionReason", "longformReason",
                "topicKey", "openingScore", "score", "finalScore"}), "characterPresetName": record.characterPresetName}
        id = "production:" + record.recordId
        add(id, production, {"video_id": link.youtube_video_id, "source": "production_record", "kind": "production",
            "period_start": None, "period_end": None, "definition_version": "production-record-v1", "dimensions": {}},
            "production", min(expiry))
        videos[link.youtube_video_id]["production_evidence_id"] = id
    if not any(item["source"] == "youtube_analytics" for item in evidence.values()):
        raise ValueError("CODEX_EVIDENCE_UNAVAILABLE")
    payload = {"review_id": review_id, "channel": {"id": channel.id, "name": channel.name},
        "batch": {"run_id": batch.id, "last_report_date": str(last), "status": batch.status},
        "videos": list(videos.values()), "evidence": compact, "evidence_groups": groups, "metric_units": UNITS,
        "format_videos": {format: [id for id, video in videos.items() if video["format"] == format]
                          for format in ("shorts", "videoondemand", "live", "unknown")},
        "missing_reports": [{key: value for key, value in item.items() if key != "requests"} for item in batch.missing_reports],
        "missing_basic_reports": missing, "production_record_issues": len(issues),
        "unavailable_reports": ["format_channel_aggregates", "traffic_sources", "retention", "impressions", "CTR", "swipe_rate"],
        "improvement_plans": []}
    return AnalysisContext(payload, evidence, videos, min(expiry))
