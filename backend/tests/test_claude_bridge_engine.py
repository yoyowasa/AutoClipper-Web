from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import launcher.codex_bridge as bridge  # noqa: E402
from launcher import claude_engine  # noqa: E402
from launcher.codex_bridge import (  # noqa: E402
    BRIDGE_ENGINE_CLAUDE,
    BRIDGE_ENGINE_CODEX,
    BRIDGE_PROTOCOL_VERSION,
    CodexRunResult,
    atomic_write_json,
    bridge_build_fingerprint,
    bridge_paths,
    configured_bridge_engine,
    ensure_bridge_directories,
    private_bridge_paths,
    process_request_file,
    register_bridge_thread,
    serve,
)

from tests.test_codex_host_bridge import request_payload, suggestion_result  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT", str(tmp_path / "private-bridge"))
    monkeypatch.delenv("AUTOCLIPPER_BRIDGE_ENGINE", raising=False)


def stream(session_id: str, output: dict | None, *, tools=("StructuredOutput",), extra_blocks=(),
           api_key_source="none", subtype="success", rate_status="allowed") -> str:
    events = [
        {"type": "system", "subtype": "init", "session_id": session_id, "tools": list(tools),
         "mcp_servers": [], "apiKeySource": api_key_source, "model": claude_engine.CLAUDE_MODEL},
        {"type": "assistant", "session_id": session_id, "message": {"content": [
            {"type": "tool_use", "name": "StructuredOutput", "input": output or {}}, *extra_blocks]}},
        {"type": "rate_limit_event", "session_id": session_id, "rate_limit_info": {"status": rate_status}},
        {"type": "result", "subtype": subtype, "is_error": subtype != "success", "session_id": session_id,
         "structured_output": output},
    ]
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    image = project_root / "storage" / "temp" / "frame_1.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"jpeg fixture")
    return project_root, image


def run_claude(project_root: Path, payload: dict, stdout: str, returncode: int = 0):
    paths = bridge_paths(project_root)
    request_path = paths.processing / f"{payload['requestId']}.json"
    atomic_write_json(request_path, payload)
    observed: dict[str, object] = {}

    def fake_runner(command, stdin_text, cwd, timeout, _stop):
        observed.update(command=list(command), stdin=stdin_text, cwd=cwd, timeout=timeout)
        return CodexRunResult(returncode, stdout, "")

    response = process_request_file(
        request_path, project_root=project_root, runner=fake_runner,
        engine=BRIDGE_ENGINE_CLAUDE, claude_executable="claude.exe",
    )
    return response, observed


def test_claude_command_disables_tools_and_uses_fixed_model_and_effort() -> None:
    command = claude_engine.build_claude_command(
        "claude.exe", schema_text='{"type":"object"}', resume_session_id=None, ephemeral=False,
    )
    assert command[:2] == ["claude.exe", "-p"]
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--model") + 1] == "claude-opus-5-5"
    assert command[command.index("--effort") + 1] == "medium"
    assert command[command.index("--json-schema") + 1] == '{"type":"object"}'
    assert command[command.index("--input-format") + 1] == "stream-json"
    assert command[command.index("--output-format") + 1] == "stream-json"
    for flag in ("--safe-mode", "--strict-mcp-config", "--disable-slash-commands", "--system-prompt"):
        assert flag in command
    assert "--resume" not in command and "--no-session-persistence" not in command
    assert not any("dangerously" in part or "bypass" in part.lower() for part in command)
    resumed = claude_engine.build_claude_command(
        "claude.exe", schema_text="{}", resume_session_id="abc", ephemeral=True,
    )
    assert resumed[-2:] == ["--resume", "abc"]
    assert "--no-session-persistence" in resumed


def test_claude_environment_drops_api_keys_and_third_party_providers() -> None:
    env = claude_engine.claude_environment({
        "PATH": "p", "USERPROFILE": "u", "ANTHROPIC_API_KEY": "secret", "ANTHROPIC_AUTH_TOKEN": "t",
        "CLAUDE_CODE_USE_BEDROCK": "1", "AWS_ACCESS_KEY_ID": "a",
    })
    assert env == {"PATH": "p", "USERPROFILE": "u"}


