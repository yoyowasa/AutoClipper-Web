import json
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.jobs.clip_plan import load_clip_plan, write_clip_plan
from app.jobs.clip_plan_runner import run_clip_plan_boundary_update
from app.jobs.queue import get_enqueue_clip_plan_boundary_update
from app.jobs.subtitle_review import subtitle_review_preview_path
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths
from test_api_routes import client as client
from test_duration_rules_api import editable_plan


def seed(api, source_type, manual=False):
    job_id, output = editable_plan(api, manual=manual, clip_type=source_type, duration=74 if source_type == "short" else 95)
    plan = load_clip_plan(output / "clip_plan.json")
    clip = next(clip for clip in plan.clips if clip.type == source_type)
    clip.hook_scene_start, clip.hook_scene_end = (72, 73) if source_type == "short" else (None, None)
    write_clip_plan(plan, output / "clip_plan.json")
    selection = json.loads((output / "selected_clips.json").read_text(encoding="utf-8"))
    selected = next(c for c in [*selection["normalClips"], *selection["shorts"]] if c["id"] == clip.id)
    selected.update(start=clip.start, end=clip.end, duration=clip.duration,
                    hook_scene_start=clip.hook_scene_start, hook_scene_end=clip.hook_scene_end)
    (output / "selected_clips.json").write_text(json.dumps(selection), encoding="utf-8")
    preview = subtitle_review_preview_path(output, clip.id)
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"old-preview")
    with next(app.dependency_overrides[get_db]()) as db:
        factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    paths = app.dependency_overrides[get_storage_paths]()
    return SimpleNamespace(id=job_id, output=output, clip=clip, preview=preview, paths=paths, factory=factory)


@pytest.mark.parametrize("workflow", ["auto", "manual", "manual_boundary"])
@pytest.mark.parametrize("source_type,target,end", [("short", "normal", 100), ("normal", "short", 70)])
def test_range_and_type_saved_together(client, workflow, source_type, target, end):
    data = seed(client, source_type, workflow != "auto")
    before = load_clip_plan(data.output / "clip_plan.json")
    untouched = next(c for c in before.clips if c.id != data.clip.id).model_dump()
    queued, renders = [], []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args, **kwargs: queued.append((args, kwargs))
    suffix = "" if workflow == "manual" else "/boundary"
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}{suffix}",
                            json={"start": 0, "end": end, "type": target})
    assert response.status_code == (200 if workflow == "manual" else 202), response.text
    if workflow == "auto":
        assert queued == [((data.id, data.clip.id, 0.0, float(end)), {"clip_type": target})]
        assert load_clip_plan(data.output / "clip_plan.json").clips == before.clips  # HTTP has not converted half the data.

        def render(source, output, **kwargs):
            renders.append(kwargs)
            output.write_bytes(b"new-preview")
            return output

        run_clip_plan_boundary_update(data.id, data.clip.id, 0, end, session_factory=data.factory, paths=data.paths,
            dependencies=SimpleNamespace(subtitle_review_preview_renderer=render), clip_type=target)
        assert renders == [{"start": 0.0, "duration": float(end)}]  # No former hook is rendered.
        selected = json.loads((data.output / "selected_clips.json").read_text(encoding="utf-8"))
        collection = "normalClips" if target == "normal" else "shorts"
        candidate = next(c for c in selected[collection] if c["id"] == data.clip.id)
        assert (candidate["type"], candidate["start"], candidate["end"]) == (target, 0, end)
        assert candidate["hook_scene_start"] is candidate["hook_scene_end"] is None
        with data.factory() as db:
            settings = db.get(Job, data.id).settings_json
            assert settings["normalClipCount"] == len(selected["normalClips"])
            assert settings["shortCount"] == len(selected["shorts"])
    else:
        assert queued == []
    plan = load_clip_plan(data.output / "clip_plan.json")
    converted = next(c for c in plan.clips if c.id == data.clip.id)
    assert (converted.type, converted.start, converted.end) == (target, 0, end)
    assert converted.title == data.clip.title and converted.id == data.clip.id
    assert converted.hook_scene_start is converted.hook_scene_end is None
    assert next(c for c in plan.clips if c.id != data.clip.id).model_dump() == untouched


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("target", ["short", "normal"])
def test_no_type_accepts_80_seconds_and_invalid_ranges_do_not_mutate(client, manual, target):
    data = seed(client, "short", manual)
    before = {p: p.read_bytes() for p in (data.output / "clip_plan.json", data.output / "selected_clips.json", data.preview)}
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *a, **k: queued.append(a)
    suffix = "" if manual else "/boundary"
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}{suffix}",
        json={"start": 0, "end": 80, "type": target})
    assert response.status_code == 422
    assert ("90秒以上" if target == "normal" else "75秒以内") in response.json()["detail"]
    assert all(path.read_bytes() == content for path, content in before.items()) and queued == []


