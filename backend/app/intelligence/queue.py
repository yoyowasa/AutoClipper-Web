from app.config import get_settings
from app.intelligence.sync import run_youtube_sync
from rq import Queue


def get_intelligence_queue() -> Queue:
    from app.jobs.queue import get_redis_connection

    return Queue(get_settings().rq_intelligence_queue_name, connection=get_redis_connection())


def enqueue_youtube_sync(run_id: str) -> None:
    get_intelligence_queue().enqueue(run_youtube_sync, run_id, job_id=f"youtube_sync-{run_id}",
                        job_timeout=get_settings().youtube_sync_budget_seconds + 30)


def get_enqueue_youtube_sync():
    return enqueue_youtube_sync


def enqueue_channel_analysis(run_id: str) -> None:
    from app.intelligence.analysis_runner import analysis_job_timeout, run_channel_analysis
    get_intelligence_queue().enqueue(run_channel_analysis, run_id, job_id=f"channel_analysis-{run_id}",
                        job_timeout=analysis_job_timeout(get_settings()))


def get_enqueue_channel_analysis():
    return enqueue_channel_analysis
