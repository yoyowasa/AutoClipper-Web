from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.candidates.codex_initial_selection import (  # noqa: E402
    CodexInitialSelectionHostResponse,
    codex_initial_selection_response_schema,
)
from app.scoring.title_hook_suggestions import TITLE_HOOK_GENERATION_SCHEMA  # noqa: E402

from launcher.codex_bridge import (  # noqa: E402
    BRIDGE_PROTOCOL_VERSION,
    EXPECTED_RESPONSE_SCHEMA_SHA256,
    INITIAL_CLIP_SELECTION_TASK,
    INITIAL_CLIP_SELECTION_TIMEOUT_SECONDS,
    REQUEST_TASK,
    TITLE_HOOK_OUTPUT_SCHEMA,
    _response_schema_sha256,
    BridgeRequest,
    CodexRunResult,
    atomic_write_json,
    bridge_paths,
    build_codex_command,
    codex_used_disallowed_tool,
    ensure_bridge_directories,
    process_pending_requests,
    process_request_file,
    private_bridge_paths,
    run_codex_command,
    safe_codex_environment,
    thread_id_from_jsonl,
    validate_request,
)


@pytest.fixture(autouse=True)
def isolate_private_bridge_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT",
        str(tmp_path / "private-codex-bridge"),
    )


def suggestion_result() -> dict[str, object]:
    return {
        "suggestions": [
            {
                "id": f"suggestion-{index}",
                "intent": ("factual", "engagement", "concise")[index - 1],
                "publicationTitle": f"公開タイトル{index}",
                "overlayTitle": f"表示タイトル{index}",
                "hookText": f"フック{index}",
                "hookDurationSeconds": 2.0,
                "hookSceneStart": 0.0,
                "hookSceneEnd": 2.0,
                "reason": f"理由{index}",
                "evidenceSegmentIds": [],
            }
            for index in range(1, 4)
        ],
        "recommendedSuggestionId": "suggestion-1",
        "youtubeDescription": "動画内の会話を短く紹介します。",
        "hashtags": ["#会話", "#切り抜き", "#動画"],
        "descriptionEvidenceSegmentIds": [],
    }


def request_payload(
    request_id: str,
    *,
    image: str | None = None,
    thread_id: str | None = None,
) -> dict[str, object]:
    return {
        "schemaVersion": BRIDGE_PROTOCOL_VERSION,
        "requestId": request_id,
        "task": "title_hook_suggestions",
        "prompt": "字幕を根拠にタイトルとフックを3案作成してください。",
        "images": [image] if image else [],
        "model": "gpt-5.5",
        "threadId": thread_id,
        "threadScope": "job_test",
    }


def test_title_hook_bridge_schema_matches_backend_generation_contract() -> None:
    assert TITLE_HOOK_OUTPUT_SCHEMA == TITLE_HOOK_GENERATION_SCHEMA
    assert EXPECTED_RESPONSE_SCHEMA_SHA256[REQUEST_TASK] == _response_schema_sha256(
        TITLE_HOOK_OUTPUT_SCHEMA
    )


def test_title_hook_bridge_schema_avoids_unsupported_unique_items() -> None:
    def keys_in(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                key
                for nested in value.values()
                for key in keys_in(nested)
            }
        if isinstance(value, list):
            return {key for nested in value for key in keys_in(nested)}
        return set()

    assert "uniqueItems" not in keys_in(TITLE_HOOK_OUTPUT_SCHEMA)


def test_initial_codex_command_is_fixed_read_only_and_persistent(tmp_path: Path) -> None:
    request = BridgeRequest(
        request_id="request-1",
        task=REQUEST_TASK,
        prompt="prompt",
        image_paths=(tmp_path / "frame.jpg",),
        response_schema=TITLE_HOOK_OUTPUT_SCHEMA,
        thread_scope="job_test",
        model="gpt-5.5",
    )

    command = build_codex_command(
        "codex.exe",
        request,
        session_dir=tmp_path / "session",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )

    assert command[:3] == ["codex.exe", "exec", "--sandbox"]
    assert command[3] == "read-only"
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--output-schema" in command
    assert "--json" in command
    assert "--output-last-message" in command
    assert "--image" in command
    assert command.count("--disable") >= 2
    assert command[command.index("--disable") + 1] == "apps"
    assert "shell_tool" in command
    assert "unified_exec" in command
    assert command[-1] == "-"
    assert "--ephemeral" not in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command


