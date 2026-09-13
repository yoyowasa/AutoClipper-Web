from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import time


LOCK_FILENAME = ".storage-lifecycle.lock"
LOCK_RETRY_SECONDS = 0.05


@contextmanager
def storage_mutation_lock(storage_root: Path) -> Iterator[None]:
    storage_root.mkdir(parents=True, exist_ok=True)
    lock_path = storage_root / LOCK_FILENAME
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(LOCK_RETRY_SECONDS)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
