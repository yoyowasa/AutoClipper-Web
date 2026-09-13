from collections.abc import Callable

from redis import Redis
from rq import Queue, Retry
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
from app.jobs.title_hook_suggestions import run_title_hook_suggestion_generation
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.jobs.thumbnail_copy import run_thumbnail_copy_generation

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
TitleHookSuggestionsEnqueue = Callable[[str, str, str], None]
RenderEnqueue = Callable[[str, int], None]
ThumbnailRegenerationEnqueue = Callable[[str, int], None]
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


def subtitle_review_render_rq_job_id(
    job_id: str,
    render_revision: int,
    attempt: int = 0,
) -> str:
    base_rq_job_id = f"subtitle_review_render-{job_id}-r{render_revision}"
    return base_rq_job_id if attempt == 0 else f"{base_rq_job_id}-a{attempt}"


def enqueue_subtitle_review_render(job_id: str, render_revision: int) -> None:
    queue = get_queue()
    for attempt in range(MAX_RETRY_RQ_ATTEMPTS):
        rq_job_id = subtitle_review_render_rq_job_id(
            job_id,
            render_revision,
            attempt,
        )
        existing = queue.fetch_job(rq_job_id)
        if existing is not None:
            if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
                return
            continue
        try:
            queue.enqueue(
                run_subtitle_review_render,
                job_id,
                render_revision=render_revision,
                job_timeout=3600,
                job_id=rq_job_id,
                retry=Retry(max=2),
                unique=True,
            )
            return
        except DuplicateJobError:
            concurrent = queue.fetch_job(rq_job_id)
            if concurrent is None:
                raise
            if concurrent.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
                return
    raise RuntimeError("subtitle render RQ attempt limit exceeded")


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


def title_hook_suggestions_rq_job_id(
    job_id: str,
    clip_id: str,
    input_hash: str,
) -> str:
    return f"ai_title_hook-{job_id}-{clip_id}-{input_hash}"


def enqueue_title_hook_suggestions(
    job_id: str,
    clip_id: str,
    input_hash: str,
) -> None:
    queue = get_queue()
    rq_job_id = title_hook_suggestions_rq_job_id(job_id, clip_id, input_hash)
    existing = queue.fetch_job(rq_job_id)
    if existing is not None:
        if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
            return
        existing.delete()
    try:
        queue.enqueue(
            run_title_hook_suggestion_generation,
            job_id,
            clip_id,
            input_hash,
            job_timeout=900,
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


def enqueue_export_thumbnail_regeneration(export_id: str, revision: int) -> None:
    queue = get_queue()
    rq_job_id = f"thumbnail-regeneration-{export_id}-r{revision}"
    existing = queue.fetch_job(rq_job_id)
    if existing is not None:
        if existing.get_status(refresh=True) in ACTIVE_RETRY_RQ_STATUSES:
            return
        existing.delete()
    try:
        queue.enqueue(
            run_export_thumbnail_regeneration,
            export_id,
            revision,
            job_timeout=900,
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


def get_enqueue_title_hook_suggestions() -> TitleHookSuggestionsEnqueue:
    return enqueue_title_hook_suggestions


def get_enqueue_render_job() -> RenderEnqueue:
    return enqueue_subtitle_review_render


def get_enqueue_thumbnail_regeneration() -> ThumbnailRegenerationEnqueue:
    return enqueue_export_thumbnail_regeneration


def enqueue_thumbnail_copy(export_id: str, request_id: str) -> None:
    get_queue().enqueue(run_thumbnail_copy_generation, export_id, request_id, job_timeout=360, job_id=f"thumbnail-copy-{request_id}")


def get_enqueue_thumbnail_copy() -> Callable[[str, str], None]:
    return enqueue_thumbnail_copy


def enqueue_thumbnail_preview(export_id: str, request_id: str) -> None:
    from app.jobs.thumbnail_preview import run_thumbnail_preview_prepare
    get_queue().enqueue(run_thumbnail_preview_prepare, export_id, request_id, job_timeout=60, job_id=f"thumbnail-preview-{request_id}")


def get_enqueue_thumbnail_preview() -> Callable[[str, str], None]:
    return enqueue_thumbnail_preview
