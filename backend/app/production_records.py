"""Permanent, allowlisted production records independent of disposable media."""

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.short_parent_range import ShortParentRangeAdjustment
from app.downloads import export_download_name
from app.models import ExportItem, Job
from app.storage.json_io import write_json_atomic
from app.storage.lifecycle import _resolve_stored_path
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths


logger = logging.getLogger(__name__)


class RecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RecordTitleCandidate(RecordModel):
    id: str
    title: str
    intent: str | None = None


class RecordTitles(RecordModel):
    candidates: list[RecordTitleCandidate] = Field(default_factory=list)
    selectedId: str | None = None
    recommendedId: str | None = None
    intent: str | None = None


class RecordSource(RecordModel):
    title: str | None = None
    url: str | None = None
    start: float | None = None
    end: float | None = None


class RecordSelection(RecordModel):
    candidateId: str | None = None
    reason: str | None = None
    selectionReason: str | None = None
    longformReason: str | None = None
    topicKey: str | None = None
    momentKey: str | None = None
    score: float
    finalScore: float | None = None
    ruleScore: float | None = None
    aiScore: float | None = None
    openingScore: float | None = None
    parentStart: float | None = None
    parentEnd: float | None = None
    parentRangeAdjustments: list[ShortParentRangeAdjustment] = Field(default_factory=list)
    parentRangeAdjustmentsScope: Literal["job"] = "job"


class RecordThumbnail(RecordModel):
    source: Literal["video_frame", "character_asset", "unknown"]
    mode: str | None = None
    frameSeconds: float | None = None
    assetId: str | None = None
    emotion: str | None = None
    reason: str | None = None
    emotionSelectionSource: str | None = None


class ProductionRecord(RecordModel):
    schemaVersion: Literal[1] = 1
    recordId: str
    revision: int = Field(ge=1)
    createdAt: datetime
    updatedAt: datetime
    previousRecordId: str | None = None
    jobId: str
    type: Literal["normal", "short"]
    publicationTitle: str
    overlayTitle: str | None = None
    hookText: str | None = None
    hookSceneStart: float | None = None
    hookSceneEnd: float | None = None
    thumbnailKicker: str | None = None
    thumbnailLine1: str | None = None
    thumbnailLine2: str | None = None
    titleCandidates: RecordTitles
    postMetadataSource: str | None = None
    bodyDurationSeconds: float
    completedDurationSeconds: float
    source: RecordSource
    characterPresetName: str | None = None
    selection: RecordSelection
    thumbnail: RecordThumbnail


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def _selected_candidate(paths: StoragePaths, export: ExportItem) -> dict[str, Any]:
    payload = _read_object(paths.outputs / export.job_id / "selected_clips.json")
    candidates = payload.get("normalClips", payload.get("normal_clips", [])) + payload.get("shorts", [])
    return next((c for c in candidates if c.get("id") == export.candidate_id), {})


def _source_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return None
    # Preserve public video identity only; never export credentials in query strings.
    from urllib.parse import parse_qs, urlencode

    query = parse_qs(parts.query)
    youtube_host = parts.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}
    public_query = urlencode({"v": query["v"][0]}) if youtube_host and "v" in query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, public_query, ""))


