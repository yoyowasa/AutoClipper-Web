from __future__ import annotations

import errno
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4


RERENDER_PUBLICATION_UNRESOLVED_FILENAME = ".rerender_publication_unresolved"
RERENDER_PUBLICATION_LEASE_FILENAME = ".rerender_publication.lease"


def rerender_publication_lease_path(job_dir: Path) -> Path:
    return job_dir / RERENDER_PUBLICATION_LEASE_FILENAME


def _try_lock_lease_file(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _unlock_lease_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass
class RerenderPublicationLease:
    attempt_id: str
    job_id: str
    render_revision: int
    path: Path
    _handle: BinaryIO | None = field(repr=False)

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            _unlock_lease_file(handle)
        finally:
            handle.close()

    def __enter__(self) -> RerenderPublicationLease:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.release()


def _open_rerender_publication_lease(path: Path) -> BinaryIO:
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        handle = os.fdopen(descriptor, "r+b")
    except Exception:
        os.close(descriptor)
        raise
    handle.seek(0)
    return handle


def _write_rerender_publication_lease_payload(
    handle: BinaryIO,
    *,
    job_id: str,
    render_revision: int,
    attempt_id: str,
) -> None:
    payload = (
        json.dumps(
            {
                "version": 1,
                "jobId": job_id,
                "renderRevision": render_revision,
                "attemptId": attempt_id,
                "acquiredAt": datetime.now(UTC).isoformat(),
                "processId": os.getpid(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    handle.seek(0)
    handle.write(payload)
    handle.truncate()
    handle.flush()


def try_acquire_rerender_publication_lease(
    job_dir: Path,
    *,
    job_id: str,
    render_revision: int,
) -> RerenderPublicationLease | None:
    path = rerender_publication_lease_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = _open_rerender_publication_lease(path)
    try:
        if not _try_lock_lease_file(handle):
            handle.close()
            return None
        lease = RerenderPublicationLease(
            attempt_id=uuid4().hex,
            job_id=job_id,
            render_revision=render_revision,
            path=path,
            _handle=handle,
        )
        try:
            _write_rerender_publication_lease_payload(
                handle,
                job_id=job_id,
                render_revision=render_revision,
                attempt_id=lease.attempt_id,
            )
        except Exception:
            lease.release()
            raise
        return lease
    except Exception:
        if not handle.closed:
            handle.close()
        raise


def rerender_publication_marker_path(job_dir: Path) -> Path:
    return job_dir / RERENDER_PUBLICATION_UNRESOLVED_FILENAME


def rerender_publication_is_unresolved(job_dir: Path) -> bool:
    return rerender_publication_marker_path(job_dir).exists()


def mark_rerender_publication_unresolved(
    job_dir: Path,
    *,
    job_id: str,
    render_revision: int,
    attempt_id: str,
) -> Path:
    marker = rerender_publication_marker_path(job_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(f"{marker.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                {
                    "version": 2,
                    "jobId": job_id,
                    "renderRevision": render_revision,
                    "attemptId": attempt_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(marker)
    finally:
        temporary.unlink(missing_ok=True)
    return marker


def clear_rerender_publication_unresolved(
    job_dir: Path,
    *,
    expected_attempt_id: str | None = None,
) -> bool:
    marker = rerender_publication_marker_path(job_dir)
    if expected_attempt_id is not None:
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError, UnicodeError, ValueError):
            return False
        if not isinstance(payload, dict) or payload.get("attemptId") != expected_attempt_id:
            return False
    try:
        marker.unlink()
    except FileNotFoundError:
        return False
    return True
