from datetime import datetime, timedelta

from rq.job import JobStatus
from sqlalchemy import select

from app.config import Settings
from app.intelligence.common import now
from app.intelligence.models import AnalysisRun, SyncRun
from app.intelligence.analysis_runner import analysis_job_timeout, mark_analysis_failed
from app.intelligence.analysis_bridge import cleanup_analysis_files
from app.intelligence.policy import expire_youtube_data
from app.intelligence.secret_files import read_private_json
from app.intelligence.sync import mark_sync_failed
from app.storage.paths import StoragePaths


def maintain_youtube(db, config: Settings, paths: StoragePaths, queues, *, clock: datetime | None = None) -> None:
    stamp = clock or now()
    expire_youtube_data(db, config, clock=stamp)
    active = {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED, JobStatus.CREATED}
    for run in db.scalars(select(SyncRun).where(SyncRun.status.in_(["queued", "running"]))):
        if stamp - (run.started_at or run.queued_at) <= timedelta(seconds=config.youtube_sync_budget_seconds + 60):
            continue
        jobs = [queue.fetch_job(f"youtube_sync-{run.id}") for queue in queues]
        if not any(job and job.get_status(refresh=True) in active for job in jobs):
            mark_sync_failed(db, run.id, "WORKER_INTERRUPTED")
    for run in db.scalars(select(AnalysisRun)):
        if run.status in {"queued", "running"}:
            if stamp - (run.started_at or run.queued_at) <= timedelta(seconds=analysis_job_timeout(config) + 60):
                continue
            jobs = [queue.fetch_job(f"channel_analysis-{run.id}") for queue in queues]
            if any(job and job.get_status(refresh=True) in active for job in jobs):
                continue
            mark_analysis_failed(db, run.id, "WORKER_INTERRUPTED")
        try:
            cleanup_analysis_files(paths, run.request_id)
        except (ValueError, OSError):
            continue
    if paths.youtube_oauth_states.exists():
        for path in paths.youtube_oauth_states.glob("*.json"):
            try:
                if datetime.fromisoformat(read_private_json(path)["expires_at"]) <= stamp:
                    path.unlink(missing_ok=True)
            except (KeyError, ValueError, OSError, TypeError):
                # Do not include a private file or exception in logs.
                continue
    from app.intelligence.scheduling import schedule_due_channels
    schedule_due_channels(db, config, stamp)
