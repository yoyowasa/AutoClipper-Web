from app.config import get_settings
from app.intelligence.sync import run_youtube_sync


def enqueue_youtube_sync(run_id: str) -> None:
    from app.jobs.queue import get_queue

    get_queue().enqueue(run_youtube_sync, run_id, job_id=f"youtube_sync-{run_id}",
                        job_timeout=get_settings().youtube_sync_budget_seconds + 30)


def get_enqueue_youtube_sync():
    return enqueue_youtube_sync
