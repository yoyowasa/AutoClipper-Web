"""Engine, model and effort per bridge lane, switched from the top screen without restarting the bridge."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import launcher.codex_bridge as bridge  # noqa: E402
from launcher import bridge_engine_settings as lane_settings  # noqa: E402
from launcher import claude_engine  # noqa: E402
from launcher.codex_bridge import (  # noqa: E402
    CodexRunResult, atomic_write_json, bridge_paths, ensure_bridge_directories, process_pending_requests,
)

from app import bridge_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.storage.paths import get_storage_paths  # noqa: E402
from test_api_routes import client as client  # noqa: E402,F401
from tests.test_claude_bridge_engine import stream  # noqa: E402
from tests.test_codex_host_bridge import request_payload, suggestion_result  # noqa: E402

CATALOG = {
    "codex": [{"id": "gpt-6.1-sol", "efforts": ["low", "medium", "high"]},
              {"id": "gpt-6.2-sol", "efforts": ["low", "medium", "high", "ultra"]}],
    "claude": [{"id": "claude-opus-5-5", "efforts": ["low", "medium", "high", "xhigh", "max"]},
               {"id": "claude-sonnet-5-5", "efforts": ["low", "medium", "high", "xhigh", "max"]}],
}


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT", str(tmp_path / "private-bridge"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.delenv("AUTOCLIPPER_BRIDGE_ENGINE", raising=False)
    yield
    bridge.ACTIVE_LANES.reset()


def test_backend_builtin_choices_match_the_bridge() -> None:
    assert bridge_engine.CLAUDE_MODELS == lane_settings.CLAUDE_MODELS
    assert bridge_engine.CLAUDE_EFFORTS == lane_settings.CLAUDE_EFFORTS
    assert bridge_engine.CODEX_FALLBACK_MODELS == lane_settings.CODEX_FALLBACK_MODELS
    assert bridge_engine.CODEX_FALLBACK_EFFORTS == lane_settings.CODEX_EFFORTS[:5]
    assert bridge_engine.DEFAULT_MODELS == lane_settings.DEFAULT_MODELS


def test_codex_models_come_from_the_cli_cache_ids_and_efforts_only(tmp_path: Path) -> None:
    home = tmp_path / "codex-home"
    assert lane_settings.codex_models(home) == [{"id": "gpt-6.1-sol", "efforts": ["low", "medium", "high", "xhigh",
                                                                                    "max"]}]
    home.mkdir()
    (home / "models_cache.json").write_text(json.dumps({"identity": "someone", "models": [
        {"slug": "gpt-6.2-sol", "visibility": "list", "supported_reasoning_levels": [
            {"effort": "low"}, {"effort": "medium"}, {"effort": "ultra"}, {"effort": "unknown"}], "description": "x"},
        {"slug": "codex-auto-review", "visibility": "hide", "supported_reasoning_levels": [{"effort": "low"}]},
        {"slug": "Bad Id!", "visibility": "list", "supported_reasoning_levels": [{"effort": "low"}]},
    ]}), encoding="utf-8")
    assert lane_settings.codex_models(home) == [{"id": "gpt-6.2-sol", "efforts": ["low", "medium", "ultra"]}]


def test_lane_settings_read_old_and_new_files_and_drop_unknown_values(tmp_path: Path) -> None:
    file = tmp_path / "engine.json"
    lanes = lane_settings.read_lane_settings(file, CATALOG)
    assert lanes["normal"] == lanes["analysis"] == lane_settings.LaneSetting("codex", "gpt-6.1-sol", "medium")
    file.write_text(json.dumps({"engine": "codex", "analysisEngine": "claude"}), encoding="utf-8")
    lanes = lane_settings.read_lane_settings(file, CATALOG)
    assert lanes["analysis"] == lane_settings.LaneSetting("claude", "claude-opus-5-5", "medium")
    file.write_text(json.dumps({"engine": "claude", "lanes": {
        "normal": {"engine": "codex", "model": "gpt-6.2-sol", "effort": "ultra"},
        "analysis": {"engine": "claude", "model": "claude-sonnet-5-5", "effort": "high"}}}), encoding="utf-8")
    lanes = lane_settings.read_lane_settings(file, CATALOG)
    assert lanes["normal"] == lane_settings.LaneSetting("codex", "gpt-6.2-sol", "ultra")
    assert lanes["analysis"] == lane_settings.LaneSetting("claude", "claude-sonnet-5-5", "high")
    # Not in the catalog, an effort the model lacks, or a model of the other engine: fall back to defaults.
    file.write_text(json.dumps({"lanes": {
        "normal": {"engine": "codex", "model": "gpt-6.1-sol", "effort": "ultra"},
        "analysis": {"engine": "claude", "model": "gpt-6.2-sol", "effort": "max"}}}), encoding="utf-8")
    lanes = lane_settings.read_lane_settings(file, CATALOG)
    assert lanes["normal"] == lane_settings.LaneSetting("codex", "gpt-6.1-sol", "medium")
    assert lanes["analysis"] == lane_settings.LaneSetting("claude", "claude-opus-5-5", "max")
    assert lane_settings.read_lane_settings(file, CATALOG, engine_override="claude")["normal"].engine == "claude"


def _queue(project_root: Path) -> str:
    request_id = uuid.uuid4().hex
    atomic_write_json(bridge_paths(project_root).requests / f"{request_id}.json", request_payload(request_id))
    return request_id


def test_each_request_uses_the_lane_setting_saved_just_before_it(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    seen = []

    def runner(command, _stdin, _cwd, _timeout, _stop):
        seen.append(list(command))
        if command[1] == "exec":
            output = command[command.index("--output-last-message") + 1]
            Path(output).write_text(json.dumps(suggestion_result()), encoding="utf-8")
            started = {"type": "thread.started", "thread_id": str(uuid.uuid4())}
            return CodexRunResult(0, json.dumps(started) + "\n", "")
        return CodexRunResult(0, stream(str(uuid.uuid4()), suggestion_result()), "")

    current = {"value": lane_settings.LaneSetting("codex", "gpt-6.2-sol", "high")}
    first = _queue(project_root)
    process_pending_requests(paths, project_root=project_root, codex_executable="codex.exe", runner=runner,
                             lane_setting=lambda: current["value"], status_heartbeat_seconds=60)
    command = seen[-1]
    assert command[command.index("--model") + 1] == "gpt-6.2-sol" and 'model_reasoning_effort="high"' in command
    assert json.loads((paths.responses / f"{first}.json").read_text("utf-8"))["state"] == "ready"

    current["value"] = lane_settings.LaneSetting("claude", "claude-sonnet-5-5", "low")
    original = claude_engine.find_claude_executable
    claude_engine.find_claude_executable = lambda: "claude.exe"
    try:
        second = _queue(project_root)
        process_pending_requests(paths, project_root=project_root, runner=runner,
                                 lane_setting=lambda: current["value"], status_heartbeat_seconds=60)
    finally:
        claude_engine.find_claude_executable = original
    command = seen[-1]
    assert command[0] == "claude.exe"
    assert command[command.index("--model") + 1] == "claude-sonnet-5-5"
    assert command[command.index("--effort") + 1] == "low"
    assert json.loads((paths.responses / f"{second}.json").read_text("utf-8"))["state"] == "ready"


def test_switching_to_an_engine_without_login_fails_the_request_instead_of_running(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = _queue(project_root)
    ran = []
    process_pending_requests(paths, project_root=project_root, runner=lambda *args: ran.append(args),
                             lane_setting=lambda: lane_settings.LaneSetting("claude", "claude-opus-5-5", "medium"),
                             engine_ready=lambda engine: "claude_login_missing" if engine == "claude" else None,
                             status_heartbeat_seconds=60)
    assert not ran
    response = json.loads((paths.responses / f"{request_id}.json").read_text("utf-8"))
    assert (response["state"], response["error"]["code"]) == ("failed", "claude_login_missing")


def test_engine_readiness_checks_a_new_engine_once_and_caches_success(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(claude_engine, "find_claude_executable", lambda: "claude.exe")
    monkeypatch.setattr(claude_engine, "claude_login_configured", lambda *_: calls.append(1) or len(calls) > 1)
    readiness = bridge._EngineReadiness({"codex"})
    assert readiness.check("codex") is None and not calls
    assert readiness.check("claude") == "claude_login_missing"
    assert readiness.check("claude") is None and readiness.check("claude") is None
    assert len(calls) == 2


def test_status_reports_both_lanes_and_the_catalog_after_a_change(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    assert bridge.ACTIVE_LANES.refresh(project_root) is False  # defaults are already active
    atomic_write_json(paths.root / "engine.json", {"lanes": {
        "normal": {"engine": "claude", "model": "claude-sonnet-5-5", "effort": "high"},
        "analysis": {"engine": "codex", "model": "gpt-6.1-sol", "effort": "low"}}})
    assert bridge.ACTIVE_LANES.refresh(project_root) is True
    bridge._RequestStatusPublisher(paths).refresh()
    status = json.loads(paths.status.read_text("utf-8"))
    assert (status["engine"], status["model"], status["reasoningEffort"]) == ("claude", "claude-sonnet-5-5", "high")
    assert (status["analysisEngine"], status["analysisModel"], status["analysisReasoningEffort"]) == (
        "codex", "gpt-6.1-sol", "low")
    assert [item["id"] for item in status["engineCatalog"]["claude"]] == list(lane_settings.CLAUDE_MODELS)
    assert status["requestState"] == "idle"


def _status(paths, **extra) -> None:
    paths.bridge_status.parent.mkdir(parents=True, exist_ok=True)
    paths.bridge_status.write_text(json.dumps({"schemaVersion": 1, "state": "ready", "engineCatalog": CATALOG,
                                               "engine": "codex", "model": "gpt-6.1-sol", "reasoningEffort": "medium",
                                               "analysisEngine": "claude", "analysisModel": "claude-opus-5-5",
                                               "analysisReasoningEffort": "medium", **extra}), encoding="utf-8")


def test_api_reads_saves_and_rejects_choices_outside_the_catalog(client):  # noqa: F811
    paths = app.dependency_overrides[get_storage_paths]()
    first = client.get("/api/bridge-engine").json()
    assert first["catalogSource"] == "builtin" and first["active"] is None
    assert first["saved"]["normal"] == {"engine": "codex", "model": "gpt-6.1-sol", "effort": "medium"}
    _status(paths)
    read = client.get("/api/bridge-engine").json()
    assert read["catalogSource"] == "bridge" and read["active"]["analysis"]["engine"] == "claude"
    body = {"normal": {"engine": "codex", "model": "gpt-6.2-sol", "effort": "ultra"},
            "analysis": {"engine": "claude", "model": "claude-sonnet-5-5", "effort": "high"}}
    assert client.put("/api/bridge-engine", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    for lane, bad in (("normal", {"engine": "codex", "model": "gpt-9", "effort": "medium"}),
                      ("normal", {"engine": "codex", "model": "gpt-6.1-sol", "effort": "ultra"}),
                      ("analysis", {"engine": "claude", "model": "gpt-6.1-sol", "effort": "medium"})):
        response = client.put("/api/bridge-engine", json=body | {lane: bad})
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.put("/api/bridge-engine", json=body | {"normal": {**body["normal"], "extra": 1}}).status_code == 422
    assert not paths.bridge_engine_settings.exists()
    saved = client.put("/api/bridge-engine", json=body)
    assert saved.status_code == 200 and saved.json()["saved"] == body
    written = json.loads(paths.bridge_engine_settings.read_text("utf-8"))
    assert (written["engine"], written["analysisEngine"], written["lanes"]) == ("codex", "claude", body)
    # The bridge reads exactly what the screen saved.
    lanes = lane_settings.read_lane_settings(paths.bridge_engine_settings, CATALOG)
    assert lanes["normal"] == lane_settings.LaneSetting("codex", "gpt-6.2-sol", "ultra")
    assert lanes["analysis"] == lane_settings.LaneSetting("claude", "claude-sonnet-5-5", "high")
    _status(paths, state="error")
    assert client.get("/api/bridge-engine").json()["active"] is None
