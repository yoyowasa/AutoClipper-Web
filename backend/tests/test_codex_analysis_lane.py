from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import signal
import sys
import threading
import time
from uuid import uuid4
from types import SimpleNamespace

import pytest

from app.intelligence.analysis_schema import analysis_response_schema
from test_codex_host_bridge import request_payload, suggestion_result
from launcher import codex_bridge as bridge


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT", str(tmp_path / "private"))
    monkeypatch.setattr(bridge, "find_codex_executable", lambda: "synthetic-codex")
    monkeypatch.setattr(bridge, "codex_login_configured", lambda _: True)
    paths = bridge.bridge_paths(tmp_path)
    bridge.ensure_bridge_directories(paths)
    return SimpleNamespace(root=tmp_path, paths=paths)


def analysis_request(environment, id="1" * 32, *, directory=None):
    payload = {"schemaVersion": 1, "task": "channel_self_analysis", "requestId": id,
        "prompt": "synthetic analysis", "responseSchema": analysis_response_schema(), "images": [],
        "model": "gpt-6-astra", "threadScope": "channel_analysis:1",
        "expiresAt": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    bridge.atomic_write_json((directory or environment.paths.requests) / f"{id}.json", payload)
    return id


def normal_request(environment, id="normal-a"):
    bridge.atomic_write_json(environment.paths.requests / f"{id}.json", request_payload(id))
    return id


def response(environment, id):
    return bridge.read_json_object(environment.paths.responses / f"{id}.json")


def status(environment):
    return bridge.read_json_object(environment.paths.status)


def wait_for(predicate, *, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (FileNotFoundError, PermissionError):
            pass
        time.sleep(0.01)
    raise AssertionError("Synthetic bridge condition was not reached")


def answer(command):
    output = Path(command[command.index("--output-last-message") + 1])
    output.write_text(json.dumps(suggestion_result()), encoding="utf-8")
    return bridge.CodexRunResult(0, json.dumps({"type": "thread.started", "thread_id": str(uuid4())}))


def blocked_until(event, stop):
    deadline = time.monotonic() + 5
    while not event.wait(0.01):
        if stop.exists():
            return False
        assert time.monotonic() < deadline, "Synthetic runner was not released"
    return True


def start_bridge(environment, runner, **kwargs):
    errors = []

    def serve():
        try:
            assert bridge.serve(environment.root, runner=runner, **kwargs) == 0
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve, name="test-analysis-bridge")
    thread.start()
    return thread, errors


def stop_bridge(environment, thread, errors):
    environment.paths.stop_request.touch()
    thread.join(timeout=6)
    assert not thread.is_alive()
    assert errors == []
    assert status(environment)["state"] == "stopped"
    assert not environment.paths.stop_request.exists()
    assert not list(environment.paths.processing.glob("*.json"))


def test_normal_poll_does_not_claim_analysis(environment):
    id = analysis_request(environment)
    assert bridge.process_pending_requests(environment.paths, project_root=environment.root,
        runner=lambda *args: pytest.fail("Normal lane consumed analysis")) == 0
    assert (environment.paths.requests / f"{id}.json").exists()
    assert list(environment.paths.processing.glob("*.json")) == []


def test_normal_requests_finish_during_analysis_and_heartbeat_keeps_other_lane_active(environment):
    id = analysis_request(environment)
    started, release = threading.Event(), threading.Event()
    normal_started, normal_release = threading.Event(), threading.Event()
    normal_order = []

    def runner(command, prompt, cwd, timeout, stop):
        if cwd.name == id:
            started.set()
            if not blocked_until(release, stop):
                return bridge.CodexRunResult(130, "")
        else:
            assert started.is_set() and not release.is_set()
            normal_order.append(cwd.name)
            if cwd.name == "normal-a":
                normal_started.set()
                if not blocked_until(normal_release, stop):
                    return bridge.CodexRunResult(130, "")
        return answer(command)

    thread, errors = start_bridge(environment, runner)
    try:
        assert started.wait(timeout=3)
        normal_request(environment, "normal-a")
        normal_request(environment, "normal-b")
        assert normal_started.wait(timeout=3)
        assert normal_order == ["normal-a"]
        assert (environment.paths.requests / "normal-b.json").exists()
        assert status(environment)["normalRequestId"] == "normal-a"
        assert status(environment)["analysisRequestId"] == id
        normal_release.set()
        wait_for(lambda: (environment.paths.responses / "normal-b.json").exists())
        assert normal_order == ["normal-a", "normal-b"]
        assert response(environment, "normal-a")["state"] == response(environment, "normal-b")["state"] == "ready"
        assert not (environment.paths.responses / f"{id}.json").exists()
        wait_for(lambda: status(environment)["normalRequestId"] is None)
        first = status(environment)
        assert first["analysisRequestId"] == first["requestId"] == id
        assert first["requestState"] == "processing"
        wait_for(lambda: status(environment)["updatedAt"] != first["updatedAt"])
        assert status(environment)["requestState"] == "processing"
        release.set()
        wait_for(lambda: status(environment)["requestState"] == "idle")
        assert response(environment, id)["state"] == "ready"
    finally:
        normal_release.set()
        release.set()
        stop_bridge(environment, thread, errors)


def test_analysis_is_serial_and_once_waits_for_both_analysis_requests(environment):
    first, second = analysis_request(environment), analysis_request(environment, "2" * 32)
    started, release = threading.Event(), threading.Event()
    active, maximum, order = 0, 0, []
    lock = threading.Lock()

    def runner(command, prompt, cwd, timeout, stop):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            order.append(cwd.name)
        try:
            if cwd.name == first:
                started.set()
                if not blocked_until(release, stop):
                    return bridge.CodexRunResult(130, "")
            return answer(command)
        finally:
            with lock:
                active -= 1

    thread, errors = start_bridge(environment, runner, once=True)
    try:
        assert started.wait(timeout=3)
        assert order == [first]
        assert (environment.paths.requests / f"{second}.json").exists()
        assert len(list(environment.paths.processing.glob("*.json"))) == 1
        release.set()
        thread.join(timeout=5)
        assert not thread.is_alive() and errors == []
        assert order == [first, second] and maximum == 1
        assert response(environment, first)["state"] == response(environment, second)["state"] == "ready"
    finally:
        release.set()
        if thread.is_alive():
            stop_bridge(environment, thread, errors)


def test_analysis_completion_does_not_mark_running_normal_request_idle(environment):
    id, normal = analysis_request(environment), normal_request(environment)
    analysis_started, normal_started = threading.Event(), threading.Event()
    analysis_release, normal_release = threading.Event(), threading.Event()

    def runner(command, prompt, cwd, timeout, stop):
        event, release = ((analysis_started, analysis_release) if cwd.name == id else (normal_started, normal_release))
        event.set()
        if not blocked_until(release, stop):
            return bridge.CodexRunResult(130, "")
        return answer(command)

    thread, errors = start_bridge(environment, runner)
    try:
        assert analysis_started.wait(timeout=3) and normal_started.wait(timeout=3)
        analysis_release.set()
        wait_for(lambda: status(environment)["analysisRequestId"] is None)
        first = status(environment)
        assert first["normalRequestId"] == first["requestId"] == normal
        assert first["requestState"] == "processing"
        assert response(environment, id)["state"] == "ready"
        wait_for(lambda: status(environment)["updatedAt"] != first["updatedAt"])
        assert status(environment)["requestState"] == "processing"
        normal_release.set()
        wait_for(lambda: status(environment)["requestState"] == "idle")
    finally:
        analysis_release.set()
        normal_release.set()
        stop_bridge(environment, thread, errors)


def test_duplicate_queued_copy_does_not_overwrite_inflight_analysis_or_run_twice(environment):
    id = analysis_request(environment)
    started, release = threading.Event(), threading.Event()
    publisher = bridge._RequestStatusPublisher(environment.paths)
    calls, errors = [], []

    def runner(command, prompt, cwd, timeout, stop):
        calls.append(cwd.name)
        started.set()
        if not blocked_until(release, stop):
            return bridge.CodexRunResult(130, "")
        return answer(command)

    def poll():
        try:
            bridge.process_pending_requests(environment.paths, project_root=environment.root, runner=runner,
                analysis_only=True, status_publisher=publisher)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=poll)
    thread.start()
    try:
        assert started.wait(timeout=3)
        original = (environment.paths.processing / f"{id}.json").read_bytes()
        analysis_request(environment, id)
        assert bridge.process_pending_requests(environment.paths, project_root=environment.root, runner=runner,
            analysis_only=True, status_publisher=publisher) == 0
        assert (environment.paths.processing / f"{id}.json").read_bytes() == original
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and errors == []
    assert bridge.process_pending_requests(environment.paths, project_root=environment.root, runner=runner,
        analysis_only=True, status_publisher=publisher) == 0
    assert calls == [id] and response(environment, id)["state"] == "ready"
    assert not (environment.paths.requests / f"{id}.json").exists()


