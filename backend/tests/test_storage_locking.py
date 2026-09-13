from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from app.storage.locking import storage_mutation_lock


def test_storage_mutation_lock_serializes_threads(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def hold_first_lock() -> None:
        with storage_mutation_lock(storage_root):
            first_entered.set()
            assert release_first.wait(timeout=5)

    def wait_for_lock() -> None:
        assert first_entered.wait(timeout=5)
        with storage_mutation_lock(storage_root):
            second_entered.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(hold_first_lock)
        assert first_entered.wait(timeout=5)
        second = executor.submit(wait_for_lock)
        assert not second_entered.wait(timeout=0.2)
        release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert second_entered.is_set()
