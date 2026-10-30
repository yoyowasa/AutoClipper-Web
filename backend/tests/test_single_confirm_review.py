from final_output_fixtures import passing_final_inspection
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.jobs.pipeline_common import AutoClipperPipelineDependencies
from app.jobs.queue import get_enqueue_subtitle_review_preview, get_enqueue_subtitle_review_hook_scene_update
from app.jobs.runner import run_subtitle_review_hook_scene_update
import app.jobs.queue as queue_module
import app.storage.paths as paths_module
from app.main import app
from app.render.render_exact_review_preview import render_exact_subtitle_review_preview
from app.storage.paths import get_storage_paths
from test_api_routes import client as client, _seed_reeditable_export, _write_reeditable_preview_inputs
from test_render_exact_review_preview import make_candidate


def seed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, dict[str, Any], list[Any]]:
    monkeypatch.setattr("app.jobs.subtitle_review_preview.exact_subtitle_review_preview_is_ready", lambda *args: False)
    monkeypatch.setattr("app.jobs.subtitle_review_preview.live_subtitle_review_preview_is_ready", lambda *args: True)
    parent_id, clip_id, _ = _seed_reeditable_export()
    _write_reeditable_preview_inputs(parent_id, clip_id)
    job_id = client.post(f"/api/jobs/{parent_id}/clips/{clip_id}/reedit").json()["jobId"]
    calls: list[Any] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: lambda *args: calls.append(args)
    document = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    calls.clear()
    return job_id, clip_id, document, calls


def test_editing_then_single_confirm_queues_exact_preview_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, clip_id, document, calls = seed(client, monkeypatch)
    segment = document["segments"][0]
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": [{
        "segmentId": segment["id"], "before": segment["text"], "text": "新しい字幕",
    }]})
    assert response.status_code == 200
    assert calls == []
    assert response.json()["clips"][0]["previewState"] == "stale"
    segment = response.json()["segments"][0]
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "split", "segments": [{"segmentId": segment["id"], "before": segment["text"], "text": segment["text"]}],
        "splitOffset": 2, "splitTime": 1,
    })
    assert response.status_code == 200
    assert calls == []
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/settings", json={
        "shortTopBannerEnabled": True, "shortBottomBannerEnabled": False,
    })
    assert response.status_code == 200
    assert calls == []
    polled = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    assert calls == [], "GET must not restart exact previews while editing"
    assert polled["clips"][0]["previewState"] == "stale"
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/apply", json={
        "title": "新しいタイトル", "publicationTitle": "投稿タイトル", "hookText": "題材のフック",
        "hookSceneStart": 0, "hookSceneEnd": 3,
        "framing": {"framingOffsetX": 10, "framingOffsetY": 0, "framingZoom": 1.2, "shortLayout": "center_crop"},
        "segments": [{"segmentId": segment["id"], "text": "確定した字幕"} for segment in polled["segments"]],
    })
    assert response.status_code == 200
    assert len(calls) == 1
    clip = response.json()["clips"][0]
    assert clip["confirmed"] is True
    assert clip["previewDeferred"] is False
    assert clip["previewState"] == "queued"
    assert clip["framingOffsetX"] == 10
    assert clip["previewFraming"] is None
    assert clip["hookSceneEnd"] == 3
    assert all(segment["text"] == "確定した字幕" for segment in response.json()["segments"])


def test_finalize_requests_one_exact_preview_and_keeps_readiness_gate(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, clip_id, document, calls = seed(client, monkeypatch)
    segment = document["segments"][0]
    client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": [{
        "segmentId": segment["id"], "before": segment["text"], "text": "編集字幕",
    }]})
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/finalize")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "subtitle_review_preview_not_ready"
    assert len(calls) == 1
    assert calls[0][1] == clip_id


def test_failed_live_preview_waits_for_explicit_retry(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs.subtitle_review_preview import write_subtitle_review_preview_error

    job_id, clip_id, document, calls = seed(client, monkeypatch)
    segment = document["segments"][0]
    client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": [{
        "segmentId": segment["id"], "before": segment["text"], "text": "編集字幕",
    }]})
    monkeypatch.setattr("app.jobs.subtitle_review_preview.live_subtitle_review_preview_is_ready", lambda *args: False)
    polled = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    paths = app.dependency_overrides[get_storage_paths]()
    write_subtitle_review_preview_error(paths.job_outputs(job_id), clip_id,
        polled["clips"][0]["previewSpecHash"], "live render failed")
    calls.clear()
    failed = client.get(f"/api/jobs/{job_id}/subtitle-review").json()["clips"][0]
    assert failed["previewState"] == "failed"
    assert failed["previewDeferred"] is True
    assert failed["previewError"] == "live render failed"
    assert calls == []
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/preview/retry")
    assert response.status_code == 200
    assert response.json()["clips"][0]["previewDeferred"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["short", "normal"])
