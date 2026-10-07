"""Publish terminal RQ failures and reconcile abandoned application jobs."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from rq import Queue
from rq.job import Job as RQJob
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.jobs.worker_state import RUNNING_STATUSES, stale_worker_timeout_seconds
from app.models import Job, utc_now

# Match function paths without importing/performing the queued function. Include
# the runner aliases used by RQ jobs queued before task-167.
WHOLE_JOB_FUNCTIONS = frozenset({
    "app.jobs.runner.run_autoclipper_job",
    "app.jobs.runner.run_subtitle_review_render",
    "app.jobs.runner.run_clip_plan_reselection",
    "app.jobs.clip_plan_runner.run_clip_plan_reselection",
})
PARTIAL_JOB_FUNCTIONS = frozenset({
    "app.jobs.runner.run_subtitle_review_preview",
    "app.jobs.runner.run_subtitle_review_hook_scene_update",
    "app.jobs.runner.run_clip_plan_boundary_update",
    "app.jobs.runner.run_clip_plan_hook_scene_update",
    "app.jobs.clip_plan_runner.run_clip_plan_boundary_update",
    "app.jobs.clip_plan_runner.run_clip_plan_hook_scene_update",
    "app.jobs.title_hook_suggestions.run_title_hook_suggestion_generation",
})
# These operations deliberately prepare one clip while retaining the review
# workflow. Losing their preview must not fail the entire application job.
PARTIAL_REVIEW_STEPS = frozenset({
    ("preparing_clip_review", "調整した範囲の確認動画を準備中"),
    ("preparing_clip_review", "冒頭フック映像の確認動画を準備中"),
    ("preparing_clip_review", "切り抜きの種類を変更中"),
    ("preparing_subtitle_review", "冒頭フック映像の確認動画を準備中"),
})


def application_job_id(rq_job: RQJob, *, whole_only: bool = False) -> str | None:
    functions = WHOLE_JOB_FUNCTIONS if whole_only else WHOLE_JOB_FUNCTIONS | PARTIAL_JOB_FUNCTIONS
    if rq_job.func_name not in functions:
        return None
    value = rq_job.args[0] if rq_job.args else rq_job.kwargs.get("job_id")
    return value if isinstance(value, str) and value.startswith("job_") else None


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value


def rq_failure_code(rq_job: RQJob, exc_string: str) -> str:
    if "JobTimeoutException" in exc_string:
        return "worker_timeout"
    if "Work-horse terminated" in exc_string or "work-horse terminated" in exc_string:
        # RQ's parent-side watchdog uses SIGKILL if the child cannot handle its
        # timeout signal. Its message has no JobTimeoutException in that case.
        if rq_job.timeout and rq_job.timeout > 0 and rq_job.started_at is not None:
            ended = rq_job.ended_at or datetime.now(UTC)
            elapsed = (_naive_utc(ended) - _naive_utc(rq_job.started_at)).total_seconds()
            if elapsed >= rq_job.timeout:
                return "worker_timeout"
        return "worker_terminated_unexpectedly"
    return "worker_execution_failed"


def _mark_failed(db: Session, job: Job, *, code: str, explanation: str, now: datetime) -> bool:
    previous_status = job.status
    previous_step = job.current_step
    result = db.execute(
        update(Job).where(
            Job.id == job.id, Job.status == previous_status, Job.updated_at == job.updated_at,
            Job.current_step == previous_step, Job.status.in_(RUNNING_STATUSES | {"queued"}),
        ).values(
            status="failed", progress=100, current_step="Failed", error_code=code,
            error_message=f"{explanation} 停止した処理: {previous_step or previous_status}（状態: {previous_status}）。",
            updated_at=now,
        ), execution_options={"synchronize_session": False},
    )
    db.commit()
    return result.rowcount == 1


def mark_rq_failure(db: Session, rq_job: RQJob, exc_string: str) -> bool:
    identifier = application_job_id(rq_job, whole_only=True)
    job = db.get(Job, identifier) if identifier else None
    if job is None or job.status not in RUNNING_STATUSES | {"queued"}:
        return False
    code = rq_failure_code(rq_job, exc_string)
    explanation = {
        "worker_timeout": "処理の制限時間を超えたため、workerの仕事が終了しました。",
        "worker_terminated_unexpectedly": "workerの処理プロセスが強制終了しました。",
        "worker_execution_failed": "workerの仕事が例外で失敗しました。",
    }[code]
    return _mark_failed(db, job, code=code, explanation=explanation, now=utc_now())


def active_application_jobs(queues: Sequence[Queue]) -> set[str]:
    active: set[str] = set()
    for queue in queues:
        # No registry cleanup here: even expired registrations are protected
        # until RQ itself has reconciled them. Protect the dequeue/start gap and
        # scheduled/deferred retries as well as the queue and running registry.
        identifiers = set(queue.get_job_ids()) | set(queue.intermediate_queue.get_job_ids())
        for registry in (queue.started_job_registry, queue.scheduled_job_registry, queue.deferred_job_registry):
            identifiers.update(registry.get_job_ids(cleanup=False))
        for identifier in identifiers:
            rq_job = queue.fetch_job(identifier)
            if rq_job is None:
                raise RuntimeError("An active RQ entry could not be inspected; orphan reconciliation skipped")
            app_id = application_job_id(rq_job)
            if app_id:
                active.add(app_id)
    return active


def reconcile_orphaned_jobs(db: Session, queues: Sequence[Queue], *, now: datetime | None = None) -> list[str]:
    timestamp = now or utc_now()
    active = active_application_jobs(queues)  # Fail closed if Redis cannot be inspected.
    failed: list[str] = []
    jobs = db.scalars(select(Job).where(Job.status.in_(RUNNING_STATUSES))).all()
    for job in jobs:
        if job.status not in RUNNING_STATUSES or (job.status, job.current_step) in PARTIAL_REVIEW_STEPS or job.id in active:
            continue
        timeout = stale_worker_timeout_seconds(job.settings_json or {})
        if timestamp - job.updated_at <= timedelta(seconds=timeout):
            continue
        # Re-read Redis immediately before the conditional UPDATE; a retry may
        # have been enqueued while the database candidates were being read.
        if job.id in active_application_jobs(queues):
            continue
        if _mark_failed(
            db, job, code="worker_terminated_unexpectedly",
            explanation=f"最終更新から{timeout}秒を超え、対応するworkerの仕事が見つかりません。",
            now=timestamp,
        ):
            failed.append(job.id)
    return failed
