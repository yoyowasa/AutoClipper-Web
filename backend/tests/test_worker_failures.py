from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rq import Queue, Worker
from rq.job import Job as RQJob, JobStatus
from rq.timeouts import HorseMonitorTimeoutException
from rq.worker import worker_classes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.jobs import worker, worker_failures
from app.jobs.worker_state import stale_worker_timeout_seconds
from app.models import Job, Video
from app.storage.paths import StoragePaths

NOW = datetime(2026, 10, 7, 1, 0)
MAIN_FUNCTION = "app.jobs.runner.run_autoclipper_job"


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add(Video(id="video", original_filename="test.mp4", stored_path="test.mp4"))
        db.commit()
    yield sessions
    engine.dispose()


def seed(factory, *, identifier="job_test", state="detecting_scenes", age=1801, settings=None, step="シーンを検出中"):
    with factory() as db:
        db.add(Job(id=identifier, video_id="video", status=state, progress=40, current_step=step,
                   settings_json=settings or {}, updated_at=NOW - timedelta(seconds=age)))
        db.commit()
    return identifier


def rq_job(*, function=MAIN_FUNCTION, identifier="job_test", status=JobStatus.FAILED, elapsed=60):
    job = RQJob.create(function, args=(identifier,), connection=Mock(), timeout=3600)
    job.started_at = NOW.replace(tzinfo=UTC) - timedelta(seconds=elapsed)
    job.ended_at = NOW.replace(tzinfo=UTC)
    job.get_status = Mock(return_value=status)
    return job


def queue_with(job=None, *, location="queued"):
    queue = Mock(spec=Queue)
    queue.get_job_ids.return_value = ["rq-id"] if job and location == "queued" else []
    queue.intermediate_queue = SimpleNamespace(get_job_ids=Mock(return_value=["rq-id"] if job and location == "intermediate" else []))
    for kind in ("started", "scheduled", "deferred"):
        registry = SimpleNamespace(get_job_ids=Mock(return_value=["rq-id"] if job and location == kind else []))
        setattr(queue, f"{kind}_job_registry", registry)
    queue.fetch_job.return_value = job
    return queue