@pytest.mark.parametrize("failure", ["queue", "render", "publication"])
def test_failed_conversion_restores_original_type_range_settings_and_preview(client, monkeypatch, failure):
    data = seed(client, "short")
    before = load_clip_plan(data.output / "clip_plan.json")
    selected = (data.output / "selected_clips.json").read_bytes()
    with data.factory() as db:
        settings = dict(db.get(Job, data.id).settings_json)

    def enqueue(*a, **kw):
        if failure == "queue":
            raise RuntimeError("synthetic queue failure")

    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: enqueue
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}/boundary",
                            json={"start": 0, "end": 100, "type": "normal"})
    if failure == "queue":
        assert response.status_code == 503
    else:
        assert response.status_code == 202

        def render(source, output, **kw):
            output.write_bytes(b"incomplete-preview")
            if failure == "render":
                raise RuntimeError("synthetic render failure")
            return output

        if failure == "publication":
            import app.jobs.clip_plan_runner as worker
            monkeypatch.setattr(worker, "invalidate_quality_gate_decisions", lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic")))
        with pytest.raises(RuntimeError):
            run_clip_plan_boundary_update(data.id, data.clip.id, 0, 100, session_factory=data.factory, paths=data.paths,
                dependencies=SimpleNamespace(subtitle_review_preview_renderer=render), clip_type="normal")
    restored = load_clip_plan(data.output / "clip_plan.json")
    assert restored.state == "awaiting_review" and restored.clips == before.clips and restored.settings == before.settings
    assert (data.output / "selected_clips.json").read_bytes() == selected
    assert data.preview.read_bytes() == b"old-preview"
    with data.factory() as db:
        job = db.get(Job, data.id)
        assert job.settings_json == settings and job.status == "awaiting_clip_review"


def test_boundary_reedit_rejects_conversion_before_queueing(client):
    data = seed(client, "short")
    plan = load_clip_plan(data.output / "clip_plan.json")
    plan.boundary_reedit = True
    write_clip_plan(plan, data.output / "clip_plan.json")
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}/boundary",
        json={"start": 0, "end": 100, "type": "normal"})
    assert response.status_code == 409 and "尺だけ" in response.json()["detail"]


@pytest.mark.parametrize("source_type,target,limit,end", [("short", "normal", 12, 100), ("normal", "short", 24, 70)])
def test_combined_update_keeps_type_count_limits(client, source_type, target, limit, end):
    data = seed(client, source_type)
    plan = load_clip_plan(data.output / "clip_plan.json")
    sample = next(c for c in plan.clips if c.type == target)
    plan.clips.extend(sample.model_copy(update={"id": f"extra_{i}"}) for i in range(limit - 1))
    write_clip_plan(plan, data.output / "clip_plan.json")
    before = (data.output / "clip_plan.json").read_bytes()
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}/boundary",
        json={"start": 0, "end": end, "type": target})
    assert response.status_code == 422 and "12本" in response.json()["detail"]
    assert (data.output / "clip_plan.json").read_bytes() == before


def test_old_boundary_request_keeps_hook_and_four_argument_queue_contract(client):
    data = seed(client, "short")
    calls = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: calls.append(args)
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/{data.clip.id}/boundary", json={"start": 0, "end": 75})
    assert response.status_code == 202 and calls == [(data.id, data.clip.id, 0, 75)]
    def render(source, output, **kwargs):
        assert kwargs["hook_start"] == 72 and kwargs["hook_duration"] == 1
        output.write_bytes(b"with-hook")
        return output
    run_clip_plan_boundary_update(data.id, data.clip.id, 0, 75, session_factory=data.factory, paths=data.paths,
        dependencies=SimpleNamespace(subtitle_review_preview_renderer=render))
    clip = next(c for c in load_clip_plan(data.output / "clip_plan.json").clips if c.id == data.clip.id)
    assert clip.type == "short" and (clip.hook_scene_start, clip.hook_scene_end) == (72, 73)


def test_rq_passes_conversion_as_optional_keyword_without_changing_legacy_args(monkeypatch):
    import app.jobs.queue as queue
    captured = []
    monkeypatch.setattr(queue, "get_queue", lambda: SimpleNamespace(enqueue=lambda *a, **k: captured.append((a, k))))
    monkeypatch.setattr(queue, "job_media_timeout", lambda *a, **k: 3600)
    queue.enqueue_clip_plan_boundary_update("job", "clip", 0, 100, clip_type="normal")
    assert captured[0][0][1:] == ("job", "clip", 0, 100) and captured[0][1]["clip_type"] == "normal"
    queue.enqueue_clip_plan_boundary_update("job", "clip", 0, 70)
    assert captured[1][0][1:] == ("job", "clip", 0, 70) and "clip_type" not in captured[1][1]