def test_resume_codex_command_reuses_thread_with_read_only_override(tmp_path: Path) -> None:
    thread_id = str(uuid.uuid4())
    request = BridgeRequest(
        request_id="request-2",
        task=REQUEST_TASK,
        prompt="follow-up",
        image_paths=(),
        response_schema=TITLE_HOOK_OUTPUT_SCHEMA,
        thread_scope="job_test",
        thread_id=thread_id,
    )

    command = build_codex_command(
        "codex.exe",
        request,
        session_dir=tmp_path / "session",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )

    assert command[:3] == ["codex.exe", "exec", "resume"]
    assert 'sandbox_mode="read-only"' in command
    assert command[-2:] == [thread_id, "-"]
    assert "--ephemeral" not in command


def test_process_request_captures_thread_and_structured_output(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    image = project_root / "storage" / "temp" / "frame_1.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"jpeg fixture")
    request_id = "request-3"
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(
        request_path,
        request_payload(request_id, image="temp/frame_1.jpg"),
    )
    thread_id = str(uuid.uuid4())
    observed: dict[str, object] = {}

    def fake_runner(
        command: list[str] | tuple[str, ...],
        prompt: str,
        cwd: Path,
        timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        observed.update(command=list(command), prompt=prompt, cwd=cwd, timeout=timeout)
        output_index = list(command).index("--output-last-message") + 1
        output_path = Path(command[output_index])
        output_path.write_text(
            json.dumps(suggestion_result(), ensure_ascii=False),
            encoding="utf-8",
        )
        schema_index = list(command).index("--output-schema") + 1
        assert json.loads(Path(command[schema_index]).read_text(encoding="utf-8"))[
            "additionalProperties"
        ] is False
        return CodexRunResult(
            0,
            json.dumps({"type": "thread.started", "thread_id": thread_id}),
            "",
        )

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert response["state"] == "ready"
    assert response["threadId"] == thread_id
    assert response["output"] == suggestion_result()
    assert "completedAt" not in response
    assert str(observed["prompt"]).startswith("この処理ではシェル")
    assert "字幕を根拠に" in str(observed["prompt"])
    assert Path(str(observed["cwd"])).is_dir()
    command = list(observed["command"])  # type: ignore[arg-type]
    assert str(image.resolve()) in command
    registry = private_bridge_paths(project_root).threads / f"{thread_id}.json"
    assert json.loads(registry.read_text(encoding="utf-8"))["threadScope"] == "job_test"
    assert not list((paths.work / request_id).glob("*"))


def test_invalid_image_escape_is_rejected_without_codex_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"fixture")
    request_id = "request-4"
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(
        request_path,
        request_payload(request_id, image="../../outside.jpg"),
    )
    called = False

    def fake_runner(*_args: object, **_kwargs: object) -> CodexRunResult:
        nonlocal called
        called = True
        return CodexRunResult(0)

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert response["state"] == "failed"
    assert response["error"] == {
        "code": "request_invalid",
        "message": "Codex bridge request failed.",
    }
    assert called is False


def test_codex_error_does_not_copy_stderr_into_response(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "request-5"
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(request_path, request_payload(request_id))

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=lambda *_args: CodexRunResult(1, "", "secret-token-value"),
    )

    encoded = json.dumps(response, ensure_ascii=False)
    assert response["state"] == "failed"
    assert response["error"]["code"] == "codex_failed"  # type: ignore[index]
    assert "secret-token-value" not in encoded


def test_pending_request_is_claimed_and_response_is_atomic(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "request-6"
    atomic_write_json(paths.requests / f"{request_id}.json", request_payload(request_id))
    thread_id = str(uuid.uuid4())

    def fake_runner(
        command: list[str] | tuple[str, ...],
        _prompt: str,
        _cwd: Path,
        _timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        output_path = Path(list(command)[list(command).index("--output-last-message") + 1])
        output_path.write_text(json.dumps(suggestion_result()), encoding="utf-8")
        return CodexRunResult(
            0,
            json.dumps({"type": "thread.started", "thread_id": thread_id}),
        )

    count = process_pending_requests(
        paths,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert count == 1
    assert not (paths.requests / f"{request_id}.json").exists()
    assert not (paths.processing / f"{request_id}.json").exists()
    response = json.loads(
        (paths.responses / f"{request_id}.json").read_text(encoding="utf-8")
    )
    assert response["threadId"] == thread_id
    assert not list(paths.responses.glob("*.tmp"))


def test_processing_request_refreshes_status_heartbeat_until_response(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "request-heartbeat"
    atomic_write_json(paths.requests / f"{request_id}.json", request_payload(request_id))
    runner_started = threading.Event()
    release_runner = threading.Event()
    thread_id = str(uuid.uuid4())
    processed: list[int] = []
    failures: list[BaseException] = []

    def blocking_runner(
        command: list[str] | tuple[str, ...],
        _prompt: str,
        _cwd: Path,
        _timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        runner_started.set()
        assert release_runner.wait(timeout=2)
        output_path = Path(list(command)[list(command).index("--output-last-message") + 1])
        output_path.write_text(json.dumps(suggestion_result()), encoding="utf-8")
        return CodexRunResult(
            0,
            json.dumps({"type": "thread.started", "thread_id": thread_id}),
        )

    def process_request() -> None:
        try:
            processed.append(
                process_pending_requests(
                    paths,
                    project_root=project_root,
                    codex_executable="codex.exe",
                    runner=blocking_runner,
                    status_heartbeat_seconds=0.05,
                )
            )
        except BaseException as exc:  # pragma: no cover - reported below
            failures.append(exc)

    worker = threading.Thread(target=process_request)
    worker.start()
    try:
        assert runner_started.wait(timeout=2)
        first_status = json.loads(paths.status.read_text(encoding="utf-8"))
        assert first_status["state"] == "ready"
        assert first_status["requestState"] == "processing"
        assert first_status["requestId"] == request_id

        deadline = time.monotonic() + 2
        refreshed_status = first_status
        while (
            refreshed_status["updatedAt"] == first_status["updatedAt"]
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
            refreshed_status = json.loads(paths.status.read_text(encoding="utf-8"))
        assert refreshed_status["updatedAt"] != first_status["updatedAt"]
    finally:
        release_runner.set()
        worker.join(timeout=3)

    assert not worker.is_alive()
    assert failures == []
    assert processed == [1]
    final_status = json.loads(paths.status.read_text(encoding="utf-8"))
    assert final_status["state"] == "ready"
    assert final_status["requestState"] == "idle"
    assert final_status["requestId"] is None
    assert (paths.responses / f"{request_id}.json").is_file()


def test_thread_id_parser_ignores_untrusted_non_uuid_values() -> None:
    valid = str(uuid.uuid4())
    output = "\n".join(
        [
            "not-json",
            json.dumps({"type": "thread.started", "thread_id": "--bad"}),
            json.dumps({"type": "thread.started", "thread_id": valid}),
        ]
    )

    assert thread_id_from_jsonl(output) == valid


def test_codex_environment_does_not_inherit_host_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("CUSTOM_SECRET", "must-not-leak")
    monkeypatch.setenv("PATH", "safe-path")
    monkeypatch.setenv("USERPROFILE", "safe-profile")

    environment = safe_codex_environment()

    assert environment["PATH"] == "safe-path"
    assert environment["USERPROFILE"] == "safe-profile"
    assert "OPENAI_API_KEY" not in environment
    assert "CUSTOM_SECRET" not in environment


def test_initial_selection_uses_supplied_schema_and_extended_timeout(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "1" * 32
    response_schema = codex_initial_selection_response_schema()
    request_path = paths.processing / f"{request_id}.json"
    payload = request_payload(request_id)
    payload["task"] = INITIAL_CLIP_SELECTION_TASK
    payload["responseSchema"] = response_schema
    atomic_write_json(request_path, payload)
    observed: dict[str, object] = {}
    thread_id = str(uuid.uuid4())

    def fake_runner(
        command: list[str] | tuple[str, ...],
        _prompt: str,
        _cwd: Path,
        timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        command_list = list(command)
        schema_path = Path(command_list[command_list.index("--output-schema") + 1])
        observed["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        observed["timeout"] = timeout
        output_path = Path(
            command_list[command_list.index("--output-last-message") + 1]
        )
        output_path.write_text('{"normalClips":[1.0]}', encoding="utf-8")
        return CodexRunResult(
            0,
            json.dumps({"type": "thread.started", "thread_id": thread_id}),
        )

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
        timeout=30,
    )

    assert response["state"] == "completed"
    assert observed["schema"] == response_schema
    assert observed["timeout"] == INITIAL_CLIP_SELECTION_TIMEOUT_SECONDS
    CodexInitialSelectionHostResponse.model_validate(response)


def test_one_hour_dense_transcript_prompt_fits_bridge_limit(tmp_path: Path) -> None:
    payload = request_payload("dense-transcript")
    payload["prompt"] = "字" * 320_000

    request = validate_request(payload, tmp_path)

    assert len(request.prompt) == 320_000


def test_initial_selection_failed_envelope_matches_worker_contract(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "2" * 32
    payload = request_payload(request_id)
    payload["task"] = INITIAL_CLIP_SELECTION_TASK
    payload["responseSchema"] = codex_initial_selection_response_schema()
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(request_path, payload)

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=lambda *_args: CodexRunResult(1, "", "not-shared"),
    )

    validated = CodexInitialSelectionHostResponse.model_validate(response)
    assert validated.state == "failed"
    assert "completedAt" not in response


def test_initial_selection_rejects_missing_or_external_response_schema(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    called = False

    def fake_runner(*_args: object, **_kwargs: object) -> CodexRunResult:
        nonlocal called
        called = True
        return CodexRunResult(0)

    missing_id = "initial-missing-schema"
    missing_payload = request_payload(missing_id)
    missing_payload["task"] = INITIAL_CLIP_SELECTION_TASK
    missing_path = paths.processing / f"{missing_id}.json"
    atomic_write_json(missing_path, missing_payload)

    external_id = "initial-external-ref"
    external_payload = request_payload(external_id)
    external_payload["task"] = INITIAL_CLIP_SELECTION_TASK
    external_payload["responseSchema"] = {
        "type": "object",
        "properties": {"clips": {"$ref": "https://invalid.example/schema.json"}},
    }
    external_path = paths.processing / f"{external_id}.json"
    atomic_write_json(external_path, external_payload)

    missing_response = process_request_file(
        missing_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )
    external_response = process_request_file(
        external_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert missing_response["error"]["code"] == "request_invalid"
    assert external_response["error"]["code"] == "request_invalid"
    assert called is False


def test_task_schema_contract_rejects_valid_but_modified_schema(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "schema-contract-mismatch"
    payload = request_payload(request_id)
    modified_schema = json.loads(json.dumps(TITLE_HOOK_OUTPUT_SCHEMA))
    modified_schema["properties"]["suggestions"]["maxItems"] = 4
    payload["responseSchema"] = modified_schema
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(request_path, payload)
    called = False

    def fake_runner(*_args: object, **_kwargs: object) -> CodexRunResult:
        nonlocal called
        called = True
        return CodexRunResult(0)

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert response["error"]["code"] == "request_invalid"
    assert called is False


def test_resume_rejects_unregistered_or_wrong_scope_thread(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    thread_id = str(uuid.uuid4())
    called = False

    def fake_runner(*_args: object, **_kwargs: object) -> CodexRunResult:
        nonlocal called
        called = True
        return CodexRunResult(0)

    unregistered_id = "resume-unregistered"
    unregistered_path = paths.processing / f"{unregistered_id}.json"
    atomic_write_json(
        unregistered_path,
        request_payload(unregistered_id, thread_id=thread_id),
    )
    unregistered = process_request_file(
        unregistered_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    private_paths = private_bridge_paths(project_root)
    private_paths.threads.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        private_paths.threads / f"{thread_id}.json",
        {
            "schemaVersion": BRIDGE_PROTOCOL_VERSION,
            "threadId": thread_id,
            "threadScope": "job_other",
        },
    )
    wrong_scope_id = "resume-wrong-scope"
    wrong_scope_path = paths.processing / f"{wrong_scope_id}.json"
    atomic_write_json(
        wrong_scope_path,
        request_payload(wrong_scope_id, thread_id=thread_id),
    )
    wrong_scope = process_request_file(
        wrong_scope_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert unregistered["error"]["code"] == "thread_scope_invalid"
    assert wrong_scope["error"]["code"] == "thread_scope_invalid"
    assert called is False


def test_resume_accepts_bridge_thread_from_same_scope(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    private_paths = private_bridge_paths(project_root)
    private_paths.threads.mkdir(parents=True, exist_ok=True)
    thread_id = str(uuid.uuid4())
    atomic_write_json(
        private_paths.threads / f"{thread_id}.json",
        {
            "schemaVersion": BRIDGE_PROTOCOL_VERSION,
            "threadId": thread_id,
            "threadScope": "job_test",
        },
    )
    request_id = "resume-same-scope"
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(
        request_path,
        request_payload(request_id, thread_id=thread_id),
    )
    observed_command: list[str] = []

    def fake_runner(
        command: list[str] | tuple[str, ...],
        _prompt: str,
        _cwd: Path,
        _timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        observed_command.extend(command)
        output_path = Path(
            observed_command[observed_command.index("--output-last-message") + 1]
        )
        output_path.write_text(json.dumps(suggestion_result()), encoding="utf-8")
        return CodexRunResult(0, json.dumps({"type": "turn.completed"}))

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert response["state"] == "ready"
    assert response["threadId"] == thread_id
    assert observed_command[:3] == ["codex.exe", "exec", "resume"]


def test_tool_activity_is_not_returned_to_shared_response(tmp_path: Path) -> None:
    project_root = tmp_path / "AutoClipper Web"
    paths = bridge_paths(project_root)
    ensure_bridge_directories(paths)
    request_id = "request-tool-attempt"
    request_path = paths.processing / f"{request_id}.json"
    atomic_write_json(request_path, request_payload(request_id))
    thread_id = str(uuid.uuid4())

    def fake_runner(
        command: list[str] | tuple[str, ...],
        _prompt: str,
        _cwd: Path,
        _timeout: float,
        _stop_request: Path | None,
    ) -> CodexRunResult:
        command_list = list(command)
        output_path = Path(
            command_list[command_list.index("--output-last-message") + 1]
        )
        output_path.write_text(json.dumps(suggestion_result()), encoding="utf-8")
        return CodexRunResult(
            0,
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": thread_id}),
                    json.dumps(
                        {
                            "type": "item.started",
                            "item": {"type": "command_execution"},
                        }
                    ),
                ]
            ),
        )

    response = process_request_file(
        request_path,
        project_root=project_root,
        codex_executable="codex.exe",
        runner=fake_runner,
    )

    assert response["state"] == "failed"
    assert response["error"]["code"] == "codex_tool_forbidden"
    assert response["output"] is None
    record = json.loads(
        (
            private_bridge_paths(project_root).threads / f"{thread_id}.json"
        ).read_text(encoding="utf-8")
    )
    assert record["revokedAt"]


def test_nonfatal_codex_error_item_is_not_misclassified_as_tool_use() -> None:
    output = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": str(uuid.uuid4())}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "error", "message": "nonfatal startup notice"},
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "{}"},
                }
            ),
        ]
    )

    assert codex_used_disallowed_tool(output) is False


def test_codex_runner_preserves_thread_id_on_timeout(tmp_path: Path) -> None:
    thread_id = str(uuid.uuid4())
    script = (
        "import json,time; "
        f"print(json.dumps({{'type':'thread.started','thread_id':'{thread_id}'}}), flush=True); "
        "time.sleep(10)"
    )

    result = run_codex_command(
        [sys.executable, "-c", script],
        "prompt",
        tmp_path,
        0.5,
    )

    assert result.returncode == 124
    assert thread_id_from_jsonl(result.stdout) == thread_id


def test_codex_runner_stops_child_when_launcher_requests_stop(tmp_path: Path) -> None:
    stop_request = tmp_path / "stop.request"
    timer = threading.Timer(0.2, lambda: stop_request.write_text("stop"))
    timer.start()
    started_at = time.monotonic()
    try:
        result = run_codex_command(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            "prompt",
            tmp_path,
            30,
            stop_request,
        )
    finally:
        timer.cancel()

    assert result.returncode == 130
    assert time.monotonic() - started_at < 3
