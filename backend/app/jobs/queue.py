from collections.abc import Callable

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.jobs.runner import run_autoclipper_job

JobEnqueue = Callable[[str], None]


def get_redis_connection() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue() -> Queue:
    settings = get_settings()
    return Queue(settings.rq_queue_name, connection=get_redis_connection())


def enqueue_autoclipper_job(job_id: str) -> None:
    queue = get_queue()
    queue.enqueue(run_autoclipper_job, job_id, job_timeout=3600)


def get_enqueue_job() -> JobEnqueue:
    return enqueue_autoclipper_job