def instance(factory, monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", factory)
    value = object.__new__(worker.CharacterAssetWorker)
    value.log = logging.getLogger("test_worker_failures")
    value.name = "test-worker"
    return value


@pytest.mark.parametrize("message,elapsed,code", [
    ("rq.timeouts.JobTimeoutException: Task exceeded maximum timeout", 3600, "worker_timeout"),
    ("Work-horse terminated unexpectedly; waitpid returned 9 (signal 9)", 60, "worker_terminated_unexpectedly"),
    ("Work-horse terminated unexpectedly; waitpid returned None", 3661, "worker_timeout"),
    ("ValueError: invalid input", 60, "worker_execution_failed"),
])
def test_rq_failure_hook_marks_job_failed(factory, monkeypatch, message, elapsed, code):
    seed(factory)
    calls = []
    monkeypatch.setattr(Worker, "handle_job_failure", lambda self, *args: calls.append(args))
    value = instance(factory, monkeypatch)
    value.handle_job_failure(rq_job(elapsed=elapsed), queue_with(), exc_string=message)
    assert len(calls) == 1
    with factory() as db:
        job = db.get(Job, "job_test")
        assert job.status == "failed" and job.progress == 100
        assert job.error_code == code
        assert "シーンを検出中" in job.error_message and "detecting_scenes" in job.error_message
        assert job.current_step == "Failed"


def test_actual_rq_parent_monitor_dispatches_sigkill_to_application_hook(factory, monkeypatch):
    # Run RQ's installed parent monitor, without killing an OS process or using
    # runtime Redis. Only its waitpid result and Redis bookkeeping are replaced.
    seed(factory)
    monkeypatch.setattr(Worker, "handle_job_failure", lambda self, *args: None)
    monkeypatch.setattr(Worker, "handle_work_horse_killed", lambda self, *args: None)
    value = instance(factory, monkeypatch)
    value.wait_for_horse = lambda: (1234, 9, None)
    value.death_penalty_class = lambda *args: nullcontext()
    value.job_monitoring_interval = 30
    value.set_current_job_working_time = Mock()
    value._stopped_job_id = None
    # Windows has no waitpid status helpers; the monitored worker runs on Linux.
    if not hasattr(worker_classes.os, "WIFSIGNALED"):
        monkeypatch.setattr(worker_classes.os, "WIFSIGNALED", lambda value: value == 9, raising=False)
        monkeypatch.setattr(worker_classes.os, "WTERMSIG", lambda value: value, raising=False)
    task = rq_job(status=JobStatus.STARTED)
    task.get_status = Mock(side_effect=[JobStatus.STARTED, JobStatus.FAILED])
    value.monitor_work_horse(task, queue_with())
    with factory() as db:
        assert db.get(Job, "job_test").error_code == "worker_terminated_unexpectedly"


def test_actual_rq_parent_watchdog_timeout_marks_application_failed(factory, monkeypatch):
    seed(factory, state="transcribing", step="文字起こし中")
    monkeypatch.setattr(Worker, "handle_job_failure", lambda self, *args: None)
    monkeypatch.setattr(Worker, "handle_work_horse_killed", lambda self, *args: None)
    times = iter([NOW.replace(tzinfo=UTC), (NOW + timedelta(seconds=3661)).replace(tzinfo=UTC),
                  (NOW + timedelta(seconds=3661)).replace(tzinfo=UTC)])
    monkeypatch.setattr(worker_classes, "now", lambda: next(times))
    value = instance(factory, monkeypatch)
    value.wait_for_horse = Mock(side_effect=[HorseMonitorTimeoutException(), (1234, 9, None)])
    value.death_penalty_class = lambda *args: nullcontext()
    value.job_monitoring_interval = 30
    value.set_current_job_working_time = lambda seconds: setattr(value, "current_job_working_time", seconds)
    value.heartbeat = Mock()
    value.kill_horse = Mock()
    value._stopped_job_id = None
    task = rq_job(status=JobStatus.STARTED)
    task.get_status = Mock(side_effect=[JobStatus.STARTED, JobStatus.FAILED])
    value.monitor_work_horse(task, queue_with())
    value.kill_horse.assert_called_once()
    with factory() as db:
        assert db.get(Job, "job_test").error_code == "worker_timeout"
        assert "文字起こし中" in db.get(Job, "job_test").error_message


@pytest.mark.parametrize("state", ["completed", "failed", "awaiting_clip_review", "awaiting_subtitle_review"])
def test_failure_preserves_terminal_and_review_states(factory, state):
    seed(factory, state=state)
    with factory() as db:
        assert not worker_failures.mark_rq_failure(db, rq_job(), "ValueError")
    with factory() as db:
        assert db.get(Job, "job_test").status == state
        assert db.get(Job, "job_test").error_code is None


@pytest.mark.parametrize("function", [
    "app.jobs.thumbnail_regeneration.run_export_thumbnail_regeneration",
    "app.jobs.thumbnail_copy.run_thumbnail_copy_generation",
    "app.jobs.thumbnail_candidates.run_thumbnail_candidate_extraction",
    "app.jobs.character_asset_harvest.run_character_asset_harvest",
    *sorted(worker_failures.PARTIAL_JOB_FUNCTIONS),
])
def test_individual_clip_or_thumbnail_failure_does_not_fail_parent_job(factory, function):
    seed(factory)
    with factory() as db:
        assert not worker_failures.mark_rq_failure(db, rq_job(function=function), "JobTimeoutException")
    with factory() as db:
        assert db.get(Job, "job_test").status == "detecting_scenes"


@pytest.mark.parametrize("function", sorted(worker_failures.WHOLE_JOB_FUNCTIONS))
def test_whole_job_function_paths_including_old_rq_alias(factory, function):
    seed(factory)
    with factory() as db:
        assert worker_failures.mark_rq_failure(db, rq_job(function=function), "ValueError")


def test_rq_retry_is_not_terminal(factory, monkeypatch):
    seed(factory)
    monkeypatch.setattr(Worker, "handle_job_failure", lambda self, *args: None)
    instance(factory, monkeypatch).handle_job_failure(rq_job(status=JobStatus.QUEUED), queue_with(), exc_string="ValueError")
    with factory() as db:
        assert db.get(Job, "job_test").status == "detecting_scenes"


@pytest.mark.parametrize("changed_status", ["completed", "transcribing"])
def test_conditional_update_protects_concurrent_completion_or_heartbeat(factory, changed_status):
    seed(factory)
    with factory() as stale:
        original = stale.get(Job, "job_test")
        with factory() as newer:
            job = newer.get(Job, "job_test")
            job.status = changed_status
            job.updated_at = NOW
            newer.commit()
        assert not worker_failures.mark_rq_failure(stale, rq_job(), "ValueError")
        assert original.status == "detecting_scenes"
    with factory() as db:
        assert db.get(Job, "job_test").status == changed_status


@pytest.mark.parametrize("location", ["queued", "started", "intermediate", "scheduled", "deferred"])
def test_maintenance_preserves_registered_work(factory, location):
    seed(factory)
    queue = queue_with(rq_job(), location=location)
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue], now=NOW) == []
    for kind in ("started", "scheduled", "deferred"):
        getattr(queue, f"{kind}_job_registry").get_job_ids.assert_called_once_with(cleanup=False)
    with factory() as db:
        assert db.get(Job, "job_test").status == "detecting_scenes"


