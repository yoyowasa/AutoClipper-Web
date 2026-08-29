import os
from pathlib import Path

import pytest

from app.storage.usage import StorageUsage, measure_storage_usage, storage_warning_reasons


def test_measure_storage_usage_counts_hardlinked_content_once(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    blob = root / "blob"
    blob.write_bytes(b"shared-content")
    os.link(blob, root / "video.mp4")
    (root / "metadata.json").write_bytes(b"{}")

    usage = measure_storage_usage(root)

    assert usage.storage_bytes == len(b"shared-content") + len(b"{}")
    assert usage.disk_total_bytes > 0
    assert usage.disk_free_bytes > 0


def test_storage_warning_boundaries() -> None:
    usage = StorageUsage(
        storage_bytes=50,
        disk_total_bytes=100,
        disk_free_bytes=20,
        disk_free_percent=20.0,
    )

    assert storage_warning_reasons(
        usage,
        storage_limit_bytes=50,
        minimum_free_percent=20.0,
    ) == ()

    over_limit = StorageUsage(51, 100, 20, 20.0)
    low_disk = StorageUsage(50, 100, 19, 19.0)
    assert len(
        storage_warning_reasons(
            over_limit,
            storage_limit_bytes=50,
            minimum_free_percent=20.0,
        )
    ) == 1
    assert len(
        storage_warning_reasons(
            low_disk,
            storage_limit_bytes=50,
            minimum_free_percent=20.0,
        )
    ) == 1


def test_measure_storage_usage_includes_source_library(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    source_library = tmp_path / "youtube"
    storage.mkdir()
    source_library.mkdir()
    (storage / "work.bin").write_bytes(b"work")
    (source_library / "source.mp4").write_bytes(b"source")

    usage = measure_storage_usage(storage, additional_roots=(source_library,))

    assert usage.storage_bytes == len(b"work") + len(b"source")


def test_measure_storage_usage_skips_unreadable_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = tmp_path / "storage"
    blocked = storage / "blocked"
    blocked.mkdir(parents=True)
    (storage / "readable.bin").write_bytes(b"readable")
    original_scandir = os.scandir

    def fail_blocked_directory(path: str | os.PathLike[str]):
        if Path(path) == blocked:
            raise OSError(5, "input/output error")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", fail_blocked_directory)

    usage = measure_storage_usage(storage)

    assert usage.storage_bytes == len(b"readable")
    assert usage.scan_error_count == 1
    assert storage_warning_reasons(
        usage,
        storage_limit_bytes=1024,
        minimum_free_percent=0,
    ) == ("一部の保存先を読み取れないため、使用量は参考値です。",)
