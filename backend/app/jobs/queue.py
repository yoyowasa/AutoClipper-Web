from collections.abc import Callable

from redis import Redis
from rq import Queue
from rq.exceptions import DuplicateJobError
from rq.job import JobStatus

from app.config import get_settings
from app.jobs.runner import (
    run_autoclipper_job,
    run_clip_plan_boundary_update,
    run_clip_plan_hook_scene_update,
    run_clip_plan_reselection,
    run_subtitle_review_preview,
    run_subtitle_review_hook_scene_update,
    run_subtitle_review_render,
)

JobEnqueue = Callable[[str], None]
TerminalRetryAllowed = Callable[[], bool]
RetryJobEnqueue = Callable[[str, TerminalRetryAllowed], None]
ClipPlanReselectionEnqueue = Callable[[str], None]
ClipPlanBoundaryUpdateEnqueue = Callable[[str, str, float, float], None]
ClipPlanHookSceneUpdateEnqueue = Callable[
    [str, str, float | None, float | None],
    None,
]
SubtitleReviewHookSceneUpdateEnqueue = Callable[
    [str, str, float | None, float | None],
    None,
]
SubtitleReviewPreviewEnqueue = Callable[[str, str, str], None]
RenderEnqueue = Callable[[str], None]
ACTIVE_RETRY_RQ_STATUSES = {
    JobStatus.CREATED,
    JobStatus.QUEUED,
    JobStatus.STARTED,
    JobStatus.DEFERRED,
    JobStatus.SCHEDULED,
}
MAX_RETRY_RQ_ATTEMPTS = 1000


def get_redis_connection() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue() -> Queue:
    settings = get_settings()
    return Queue(settings.rq_queue_name, connection=get_redis_connection())


def enqueue_autoclipper_job(job_id: str) -> None:
    queue = get_queue()
    queue.enqueue(run_autoclipper_job, job_id, job_timeout=3600)


def enqueue_autoclipper_retry_job(
    job_id: str,
    terminal_retry_allowed: TerminalRetryAllowed,
) -> None:
    queue = get_queue()
    base_rq_job_id = f"autoclipper_retry_{job_id}"
    terminal_attempt_found = False
    for attempt in range(MAX_RETRY_RQ_ATTEMPTS):
        rq_job_id = base_rq_job_id if attempt == 0 else f"{base_rq_job_id}_{attempt}"
        existing = queue.fetch_job(rq_job_id)
        if existing is not None:
            if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
                return
            terminal_attempt_found = True
            continue
        if terminal_attempt_found and not terminal_retry_allowed():
            return
        try:
            queue.enqueue(
                run_autoclipper_job,
                job_id,
                job_timeout=3600,
                job_id=rq_job_id,
                unique=True,
            )
            return
        except DuplicateJobError:
            existing = queue.fetch_job(rq_job_id)
            if existing is None:
                raise
            if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
                return
            terminal_attempt_found = True
    raise RuntimeError("retry RQ attempt limit exceeded")


def enqueue_subtitle_review_render(job_id: str) -> None:
    queue = get_queue()
    queue.enqueue(run_subtitle_review_render, job_id, job_timeout=3600)


def subtitle_review_preview_rq_job_id(
    job_id: str,
    clip_id: str,
    spec_hash: str,
) -> str:
    return f"subtitle_review_preview-{job_id}-{clip_id}-{spec_hash}"


def enqueue_subtitle_review_preview(
    job_id: str,
    clip_id: str,
    spec_hash: str,
) -> None:
    queue = get_queue()
    rq_job_id = subtitle_review_preview_rq_job_id(job_id, clip_id, spec_hash)
    existing = queue.fetch_job(rq_job_id)
    if existing is not None:
        if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
            return
        # A content-addressed artifact may have been removed after a completed or
        # failed RQ job. Retrying the same immutable spec must reuse the same ID.
        existing.delete()
    try:
        queue.enqueue(
            run_subtitle_review_preview,
            job_id,
            clip_id,
            spec_hash,
            job_timeout=3600,
            job_id=rq_job_id,
            unique=True,
        )
    except DuplicateJobError:
        concurrent = queue.fetch_job(rq_job_id)
        if (
            concurrent is not None
            and concurrent.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES
        ):
            return
        raise


def enqueue_clip_plan_reselection(job_id: str) -> None:
    queue = get_queue()
    queue.enqueue(run_clip_plan_reselection, job_id, job_timeout=3600)


def enqueue_clip_plan_boundary_update(
    job_id: str,
    clip_id: str,
    start: float,
    end: float,
) -> None:
    queue = get_queue()
    queue.enqueue(
        run_clip_plan_boundary_update,
        job_id,
        clip_id,
        start,
        end,
        job_timeout=3600,
    )


def enqueue_clip_plan_hook_scene_update(
    job_id: str,
    clip_id: str,
    start: float | None,
    end: float | None,
) -> None:
    queue = get_queue()
    queue.enqueue(
        run_clip_plan_hook_scene_update,
        job_id,
        clip_id,
        start,
        end,
        job_timeout=3600,
    )


def enqueue_subtitle_review_hook_scene_update(
    job_id: str,
    clip_id: str,
    start: float | None,
    end: float | None,
) -> None:
    queue = get_queue()
    queue.enqueue(
        run_subtitle_review_hook_scene_update,
        job_id,
        clip_id,
        start,
        end,
        job_timeout=3600,
    )


def get_enqueue_job() -> JobEnqueue:
    return enqueue_autoclipper_job


def get_enqueue_retry_job() -> RetryJobEnqueue:
    return enqueue_autoclipper_retry_job


def get_enqueue_clip_plan_reselection() -> ClipPlanReselectionEnqueue:
    return enqueue_clip_plan_reselection


def get_enqueue_clip_plan_boundary_update() -> ClipPlanBoundaryUpdateEnqueue:
    return enqueue_clip_plan_boundary_update


def get_enqueue_clip_plan_hook_scene_update() -> ClipPlanHookSceneUpdateEnqueue:
    return enqueue_clip_plan_hook_scene_update


def get_enqueue_subtitle_review_hook_scene_update() -> SubtitleReviewHookSceneUpdateEnqueue:
    return enqueue_subtitle_review_hook_scene_update


def get_enqueue_subtitle_review_preview() -> SubtitleReviewPreviewEnqueue:
    return enqueue_subtitle_review_preview


def get_enqueue_render_job() -> RenderEnqueue:
    return enqueue_subtitle_review_render
