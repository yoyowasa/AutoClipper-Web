import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.storage.json_io import write_json_atomic


def test_write_json_atomic_preserves_format_and_removes_temp(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "artifact.json"
    payload = {"title": "日本語", "values": [1, 2]}

    assert write_json_atomic(path, payload) == path
    assert path.read_text(encoding="utf-8") == json.dumps(
        payload, ensure_ascii=False, indent=2
    ) + "\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))

    assert write_json_atomic(path, payload, indent=None, separators=(",", ":")) == path
    assert path.read_text(encoding="utf-8") == json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_write_json_atomic_removes_temp_after_replace_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "artifact.json"
    original = '{"previous": true}\n'
    path.write_text(original, encoding="utf-8")

    def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise OSError("replace failed")

    with monkeypatch.context() as patch:
        patch.setattr("app.storage.json_io.os.replace", fail_replace)
        with pytest.raises(OSError, match="replace failed"):
            write_json_atomic(path, {"next": True})

    assert path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


def test_concurrent_writes_leave_one_complete_json_document(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "artifact.json"
    payloads = [
        {"writer": "first", "text": "あ" * 10000},
        {"writer": "second", "text": "い" * 10000},
    ]
    barrier = Barrier(3)

    def write_after_barrier(payload: dict[str, str]) -> Path:
        barrier.wait(timeout=15)
        return write_json_atomic(path, payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write_after_barrier, payload) for payload in payloads]
        barrier.wait(timeout=15)
        assert [future.result(timeout=30) for future in futures] == [path, path]

    assert json.loads(path.read_text(encoding="utf-8")) in payloads
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