def test_stop_joins_analysis_lane_heartbeat_and_real_child_without_running_codex(environment, monkeypatch):
    id = analysis_request(environment)
    marker = environment.root / "python-child-started"
    processes = []
    popen = bridge.subprocess.Popen

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(bridge.subprocess, "Popen", capture)

    def runner(command, prompt, cwd, timeout, stop):
        script = f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(30)"
        return bridge.run_codex_command([sys.executable, "-c", script], "synthetic", cwd, timeout, stop)

    thread, errors = start_bridge(environment, runner)
    try:
        wait_for(marker.exists)
    finally:
        stop_bridge(environment, thread, errors)
    assert len(processes) == 1 and processes[0].poll() is not None
    assert response(environment, id)["error"]["code"] == "codex_cancelled"
    assert not any(t.name in {"codex-bridge-analysis", f"codex-bridge-heartbeat-{id}"} for t in threading.enumerate())
    private = bridge.private_bridge_paths(environment.root)
    assert not (private.work / id).exists() and not (private.sessions / id).exists()


@pytest.mark.parametrize("shutdown", ["exception", "sigterm"])
def test_bridge_exit_and_sigterm_stop_analysis_and_restore_signal_handler(environment, shutdown):
    id = analysis_request(environment)
    normal_request(environment)
    started, stopped = threading.Event(), threading.Event()
    previous = signal.getsignal(signal.SIGTERM)

    class SyntheticExit(BaseException):
        pass

    def runner(command, prompt, cwd, timeout, stop):
        if cwd.name == id:
            started.set()
            assert not blocked_until(threading.Event(), stop)
            stopped.set()
            return bridge.CodexRunResult(130, "")
        assert started.wait(timeout=3)
        if shutdown == "exception":
            raise SyntheticExit()
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return bridge.CodexRunResult(130, "")

    if shutdown == "exception":
        with pytest.raises(SyntheticExit):
            bridge.serve(environment.root, runner=runner)
    else:
        assert bridge.serve(environment.root, runner=runner) == 0
    assert stopped.is_set()
    assert signal.getsignal(signal.SIGTERM) is previous
    assert response(environment, id)["error"]["code"] == "codex_cancelled"
    assert status(environment)["state"] == "stopped"
    assert not any(t.name == "codex-bridge-analysis" for t in threading.enumerate())