def test_claude_input_embeds_guarded_prompt_and_images(tmp_path: Path) -> None:
    image = tmp_path / "f.png"
    image.write_bytes(b"png")
    line = claude_engine.build_claude_input("字幕", [image])
    assert line.endswith("\n")
    message = json.loads(line)
    text, picture = message["message"]["content"]
    assert text == {"type": "text", "text": "字幕"}
    assert picture["source"] == {"type": "base64", "media_type": "image/png",
                                 "data": base64.b64encode(b"png").decode("ascii")}
    with pytest.raises(ValueError):
        claude_engine.build_claude_input("x", [tmp_path / "f.gif"])


def test_schema_argument_rejects_command_line_overflow() -> None:
    assert claude_engine.schema_argument({"type": "object"}) == '{"type":"object"}'
    with pytest.raises(ValueError, match="claude_schema_too_large"):
        claude_engine.schema_argument({"type": "object", "description": "x" * 30_000})


def test_process_request_returns_structured_output_and_registers_claude_session(tmp_path: Path) -> None:
    project_root, image = make_project(tmp_path)
    session_id = str(uuid.uuid4())
    response, observed = run_claude(project_root, request_payload("claude-1", image="temp/frame_1.jpg"),
                                    stream(session_id, suggestion_result()))
    assert response["state"] == "ready"
    assert response["threadId"] == session_id
    assert response["output"] == suggestion_result()
    message = json.loads(str(observed["stdin"]))
    text, picture = message["message"]["content"]
    assert text["text"].startswith("この処理ではシェル") and "字幕を根拠に" in text["text"]
    assert picture["source"]["data"] == base64.b64encode(image.read_bytes()).decode("ascii")
    schema = json.loads(observed["command"][observed["command"].index("--json-schema") + 1])
    assert schema["additionalProperties"] is False
    record = json.loads((private_bridge_paths(project_root).threads / f"{session_id}.json").read_text("utf-8"))
    assert record["engine"] == BRIDGE_ENGINE_CLAUDE and record["threadScope"] == "job_test"


def test_claude_resumes_its_own_session_but_not_a_codex_thread(tmp_path: Path) -> None:
    project_root, _image = make_project(tmp_path)
    private = private_bridge_paths(project_root)
    private.threads.mkdir(parents=True)
    codex_thread, claude_thread = str(uuid.uuid4()), str(uuid.uuid4())
    register_bridge_thread(private, thread_id=codex_thread, thread_scope="job_test", task="title_hook_suggestions")
    register_bridge_thread(private, thread_id=claude_thread, thread_scope="job_test",
                           task="title_hook_suggestions", engine=BRIDGE_ENGINE_CLAUDE)
    new_session = str(uuid.uuid4())
    response, observed = run_claude(project_root, request_payload("claude-2", thread_id=codex_thread),
                                    stream(new_session, suggestion_result()))
    assert "--resume" not in observed["command"]
    assert response["threadId"] == new_session
    response, observed = run_claude(project_root, request_payload("claude-3", thread_id=claude_thread),
                                    stream(claude_thread, suggestion_result()))
    assert observed["command"][-2:] == ["--resume", claude_thread]
    assert response["state"] == "ready"


@pytest.mark.parametrize(
    ("kwargs", "returncode", "code"),
    [
        ({"tools": ("StructuredOutput", "Bash")}, 0, "claude_tool_forbidden"),
        ({"extra_blocks": ({"type": "tool_use", "name": "WebFetch", "input": {}},)}, 0, "claude_tool_forbidden"),
        ({"api_key_source": "ANTHROPIC_API_KEY"}, 0, "claude_api_key_forbidden"),
        ({"subtype": "error_max_turns"}, 0, "claude_failed"),
        ({"subtype": "error_during_execution", "rate_status": "rejected"}, 1, "claude_rate_limited"),
        ({}, 124, "claude_timeout"),
    ],
)
def test_claude_failures_never_return_output(tmp_path: Path, kwargs, returncode, code) -> None:
    project_root, _image = make_project(tmp_path)
    session_id = str(uuid.uuid4())
    response, _observed = run_claude(project_root, request_payload("claude-f"),
                                     stream(session_id, suggestion_result(), **kwargs), returncode)
    assert response["state"] == "failed"
    assert response["output"] is None
    assert response["error"]["code"] == code
    if code == "claude_tool_forbidden":
        record = json.loads((private_bridge_paths(project_root).threads / f"{session_id}.json").read_text("utf-8"))
        assert record["revokedAt"]


