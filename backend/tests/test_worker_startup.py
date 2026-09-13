import subprocess
from types import SimpleNamespace

import pytest

from app.jobs import worker as worker_module


def test_gpu_preflight_failure_happens_before_rq_worker_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    settings = SimpleNamespace(
        autoclipper_runtime_profile="gpu",
        rq_queue_name="autoclipper",
    )

    def fail_preflight(command: list[str], *, check: bool) -> None:
        events.append("preflight")
        assert command[1:] == [
            "-m",
            "app.audio.gpu_preflight",
            "--device",
            "cuda",
            "--compute-type",
            "float16",
        ]
        assert check is True
        raise subprocess.CalledProcessError(1, command)

    class FakeWorker:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            events.append("worker_init")

        def work(self) -> None:
            events.append("worker_work")

    monkeypatch.setattr(worker_module, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_module.subprocess, "run", fail_preflight)
    monkeypatch.setattr(worker_module, "get_redis_connection", lambda: events.append("redis"))
    monkeypatch.setattr(worker_module, "Worker", FakeWorker)

    with pytest.raises(subprocess.CalledProcessError):
        worker_module.main()

    assert events == ["preflight"]
