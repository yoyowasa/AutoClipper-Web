import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.intelligence.analysis_bridge import ChannelAnalysisGenerator, cleanup_analysis_files
from app.intelligence.analysis_input import build_analysis_input
from app.intelligence.analysis_schema import analysis_response_schema
from app.intelligence.analysis_runner import analysis_job_timeout
from app.intelligence.maintenance import maintain_youtube
from app.intelligence.models import AnalysisRun
from app.intelligence.queue import enqueue_channel_analysis
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_channel_analysis import CLOCK, prepared as prepared, valid_review, execute, URL
from test_intelligence import environment as environment

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from launcher import codex_bridge as host  # noqa: E402


def test_legacy_profiles_and_fingerprints_unchanged_and_analysis_schema_pinned():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "codex_profiles_before_task208.json").read_text(encoding="utf-8"))
    assert host.CODEX_MODEL == fixture["model"] and host.CODEX_REASONING_EFFORT == fixture["effort"]
    assert {key: value for key, value in host.EXPECTED_RESPONSE_SCHEMA_SHA256.items()
            if key != "channel_self_analysis"} == fixture["schemas"]
    schema = analysis_response_schema()
    assert host._response_schema_sha256(schema) == host.EXPECTED_RESPONSE_SCHEMA_SHA256["channel_self_analysis"]
    assert len(json.dumps(schema).encode()) < host.MAX_RESPONSE_SCHEMA_BYTES
    host._validated_response_schema(schema, task="channel_self_analysis")
    modified = {**schema, "description": "modified"}
    with pytest.raises(ValueError, match="response_schema_contract_mismatch"):
        host._validated_response_schema(modified, task="channel_self_analysis")


