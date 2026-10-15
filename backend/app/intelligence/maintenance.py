from datetime import datetime, timedelta

from rq.job import JobStatus
from sqlalchemy import select

from app.config import Settings
from app.intelligence.common import now
from app.intelligence.models import SyncRun
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
    if paths.youtube_oauth_states.exists():
        for path in paths.youtube_oauth_states.glob("*.json"):
            try:
                if datetime.fromisoformat(read_private_json(path)["expires_at"]) <= stamp:
                    path.unlink(missing_ok=True)
            except (KeyError, ValueError, OSError, TypeError):
                # Do not include a private file or exception in logs.
                continue