def test_missing_structured_output_is_invalid(tmp_path: Path) -> None:
    project_root, _image = make_project(tmp_path)
    response, _observed = run_claude(project_root, request_payload("claude-o"), stream(str(uuid.uuid4()), None))
    assert response["error"]["code"] == "claude_output_invalid"


def test_engine_is_configured_by_env_then_file_and_defaults_to_codex(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "root"
    assert configured_bridge_engine(project_root) == BRIDGE_ENGINE_CODEX
    engine_file = bridge_paths(project_root).root / "engine.json"
    atomic_write_json(engine_file, {"engine": "claude"})
    assert configured_bridge_engine(project_root) == BRIDGE_ENGINE_CLAUDE
    atomic_write_json(engine_file, {"engine": "openai-api"})
    assert configured_bridge_engine(project_root) == BRIDGE_ENGINE_CODEX
    monkeypatch.setenv("AUTOCLIPPER_BRIDGE_ENGINE", "Claude")
    assert configured_bridge_engine(project_root) == BRIDGE_ENGINE_CLAUDE


def test_serve_with_claude_reports_engine_and_missing_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOCLIPPER_BRIDGE_ENGINE", "claude")
    monkeypatch.setattr(claude_engine, "find_claude_executable", lambda: None)
    try:
        assert serve(tmp_path, sleeper=lambda _: None, once=True) == 4
        status = json.loads(bridge_paths(tmp_path).status.read_text("utf-8"))
        assert status["errorCode"] == "claude_cli_missing"
        assert status["engine"] == "claude" and status["model"] == "claude-opus-5-5"
        assert status["reasoningEffort"] == "medium"
        monkeypatch.setattr(claude_engine, "find_claude_executable", lambda: "claude.exe")
        monkeypatch.setattr(claude_engine, "claude_login_configured", lambda *_: False)
        assert serve(tmp_path, sleeper=lambda _: None, once=True) == 5
        assert json.loads(bridge_paths(tmp_path).status.read_text("utf-8"))["errorCode"] == "claude_login_missing"
    finally:
        bridge.ACTIVE_ENGINE = BRIDGE_ENGINE_CODEX


def test_claude_login_requires_subscription_not_api_key(monkeypatch) -> None:
    class Done:
        def __init__(self, payload):
            self.returncode, self.stdout = 0, json.dumps(payload)

    seen = {}

    def fake_run(command, **kwargs):
        seen["env"] = kwargs["env"]
        return Done(state)

    monkeypatch.setattr(claude_engine.subprocess, "run", fake_run)
    state = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}
    assert claude_engine.claude_login_configured("claude.exe", {"ANTHROPIC_API_KEY": "x", "PATH": "p"})
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    state = {"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"}
    assert not claude_engine.claude_login_configured("claude.exe", {})


def test_build_fingerprint_covers_engine_module(tmp_path: Path) -> None:
    module = tmp_path / "codex_bridge.py"
    module.write_text("# bridge\n", encoding="utf-8")
    alone = bridge_build_fingerprint(module)
    (tmp_path / "claude_engine.py").write_text("# engine v1\n", encoding="utf-8")
    first = bridge_build_fingerprint(module)
    (tmp_path / "claude_engine.py").write_text("# engine v2\n", encoding="utf-8")
    assert len({alone, first, bridge_build_fingerprint(module)}) == 3


def test_launcher_restarts_bridge_running_another_engine(tmp_path: Path) -> None:
    from tests.test_windows_launcher import FakeRunner, compatible_bridge_status, make_controller
    from tests.test_windows_launcher import make_project as make_launcher_project

    root = make_launcher_project(tmp_path)
    module = root / "launcher" / "codex_bridge.py"
    module.parent.mkdir()
    module.write_text("# current bridge fixture\n", encoding="utf-8")
    status = root / "storage" / "codex_bridge" / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(compatible_bridge_status(module, pid=111, engine="codex")), encoding="utf-8")
    controller = make_controller(root, FakeRunner(), process_checker=lambda pid: pid == 111)
    assert controller.codex_bridge_ready() is True
    atomic_write_json(status.parent / "engine.json", {"engine": "claude"})
    assert controller.codex_bridge_ready() is False
    status.write_text(json.dumps(compatible_bridge_status(module, pid=111, engine="claude")), encoding="utf-8")
    assert controller.codex_bridge_ready() is True
    assert BRIDGE_PROTOCOL_VERSION == 1