def build_production_record(
    job: Job, export: ExportItem, paths: StoragePaths, *, previous: ProductionRecord | None = None,
    created_at: datetime | None = None,
) -> ProductionRecord:
    selected = _selected_candidate(paths, export)
    metadata = _read_object(_resolve_stored_path(export.metadata_path, paths.root)) if export.metadata_path else {}
    data = {**selected, **metadata}
    settings = job.settings_json or {}
    candidates = [RecordTitleCandidate(**{k: c[k] for k in ("id", "title", "intent") if k in c})
                  for c in data.get("title_candidates", [])]
    selected_id = data.get("selected_title_id")
    intent = next((c.intent for c in candidates if c.id == selected_id), None)
    start, end = data.get("start"), data.get("end")
    body = data.get("body_duration", end - start if start is not None and end is not None else export.duration)
    adjustments = []
    for filename in ("codex_initial_selection_summary.json", "codex_reselection_summary.json"):
        for item in _read_object(paths.outputs / job.id / filename).get("parentRangeAdjustments", []):
            adjustment = ShortParentRangeAdjustment.model_validate(item)
            if adjustment not in adjustments:
                adjustments.append(adjustment)
    thumbnail_source = data.get("thumbnail_subject_source")
    if thumbnail_source is None and data.get("thumbnail_source_time_basis"):
        thumbnail_source = "asset" if data["thumbnail_source_time_basis"] == "character_asset" else "video"
    now = datetime.now(UTC)
    return ProductionRecord(
        recordId=export.id, revision=previous.revision + 1 if previous else 1,
        createdAt=created_at if created_at is not None else previous.createdAt if previous else now,
        updatedAt=max(now, created_at) if created_at is not None else now,
        previousRecordId=previous.recordId if previous and previous.recordId != export.id else (
            previous.previousRecordId if previous else None),
        jobId=job.id, type=export.type, publicationTitle=export_download_name(export).stem,
        overlayTitle=data.get("overlay_title"), hookText=data.get("hook_text"),
        hookSceneStart=data["hook_scene_start"] - start if data.get("hook_scene_start") is not None and start is not None else None,
        hookSceneEnd=data["hook_scene_end"] - start if data.get("hook_scene_end") is not None and start is not None else None,
        thumbnailKicker=data.get("thumbnail_kicker"), thumbnailLine1=data.get("thumbnail_line1"),
        thumbnailLine2=data.get("thumbnail_line2"),
        titleCandidates=RecordTitles(candidates=candidates, selectedId=selected_id,
                                    recommendedId=data.get("recommended_title_id"), intent=intent),
        postMetadataSource=data.get("post_metadata_source"),
        bodyDurationSeconds=body, completedDurationSeconds=export.duration,
        source=RecordSource(title=settings.get("youtubeSourceTitle") or None, url=_source_url(settings.get("youtubeSourceUrl")),
                            start=start, end=end),
        characterPresetName=settings.get("characterPresetName") or None,
        selection=RecordSelection(
            candidateId=export.candidate_id, score=export.score, parentRangeAdjustments=adjustments,
            **{key: data.get(value) for key, value in {
                "reason": "reason", "selectionReason": "selection_reason", "longformReason": "longform_reason",
                "topicKey": "topic_key", "momentKey": "moment_key", "finalScore": "final_score", "ruleScore": "rule_score",
                "aiScore": "ai_score", "openingScore": "opening_score", "parentStart": "parent_start", "parentEnd": "parent_end",
            }.items()},
        ),
        thumbnail=RecordThumbnail(
            source="character_asset" if thumbnail_source == "asset" else "video_frame" if thumbnail_source in {"video", "legacy"}
            else "unknown", mode=data.get("thumbnail_crop_mode"), frameSeconds=data.get("thumbnail_frame_seconds"),
            assetId=data.get("thumbnail_character_asset_id"), emotion=data.get("thumbnail_emotion"),
            reason=data.get("thumbnail_subject_reason"), emotionSelectionSource=data.get("thumbnail_emotion_selection_source"),
        ),
    )


def write_production_record(
    job: Job, export: ExportItem, paths: StoragePaths, *, previous_export: ExportItem | None = None,
) -> Path:
    # The same lock used by lifecycle prevents concurrent read/increment/write and cleanup races.
    with storage_mutation_lock(paths.root):
        target = paths.production_record(export.id)
        previous_path = target
        if not target.exists() and previous_export is not None:
            previous_path = paths.production_record(previous_export.id)
        previous = ProductionRecord.model_validate(_read_object(previous_path)) if previous_path.exists() else None
        record = build_production_record(job, export, paths, previous=previous)
        return write_json_atomic(target, record.model_dump(mode="json", by_alias=True), allow_nan=False)


def record_completed_productions(
    db: Session, job: Job, paths: StoragePaths, *, previous_exports: list[ExportItem] | None = None,
) -> None:
    """Best effort only, called after successful publication and its DB commit."""
    try:
        if job.status != "completed":
            return
        previous_by_candidate = {e.candidate_id: e for e in previous_exports or []}
        exports = list(db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)))
        for export in exports:
            try:
                write_production_record(job, export, paths, previous_export=previous_by_candidate.get(export.candidate_id))
            except Exception as exc:
                logger.warning("Production record failed: job=%s export=%s errorType=%s", job.id, export.id, type(exc).__name__)
    except Exception as exc:
        logger.warning("Production records failed: job=%s errorType=%s", job.id, type(exc).__name__)


def backfill_production_records(db: Session, paths: StoragePaths, *, execute: bool = False, force: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {"operation": "backfill-production-records", "dry_run": not execute, "force": force,
                              "eligible": 0, "written": 0, "skipped": 0, "targets": [], "errors": []}
    for export, job in db.execute(select(ExportItem, Job).join(Job).where(Job.status == "completed").order_by(ExportItem.id)):
        try:
            target = paths.production_record(export.id)
            if target.exists() and not force:
                report["skipped"] += 1
                continue
            # Build even in dry-run to catch unreadable/malformed source JSON, without creating any files.
            # SQLite stores naive UTC; aware timestamps must retain their instant when normalized.
            created_at = (export.created_at.replace(tzinfo=UTC) if export.created_at.tzinfo is None
                          else export.created_at.astimezone(UTC))
            previous = ProductionRecord.model_validate(_read_object(target)) if target.exists() else None
            build_production_record(job, export, paths, previous=previous, created_at=created_at)
            report["eligible"] += 1
            report["targets"].append(export.id)
            if execute:
                with storage_mutation_lock(paths.root):
                    # Recheck after locking in case a worker/backfill created the record.
                    if target.exists() and not force:
                        report["skipped"] += 1
                        continue
                    previous = ProductionRecord.model_validate(_read_object(target)) if target.exists() else None
                    record = build_production_record(job, export, paths, previous=previous, created_at=created_at)
                    write_json_atomic(target, record.model_dump(mode="json", by_alias=True), allow_nan=False)
                    report["written"] += 1
        except Exception as exc:
            report["errors"].append({"exportId": export.id, "errorType": type(exc).__name__})
    return report