@pytest.mark.parametrize("outcome", ["ready", "timeout", "invalid"])
def test_analysis_uses_astra_high_900_seconds_and_cleans_private_scratch(tmp_path, monkeypatch, outcome):
    monkeypatch.setenv("AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT", str(tmp_path / "private"))
    root = tmp_path / "project"
    paths = host.bridge_paths(root)
    host.ensure_bridge_directories(paths)
    id = uuid4().hex
    payload = {"schemaVersion": 1, "task": "channel_self_analysis", "requestId": id, "prompt": "synthetic private title",
               "responseSchema": analysis_response_schema(), "images": [], "threadScope": "channel_analysis:1", "model": "gpt-6-astra",
               "expiresAt": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    path = paths.requests / f"{id}.json"
    host.atomic_write_json(path, payload)
    captures = []
    def fake(command, prompt, cwd, timeout, stop):
        captures.append((command, timeout))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"transport": "synthetic"}), encoding="utf-8")
        (cwd / "synthetic.txt").write_text("private title", encoding="utf-8")
        marker = host.private_bridge_paths(root).work / id / ".channel-self-analysis"
        assert host.read_json_object(marker)["expiresAt"] == datetime.fromisoformat(payload["expiresAt"]).timestamp()
        if outcome == "timeout":
            return host.CodexRunResult(124, "", "synthetic private timeout")
        if outcome == "invalid":
            output.write_text("invalid JSON", encoding="utf-8")
        return host.CodexRunResult(0, json.dumps({"type": "thread.started", "thread_id": str(uuid4())}))
    response = host.process_request_file(path, project_root=root, codex_executable="codex", runner=fake)
    assert response["state"] == ("ready" if outcome == "ready" else "failed")
    command, timeout = captures[0]
    assert command[command.index("--model") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="high"' in command and "--ephemeral" in command
    assert 'history.persistence="none"' in command and timeout == 900
    private = host.private_bridge_paths(root)
    assert not (private.sessions / id).exists() and not (private.work / id).exists()
    assert not list(private.threads.glob("*.json"))


@pytest.mark.parametrize("change", [{"images": ["example.png"]}, {"threadId": "legacy-thread"},
                                    {"model": "gpt-5.6-sol"}, {"model": {"invalid": True}},
                                    {"expiresAt": "2020-01-01T00:00:00Z"}, {"expiresAt": "2026-11-01T00:00:00"}])
def test_analysis_rejects_images_resume_or_model_override(tmp_path, change):
    payload = {"schemaVersion": 1, "task": "channel_self_analysis", "requestId": uuid4().hex,
               "prompt": "text", "responseSchema": analysis_response_schema(), "images": [],
               "threadScope": "analysis:1", "expiresAt": (datetime.now(UTC) + timedelta(hours=1)).isoformat(), **change}
    with pytest.raises(ValueError, match="analysis_request_invalid"):
        host.validate_request(payload, tmp_path)


def test_private_analysis_scratch_expiry_preserves_other_tasks_and_fresh_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIPPER_CODEX_BRIDGE_PRIVATE_ROOT", str(tmp_path / "private"))
    root = tmp_path / "project"
    private = host.private_bridge_paths(root)
    old, fresh, legacy = uuid4().hex, uuid4().hex, uuid4().hex
    for id in (old, fresh, legacy):
        for base in (private.work, private.sessions):
            (base / id).mkdir(parents=True)
            (base / id / "private.txt").write_text("synthetic metadata", encoding="utf-8")
    stamp = 40 * 86400
    host.atomic_write_json(private.work / old / ".channel-self-analysis", {"expiresAt": stamp})
    host.atomic_write_json(private.work / fresh / ".channel-self-analysis", {"expiresAt": stamp + 3600})
    host.expire_analysis_scratch(root, clock=stamp)
    for base in (private.work, private.sessions):
        assert not (base / old).exists()
        assert (base / fresh).exists() and (base / legacy).exists()


def test_real_bridge_envelope_and_parser_without_codex_execution(prepared):
    context = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    requests = []
    def respond(id):
        requests.append(id)
        write_json_atomic(prepared.paths.analysis_bridge_files(id)[2], {"schemaVersion": 1, "requestId": id,
            "state": "ready", "threadId": None, "output": valid_review(context), "error": None})
    generator = ChannelAnalysisGenerator(paths=prepared.paths, run_id="analysis_test", on_request=respond)
    result = generator.analyze(context)
    assert result["id"] == "analysis_test" and len(requests) == 1
    envelope = json.loads(prepared.paths.analysis_bridge_files(requests[0])[0].read_text(encoding="utf-8"))
    assert envelope["task"] == "channel_self_analysis" and envelope["model"] == "gpt-6-astra"
    assert datetime.fromisoformat(envelope["expiresAt"]).replace(tzinfo=None) == context.expires_at
    assert "<untrusted_channel_data>" in envelope["prompt"] and envelope["images"] == []
    host.validate_request(envelope, prepared.paths.root)
    cleanup_analysis_files(prepared.paths, requests[0])
    assert all(not path.exists() for path in prepared.paths.analysis_bridge_files(requests[0]))


def test_queue_time_budget_and_expired_bridge_cleanup(client, prepared, monkeypatch):
    import app.intelligence.queue as queue
    from datetime import timedelta
    captured = []
    monkeypatch.setattr(queue, "get_intelligence_queue", lambda: SimpleNamespace(enqueue=lambda *args, **kwargs: captured.append(kwargs)))
    enqueue_channel_analysis("analysis_test")
    assert captured[0]["job_timeout"] == analysis_job_timeout(get_settings()) == 1140
    id = client.post(URL, json={"syncBefore": "never"}).json()["id"]
    run = execute(prepared, id)
    artifacts = prepared.paths.analysis_bridge_files(run.request_id)
    for path in artifacts:
        write_json_atomic(path, {"title": "expired synthetic metadata"})
    maintain_youtube(prepared.db, prepared.config, prepared.paths, [], clock=CLOCK + timedelta(days=30))
    prepared.db.expire_all()
    assert prepared.db.get(AnalysisRun, id).review is None
    assert all(not path.exists() for path in artifacts)
