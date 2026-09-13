from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import BinaryIO

import pytest

from app.jobs import publication_state


def test_try_acquire_locks_empty_file_before_writing_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_before_lock: list[bytes] = []

    def observe_and_reject_lock(handle: BinaryIO) -> bool:
        handle.seek(0)
        observed_before_lock.append(handle.read())
        return False

    monkeypatch.setattr(
        publication_state,
        "_try_lock_lease_file",
        observe_and_reject_lock,
    )
    job_dir = tmp_path / "job"

    lease = publication_state.try_acquire_rerender_publication_lease(
        job_dir,
        job_id="job_empty_lock",
        render_revision=2,
    )

    assert lease is None
    assert observed_before_lock == [b""]
    assert publication_state.rerender_publication_lease_path(job_dir).read_bytes() == b""


@pytest.mark.parametrize(
    "error_number",
    [publication_state.errno.EACCES, publication_state.errno.EAGAIN],
)
def test_windows_lease_busy_errors_return_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    def raise_busy(*_args: object) -> None:
        raise OSError(error_number, "busy")

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, locking=raise_busy)
    monkeypatch.setattr(publication_state.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    with (tmp_path / "lease").open("w+b") as handle:
        assert publication_state._try_lock_lease_file(handle) is False


def test_windows_lease_unexpected_error_is_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unexpected(*_args: object) -> None:
        raise OSError(publication_state.errno.EIO, "unexpected")

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, locking=raise_unexpected)
    monkeypatch.setattr(publication_state.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    with (tmp_path / "lease").open("w+b") as handle:
        with pytest.raises(OSError, match="unexpected"):
            publication_state._try_lock_lease_file(handle)


def test_rerender_publication_lease_is_nonblocking_and_reusable(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "job"
    first = publication_state.try_acquire_rerender_publication_lease(
        job_dir,
        job_id="job_lease",
        render_revision=2,
    )
    assert first is not None

    competing = publication_state.try_acquire_rerender_publication_lease(
        job_dir,
        job_id="job_lease",
        render_revision=2,
    )
    assert competing is None

    first_attempt_id = first.attempt_id
    first.release()
    first.release()
    payload = json.loads(first.path.read_text(encoding="utf-8"))
    acquired_at = datetime.fromisoformat(payload.pop("acquiredAt"))
    assert acquired_at.tzinfo == UTC
    assert payload == {
        "version": 1,
        "jobId": "job_lease",
        "renderRevision": 2,
        "attemptId": first_attempt_id,
        "processId": publication_state.os.getpid(),
    }

    second = publication_state.try_acquire_rerender_publication_lease(
        job_dir,
        job_id="job_lease",
        render_revision=2,
    )
    assert second is not None
    assert second.attempt_id != first_attempt_id
    second.release()


def test_rerender_publication_lease_is_released_after_process_death(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "job"
    ready_path = tmp_path / "lease-ready"
    backend_root = Path(publication_state.__file__).resolve().parents[2]
    script = """
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from app.jobs.publication_state import try_acquire_rerender_publication_lease

lease = try_acquire_rerender_publication_lease(
    Path(sys.argv[1]),
    job_id="job_process_death",
    render_revision=4,
)
if lease is None:
    raise RuntimeError("lease was not acquired")
Path(sys.argv[3]).write_text(lease.attempt_id, encoding="ascii")
time.sleep(30)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(job_dir),
            str(backend_root),
            str(ready_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    acquired_after_death = None
    try:
        deadline = time.monotonic() + 10
        while not ready_path.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                pytest.fail("child process did not acquire the lease")
            time.sleep(0.02)
        if not ready_path.exists():
            stderr = process.stderr.read() if process.stderr is not None else ""
            pytest.fail(f"child process exited before acquiring the lease: {stderr}")

        assert (
            publication_state.try_acquire_rerender_publication_lease(
                job_dir,
                job_id="job_process_death",
                render_revision=4,
            )
            is None
        )

        process.terminate()
        process.wait(timeout=10)
        release_deadline = time.monotonic() + 5
        while acquired_after_death is None:
            acquired_after_death = publication_state.try_acquire_rerender_publication_lease(
                job_dir,
                job_id="job_process_death",
                render_revision=4,
            )
            if acquired_after_death is not None or time.monotonic() >= release_deadline:
                break
            time.sleep(0.02)
        assert acquired_after_death is not None
    finally:
        if acquired_after_death is not None:
            acquired_after_death.release()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_marker_clear_requires_matching_attempt_owner(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    marker = publication_state.mark_rerender_publication_unresolved(
        job_dir,
        job_id="job_marker",
        render_revision=5,
        attempt_id="attempt-owner",
    )
    original = marker.read_bytes()
    assert json.loads(original) == {
        "version": 2,
        "jobId": "job_marker",
        "renderRevision": 5,
        "attemptId": "attempt-owner",
    }

    assert (
        publication_state.clear_rerender_publication_unresolved(
            job_dir,
            expected_attempt_id="attempt-other",
        )
        is False
    )
    assert marker.read_bytes() == original
    assert (
        publication_state.clear_rerender_publication_unresolved(
            job_dir,
            expected_attempt_id="attempt-owner",
        )
        is True
    )
    assert not marker.exists()
    assert (
        publication_state.clear_rerender_publication_unresolved(
            job_dir,
            expected_attempt_id="attempt-owner",
        )
        is False
    )


def test_owner_clear_preserves_legacy_marker_bytes(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    marker = publication_state.rerender_publication_marker_path(job_dir)
    marker.parent.mkdir(parents=True)
    legacy = b'{"jobId":"job_marker","renderRevision":2,"version":1}\n'
    marker.write_bytes(legacy)

    assert (
        publication_state.clear_rerender_publication_unresolved(
            job_dir,
            expected_attempt_id="attempt-current",
        )
        is False
    )
    assert marker.read_bytes() == legacy

    assert publication_state.clear_rerender_publication_unresolved(job_dir) is True
    assert not marker.exists()
