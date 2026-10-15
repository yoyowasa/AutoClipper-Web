from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from rq.timeouts import JobTimeoutException

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.intelligence.collection import collect_reports
from app.intelligence.common import YouTubeError, now
from app.intelligence.credentials import load_credentials
from app.intelligence.ingest import ingest_video, save_report
from app.intelligence.models import Channel, ChannelConnection, SyncRun, YouTubeVideo
from app.intelligence.production_links import reconcile_safely
from app.intelligence.youtube_client import YouTubeClient
from app.storage.paths import StoragePaths, get_storage_paths


def mark_sync_failed(db: Session, run_id: str, code: str) -> None:
    db.execute(update(SyncRun).where(SyncRun.id == run_id, SyncRun.status.in_(["queued", "running"])).values(
        status="failed", error_code=code, finished_at=now(), active_channel_id=None))
    db.commit()


def record_rq_sync_failure(db: Session, rq_job) -> None:
    if getattr(rq_job, "func_name", None) == "app.intelligence.sync.run_youtube_sync" and rq_job.args:
        mark_sync_failed(db, str(rq_job.args[0]), "WORKER_INTERRUPTED")


def run_youtube_sync(run_id: str, *, session_factory: Callable[[], Session] = SessionLocal,
                     paths: StoragePaths | None = None, config: Settings | None = None, client: YouTubeClient | None = None) -> None:
    settings, storage = config or get_settings(), paths or get_storage_paths()
    with session_factory() as db:
        claim = db.execute(update(SyncRun).where(SyncRun.id == run_id, SyncRun.status == "queued")
                           .values(status="running", started_at=now()))
        db.commit()
        if claim.rowcount != 1:
            return
        run = db.get(SyncRun, run_id)
        channel = db.get(Channel, run.channel_id)
        try:
            connection = db.get(ChannelConnection, channel.id)
            if not connection or connection.status != "connected":
                raise YouTubeError("RECONNECT_REQUIRED")
            if client is None:
                credentials = load_credentials(storage, channel.external_id)
                client = YouTubeClient(credentials.token, budget_seconds=settings.youtube_sync_budget_seconds)
            # Avoid holding SQLite write locks during network I/O. Stage ORM
            # changes without autoflush, then publish the whole batch at once.
            with db.no_autoflush:
                identity = client.identity()
                if identity["id"] != channel.external_id:
                    raise YouTubeError("CHANNEL_MISMATCH")
                ids, truncated = client.uploads(identity["contentDetails"]["relatedPlaylists"]["uploads"])
                # Refresh tracked older uploads too; the discovery cap does not exempt
                # metadata from the 30-day refresh/delete requirement.
                known = db.scalars(select(YouTubeVideo.id).where(YouTubeVideo.channel_id == channel.id)).all()
                ids = list(dict.fromkeys([*ids, *known]))
                stamp = now()
                prepared = []
                for requested, items in client.videos(ids):
                    if any(item["snippet"]["channelId"] != channel.external_id or item["id"] not in requested for item in items):
                        raise YouTubeError("CHANNEL_MISMATCH")
                    returned = set()
                    for item in items:
                        if item.get("status", {}).get("privacyStatus") == "public":
                            prepared.append(ingest_video(db, channel.id, item, stamp))
                            returned.add(item["id"])
                    for missing in set(requested) - returned:
                        old = db.get(YouTubeVideo, missing)
                        if old:
                            old.availability = "unavailable_unconfirmed"
                videos = sorted(prepared, key=lambda video: (video.published_at, video.id), reverse=True)
                previous = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel.id, SyncRun.status.in_(["success", "partial"]))
                                     .order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()).limit(1))
                pending = next((entry["requests"] for entry in previous.missing_reports if entry.get("kind") == "pending_reports"),
                               []) if previous else []
                start, end, last, reports, pending = collect_reports(client, channel.external_id, videos, stamp, pending=pending)
            db.flush()
            for report in reports:
                save_report(db, run, settings, report.kind, report.start, report.end, report.rows, stamp, report.video_id,
                            error=report.error)
            if pending:
                run.missing_reports = [*run.missing_reports, {"kind": "pending_reports", "reason": "SYNC_LIMIT", "requests": pending}]
            channel.name, channel.metadata_updated_at, channel.last_sync_at = identity["snippet"]["title"], stamp, stamp
            run.requested_start, run.requested_end, run.last_report_date = start, end, last
            run.truncated = truncated or bool(pending)
            partial_failure = any(report.error for report in reports)
            run.error_code = "API_5XX" if partial_failure else "SYNC_LIMIT" if pending else None
            run.status = "partial" if run.truncated or partial_failure else "success"
            run.finished_at, run.active_channel_id = now(), None
            run.fetched_count, run.request_count = sum(len(report.rows) for report in reports), client.requests
            db.commit()
            reconcile_safely(db, storage)
        except Exception as error:
            db.rollback()
            if isinstance(error, YouTubeError):
                code = error.code
            elif isinstance(error, JobTimeoutException):
                code = "SYNC_LIMIT"
            else:
                code = "SYNC_FAILED"
            run = db.get(SyncRun, run_id)
            run.request_count = client.requests if client else 0
            if isinstance(error, YouTubeError):
                run.missing_reports = [*run.missing_reports, {"kind": "sync_failure", **error.details()}]
            if code == "RECONNECT_REQUIRED":
                connection = db.get(ChannelConnection, channel.id)
                if connection:
                    connection.status, connection.error_code = "reconnect_required", code
            mark_sync_failed(db, run_id, code)
            # RQ sees failure too; the exception contains only an allowlisted reason.
            raise YouTubeError(code) from None
