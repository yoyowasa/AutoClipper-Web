import re
from typing import Any

import pytest
from rq.exceptions import DuplicateJobError
from rq.job import JobStatus

from app.jobs import queue as queue_module


class FakeJob:
    def __init__(self, status: JobStatus) -> None:
        self.status = status
        self.deleted = False

    def get_status(self, *, refresh: bool = True) -> JobStatus:
        assert refresh is True
        return self.status

    def delete(self) -> None:
        self.deleted = True


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: dict[str, FakeJob] = {}
        self.calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []
        self.duplicate_on_next_enqueue = False

    def fetch_job(self, job_id: str) -> FakeJob | None:
        return self.jobs.get(job_id)

    def enqueue(self, function: Any, *args: Any, **kwargs: Any) -> None:
        self.calls.append((function, args, kwargs))
        job_id = str(kwargs["job_id"])
        if self.duplicate_on_next_enqueue:
            self.duplicate_on_next_enqueue = False
            self.jobs[job_id] = FakeJob(JobStatus.QUEUED)
            raise DuplicateJobError()
        self.jobs[job_id] = FakeJob(JobStatus.QUEUED)


def test_retry_enqueue_uses_unique_rq_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue()
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_autoclipper_retry_job("job_retry", lambda: False)

    assert len(queue.calls) == 1
    function, args, kwargs = queue.calls[0]
    assert function is queue_module.run_autoclipper_job
    assert args == ("job_retry",)
    assert kwargs["job_id"] == "autoclipper_retry_job_retry"
    assert kwargs["unique"] is True
    assert kwargs["job_timeout"] == 3600


def test_retry_enqueue_keeps_active_rq_job(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue()
    queue.jobs["autoclipper_retry_job_retry"] = FakeJob(JobStatus.STARTED)
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_autoclipper_retry_job("job_retry", lambda: False)

    assert queue.calls == []


@pytest.mark.parametrize(
    "terminal_status",
    [JobStatus.FINISHED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED],
)
def test_retry_enqueue_uses_next_attempt_after_terminal_rq_job(
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: JobStatus,
) -> None:
    queue = FakeQueue()
    queue.jobs["autoclipper_retry_job_retry"] = FakeJob(terminal_status)
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_autoclipper_retry_job("job_retry", lambda: True)

    assert len(queue.calls) == 1
    assert queue.calls[0][2]["job_id"] == "autoclipper_retry_job_retry_1"


def test_retry_enqueue_resolves_concurrent_duplicate_as_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = FakeQueue()
    queue.duplicate_on_next_enqueue = True
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_autoclipper_retry_job("job_retry", lambda: False)

    assert len(queue.calls) == 1
    assert queue.fetch_job("autoclipper_retry_job_retry") is not None


def test_retry_enqueue_does_not_replace_terminal_job_when_db_disallows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = FakeQueue()
    queue.jobs["autoclipper_retry_job_retry"] = FakeJob(JobStatus.FINISHED)
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_autoclipper_retry_job("job_retry", lambda: False)

    assert queue.calls == []


def test_subtitle_preview_enqueue_uses_content_addressed_unique_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = FakeQueue()
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)
    spec_hash = "a" * 64

    queue_module.enqueue_subtitle_review_preview(
        "job_preview",
        "candidate_short_1",
        spec_hash,
    )

    assert len(queue.calls) == 1
    function, args, kwargs = queue.calls[0]
    assert function is queue_module.run_subtitle_review_preview
    assert args == ("job_preview", "candidate_short_1", spec_hash)
    assert kwargs["job_id"] == (
        "subtitle_review_preview-job_preview-candidate_short_1-" + spec_hash
    )
    assert re.fullmatch(r"[A-Za-z0-9_-]+", kwargs["job_id"])
    assert kwargs["unique"] is True
    assert kwargs["job_timeout"] == 3600


def test_subtitle_preview_enqueue_keeps_active_same_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = FakeQueue()
    spec_hash = "b" * 64
    rq_job_id = queue_module.subtitle_review_preview_rq_job_id(
        "job_preview",
        "candidate_short_1",
        spec_hash,
    )
    queue.jobs[rq_job_id] = FakeJob(JobStatus.STARTED)
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_subtitle_review_preview(
        "job_preview",
        "candidate_short_1",
        spec_hash,
    )

    assert queue.calls == []


def test_subtitle_preview_enqueue_reuses_id_after_terminal_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = FakeQueue()
    spec_hash = "c" * 64
    rq_job_id = queue_module.subtitle_review_preview_rq_job_id(
        "job_preview",
        "candidate_short_1",
        spec_hash,
    )
    old_job = FakeJob(JobStatus.FAILED)
    queue.jobs[rq_job_id] = old_job
    monkeypatch.setattr(queue_module, "get_queue", lambda: queue)

    queue_module.enqueue_subtitle_review_preview(
        "job_preview",
        "candidate_short_1",
        spec_hash,
    )

    assert old_job.deleted is True
    assert len(queue.calls) == 1
    assert queue.calls[0][2]["job_id"] == rq_job_id