@pytest.mark.parametrize("leftover", ["processing", "response", "queued_copy"])
def test_restart_recovers_analysis_like_existing_requests(environment, leftover):
    id = analysis_request(environment, directory=environment.paths.processing)
    if leftover == "response":
        bridge.atomic_write_json(environment.paths.responses / f"{id}.json", {"state": "ready", "requestId": id})
    elif leftover == "queued_copy":
        analysis_request(environment, id)
    calls = []

    def runner(command, prompt, cwd, timeout, stop):
        calls.append(cwd.name)
        return answer(command)

    assert bridge.serve(environment.root, runner=runner, once=True) == 0
    assert calls == ([] if leftover == "response" else [id])
    assert not list(environment.paths.processing.glob("*.json"))
    assert not list(environment.paths.requests.glob("*.json"))
    assert response(environment, id)["state"] == "ready"


def test_analysis_runner_exception_does_not_stop_normal_lane_and_diagnostics_remain_safe(environment):
    analysis = analysis_request(environment)
    normal = normal_request(environment)

    def runner(command, prompt, cwd, timeout, stop):
        if cwd.name == analysis:
            raise RuntimeError("synthetic-private-text")
        return answer(command)

    assert bridge.serve(environment.root, runner=runner, once=True) == 0
    assert response(environment, normal)["state"] == "ready"
    assert response(environment, analysis)["error"]["code"] == "bridge_request_exception"
    diagnostic = (environment.paths.root / "diagnostics.jsonl").read_text(encoding="utf-8")
    assert "RuntimeError" in diagnostic and "synthetic-private-text" not in diagnostic


def test_interrupted_runner_terminates_its_child(environment, monkeypatch):
    class Process:
        terminated = False

        def poll(self):
            return -1 if self.terminated else None

        def communicate(self, **kwargs):
            if not self.terminated:
                raise KeyboardInterrupt()
            return "", ""

        def terminate(self):
            self.terminated = True

    process = Process()
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(KeyboardInterrupt):
        bridge.run_codex_command(["synthetic"], "synthetic", environment.root, 240)
    assert process.terminated