@pytest.mark.parametrize("state,age,settings", [
    ("detecting_scenes", 1800, {}), ("transcribing", 1801, {"workerHeartbeatTimeoutSeconds": 3600}),
    ("selecting_clips", 60, {"workerHeartbeatTimeoutSeconds": 1}),
    ("completed", 999999, {}), ("failed", 999999, {}), ("queued", 999999, {}),
    ("uploaded", 999999, {}), ("awaiting_clip_review", 999999, {}),
    ("awaiting_subtitle_review", 999999, {}), ("awaiting_manual_edit", 999999, {}),
])
def test_maintenance_skips_fresh_or_nonrunning_jobs(factory, state, age, settings):
    seed(factory, state=state, age=age, settings=settings)
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue_with()], now=NOW) == []
    with factory() as db:
        assert db.get(Job, "job_test").status == state


@pytest.mark.parametrize("settings,expected", [({}, 1800), ({"workerHeartbeatTimeoutSeconds": "bad"}, 1800),
                                                        ({"workerHeartbeatTimeoutSeconds": None}, 1800),
                                                        ({"workerHeartbeatTimeoutSeconds": 1}, 60)])
def test_shared_heartbeat_policy(settings, expected):
    assert stale_worker_timeout_seconds(settings) == expected


def test_maintenance_fails_stale_orphan_and_names_stopped_step(factory):
    identifier = seed(factory, identifier="job_ea68be9806884d25aaa3dbd62a259f24", age=5 * 86400)
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue_with()], now=NOW) == [identifier]
    with factory() as db:
        job = db.get(Job, identifier)
        assert job.status == "failed" and job.error_code == "worker_terminated_unexpectedly"
        assert "detecting_scenes" in job.error_message and "シーンを検出中" in job.error_message


@pytest.mark.parametrize("state,step", sorted(worker_failures.PARTIAL_REVIEW_STEPS))
def test_maintenance_does_not_fail_one_clip_preview_operation(factory, state, step):
    seed(factory, state=state, step=step)
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue_with()], now=NOW) == []


def test_active_partial_preview_protects_parent(factory):
    seed(factory, state="preparing_subtitle_review")
    queue = queue_with(rq_job(function="app.jobs.runner.run_subtitle_review_preview"), location="started")
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue], now=NOW) == []


def test_maintenance_rechecks_queue_for_concurrent_enqueue(factory):
    seed(factory)
    queue = queue_with(rq_job())
    queue.get_job_ids.side_effect = [[], ["rq-id"]]
    with factory() as db:
        assert worker_failures.reconcile_orphaned_jobs(db, [queue], now=NOW) == []


@pytest.mark.parametrize("unreadable", [False, True])
def test_maintenance_fails_closed_when_redis_or_active_entry_is_unreadable(factory, unreadable):
    seed(factory)
    queue = queue_with(rq_job())
    if unreadable:
        queue.fetch_job.return_value = None
    else:
        queue.get_job_ids.side_effect = ConnectionError("unavailable")
    with factory() as db, pytest.raises((ConnectionError, RuntimeError)):
        worker_failures.reconcile_orphaned_jobs(db, [queue], now=NOW)
    with factory() as db:
        assert db.get(Job, "job_test").status == "detecting_scenes"


def test_worker_maintenance_runs_reconciliation_and_preserves_existing_cleanup(factory, monkeypatch, tmp_path):
    seed(factory)
    value = instance(factory, monkeypatch)
    value.queues = [queue_with()]
    monkeypatch.setattr(Worker, "run_maintenance_tasks", lambda self: None)
    monkeypatch.setattr(worker_failures, "utc_now", lambda: NOW)
    monkeypatch.setattr(worker, "get_storage_paths", lambda: StoragePaths(tmp_path))
    cleanup = Mock()
    monkeypatch.setattr(worker, "expire_candidates", cleanup)
    value.run_maintenance_tasks()
    cleanup.assert_called_once()
    with factory() as db:
        assert db.get(Job, "job_test").status == "failed"