def test_live_only_render_does_not_create_exact_artifacts(tmp_path: Path, kind: str) -> None:
    outputs: list[tuple[Path, Any]] = []

    def renderer(_input: Any, output: Any, **kwargs: Any) -> Path:
        path = Path(output)
        path.write_bytes(b"live-video")
        outputs.append((path, kwargs.get("subtitle_path")))
        return path

    result = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4", tmp_path / "job", candidate=make_candidate("clip", kind),
        transcript_segments=[], settings={}, source_fingerprint="source", source_width=1920, source_height=1080,
        normal_renderer=renderer, short_renderer=renderer, live_only=True,
    )
    assert len(outputs) == 1
    assert outputs[0][1] is None
    assert result.live_path.is_file()
    assert not result.path.exists()
    assert not result.subtitle_path.exists()
    assert not result.spec_path.exists()


def test_hook_scene_worker_only_prepares_live_video(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, clip_id, _document, calls = seed(client, monkeypatch)
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: lambda *args: None
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/hook-scene", json={"start": 0, "end": 3})
    assert response.status_code == 202
    outputs: list[Path] = []

    def renderer(_input: Any, output: Any, **kwargs: Any) -> Path:
        path = Path(output)
        path.write_bytes(b"live-video")
        outputs.append(path)
        assert kwargs["subtitle_path"] is None
        return path

    storage = app.dependency_overrides[get_storage_paths]()
    statuses = run_subtitle_review_hook_scene_update(job_id, clip_id, 0, 3,
        session_factory=lambda: next(app.dependency_overrides[get_db]()), paths=storage,
        dependencies=AutoClipperPipelineDependencies(final_output_inspector=passing_final_inspection,
                                                    normal_renderer=renderer, short_renderer=renderer))
    assert statuses[-1] == "awaiting_subtitle_review"
    assert len(outputs) == 1 and "live" in outputs[0].parts
    assert calls == []
    document = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    assert document["clips"][0]["previewState"] == "stale"
    assert document["clips"][0]["confirmed"] is False


def test_apply_job_is_not_absorbed_by_running_live_job(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id, clip_id, document, _calls = seed(client, monkeypatch)
    segment = document["segments"][0]
    client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": [{
        "segmentId": segment["id"], "before": segment["text"], "text": "編集中",
    }]})
    polled = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    spec_hash = polled["clips"][0]["previewSpecHash"]
    enqueued: list[dict[str, Any]] = []

    class Queue:
        def get_job_ids(self) -> list[str]:
            return []

        def fetch_job(self, job_id: str) -> Any:
            if any(item["job_id"] == job_id for item in enqueued):
                return SimpleNamespace(get_status=lambda **kwargs: queue_module.JobStatus.STARTED)
            return None

        def enqueue(self, *args: Any, **kwargs: Any) -> None:
            enqueued.append(kwargs)

    storage = app.dependency_overrides[get_storage_paths]()
    monkeypatch.setattr(paths_module, "get_storage_paths", lambda: storage)
    monkeypatch.setattr(queue_module, "get_queue", lambda: Queue())
    monkeypatch.setattr(queue_module, "job_media_timeout", lambda *args, **kwargs: 3600)
    queue_module.enqueue_subtitle_review_preview(job_id, clip_id, spec_hash)
    assert enqueued[0]["job_id"].startswith("live_subtitle_review_preview-")
    from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review, subtitle_review_output_path

    path = subtitle_review_output_path(storage.job_outputs(job_id))
    stored = load_subtitle_review(path)
    stored.clips[0].preview_deferred = False
    stored.clips[0].confirmed = True
    write_subtitle_review(stored, path)
    queue_module.enqueue_subtitle_review_preview(job_id, clip_id, spec_hash)
    assert len(enqueued) == 2
    assert enqueued[1]["job_id"].startswith("subtitle_review_preview-")
    assert enqueued[0]["job_id"] != enqueued[1]["job_id"]
