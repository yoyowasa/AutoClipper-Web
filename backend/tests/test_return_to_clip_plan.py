import json
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.jobs.clip_plan import load_clip_plan
from app.jobs.queue import get_enqueue_clip_plan_reselection, get_enqueue_clip_plan_boundary_update
from app.jobs.clip_plan_runner import run_clip_plan_boundary_update
from app.jobs.runner import run_subtitle_review_preview
from app.jobs.subtitle_review import load_subtitle_review, subtitle_review_preview_path, write_subtitle_review
from app.main import app
from app.models import Job, Video
from app.storage.paths import get_storage_paths
from test_api_routes import client as client
from test_clip_plan_type_conversion import seed_plan


def approved(api):
    job_id, output = seed_plan(api, duration=100, short_max=120)
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        db.get(Video, job.video_id).duration = 300
        job.settings_json = {**job.settings_json, "_keptClipIds": ["normal0"]}
        settings = dict(job.settings_json)
        factory = sessionmaker(bind=db.get_bind())
        db.commit()
    before = load_clip_plan(output / "clip_plan.json")
    response = api.post(f"/api/jobs/{job_id}/clip-plan/approve")
    assert response.status_code == 200, response.text
    return SimpleNamespace(id=job_id, output=output, plan=before, settings=settings, factory=factory,
        paths=app.dependency_overrides[get_storage_paths](), endpoint=f"/api/jobs/{job_id}/subtitle-review/return-to-clip-plan")


def test_return_preserves_approved_selection_discards_review_and_rebuilds(client):
    data = approved(client)
    original_selection = json.loads((data.output / "selected_clips.json").read_text(encoding="utf-8"))
    review = load_subtitle_review(data.output / "subtitle_review.json")
    review.segments[0].text = "破棄する字幕"
    review.clips[0].title = "破棄するタイトル"
    review.clips[0].framing_zoom = 1.5
    write_subtitle_review(review, data.output / "subtitle_review.json")
    preview = subtitle_review_preview_path(data.output, "normal0")
    preview.parent.mkdir(exist_ok=True)
    preview.write_bytes(b"clip plan preview to retain")
    exact = preview.with_suffix("") / "live" / "old.mp4"
    exact.parent.mkdir(parents=True)
    exact.write_bytes(b"discard")
    with data.factory() as db:
        job = db.get(Job, data.id)
        job.settings_json = {**job.settings_json, "shortLayout": "center_crop", "characterPresetName": "discard"}
        db.commit()
    response = client.post(data.endpoint)
    assert response.status_code == 200, response.text
    plan = load_clip_plan(data.output / "clip_plan.json")
    assert plan.state == "awaiting_review" and plan.boundary_reedit is False
    assert plan.clips == data.plan.clips
    assert json.loads((data.output / "selected_clips.json").read_text(encoding="utf-8")) == original_selection
    assert preview.read_bytes() == b"clip plan preview to retain"
    assert not (data.output / "subtitle_review.json").exists()
    assert not (data.output / "subtitle_review_summary.json").exists()
    assert not exact.exists() and not list(data.output.glob(".discarded-review-*"))
    with data.factory() as db:
        assert db.get(Job, data.id).settings_json == data.settings
        assert db.get(Job, data.id).status == "awaiting_clip_review"
    assert client.post(data.endpoint).status_code == 409
    # The ordinary range-update path is available, including the real worker publication.
    boundary_jobs = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: boundary_jobs.append(args)
    response = client.patch(f"/api/jobs/{data.id}/clip-plan/clips/normal0/boundary", json={"start": 0, "end": 110})
    assert response.status_code == 202 and boundary_jobs == [(data.id, "normal0", 0, 110)]
    def render(source, target, **kw):
        target.write_bytes(b"updated range preview")
        return target
    run_clip_plan_boundary_update(data.id, "normal0", 0, 110, session_factory=data.factory, paths=data.paths,
        dependencies=SimpleNamespace(subtitle_review_preview_renderer=render))
    assert load_clip_plan(data.output / "clip_plan.json").clips[0].end == 110
    # The regular type API and keep/reselection are available again, not boundary-only mode.
    assert client.patch(f"/api/jobs/{data.id}/clip-plan/clips/normal0/type", json={"type": "short"}).status_code == 200
    assert client.post(f"/api/jobs/{data.id}/clip-plan/approve").status_code == 200
    rebuilt = load_subtitle_review(data.output / "subtitle_review.json")
    assert rebuilt.preview_generation and rebuilt.created_at != review.created_at
    assert all(s.text != "破棄する字幕" for s in rebuilt.segments)
    assert rebuilt.clips[0].title != "破棄するタイトル" and not any(c.confirmed for c in rebuilt.clips)
    assert client.post(data.endpoint).status_code == 200
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: lambda job_id: queued.append(job_id)
    request = {key: data.settings[key] for key in (
        "normalClipSelectionPreset", "shortClipSelectionPreset", "normalClipGuidance", "shortClipGuidance",
        "excludeIntroOutro", "excludePromotionalContent", "selectionPolicy")}
    response = client.post(f"/api/jobs/{data.id}/clip-plan/reselect", json={**request, "keptClipIds": ["normal1"]})
    assert response.status_code == 202, response.text
    assert queued == [data.id]


@pytest.mark.parametrize("state", ["rendering_normal_clips", "completed", "failed", "queued"])
def test_return_rejects_non_review_job_without_changing_files(client, state):
    data = approved(client)
    before = (data.output / "subtitle_review.json").read_bytes()
    with data.factory() as db:
        db.get(Job, data.id).status = state
        db.commit()
    response = client.post(data.endpoint)
    assert response.status_code == 409 and "字幕確認中だけ" in response.json()["detail"]
    assert (data.output / "subtitle_review.json").read_bytes() == before


@pytest.mark.parametrize("manual,review_state", [(True, "awaiting_review"), (False, "rendering"), (False, "completed")])
def test_return_rejects_manual_or_finalized_review(client, manual, review_state):
    data = approved(client)
    if manual:
        with data.factory() as db:
            job = db.get(Job, data.id)
            job.settings_json = {**job.settings_json, "workflowMode": "manual"}
            db.commit()
    else:
        review = load_subtitle_review(data.output / "subtitle_review.json")
        review.state = review_state
        write_subtitle_review(review, data.output / "subtitle_review.json")
    response = client.post(data.endpoint)
    assert response.status_code == 409
    if manual:
        assert "手動ワークフロー" in response.json()["detail"]
        assert client.get(f"/api/jobs/{data.id}/subtitle-review").json()["returnToClipPlanAllowed"] is False


def test_queued_preview_is_discarded_even_after_identical_review_is_recreated(client):
    data = approved(client)
    old = load_subtitle_review(data.output / "subtitle_review.json")
    old_hash = old.clips[0].preview_spec_hash
    assert client.post(data.endpoint).status_code == 200
    assert run_subtitle_review_preview(data.id, "normal0", old_hash, session_factory=data.factory, paths=data.paths) == ["superseded"]
    assert client.post(f"/api/jobs/{data.id}/clip-plan/approve").status_code == 200
    new = load_subtitle_review(data.output / "subtitle_review.json")
    assert new.clips[0].preview_spec_hash != old_hash
    before = (data.output / "subtitle_review.json").read_bytes()
    assert run_subtitle_review_preview(data.id, "normal0", old_hash, session_factory=data.factory, paths=data.paths) == ["superseded"]
    assert (data.output / "subtitle_review.json").read_bytes() == before


@pytest.mark.parametrize("reapprove", [False, True])
@pytest.mark.parametrize("render_fails", [False, True])
def test_return_during_preview_render_does_not_publish_or_auto_render(client, monkeypatch, reapprove, render_fails):
    import app.jobs.runner as runner
    from app.render.render_exact_review_preview import exact_subtitle_review_preview_paths

    data = approved(client)
    old = load_subtitle_review(data.output / "subtitle_review.json")
    old_hash = old.clips[0].preview_spec_hash
    old_paths = exact_subtitle_review_preview_paths(data.output, "normal0", old_hash)

    def render(**kwargs):
        assert client.post(data.endpoint).status_code == 200
        if reapprove:
            assert client.post(f"/api/jobs/{data.id}/clip-plan/approve").status_code == 200
        old_paths.video_path.parent.mkdir(parents=True, exist_ok=True)
        old_paths.video_path.write_bytes(b"old render completed after return")
        if render_fails:
            raise RuntimeError("obsolete render interrupted")
        return SimpleNamespace(spec_hash=old_hash)

    monkeypatch.setattr(runner, "_render_exact_subtitle_review_preview_for_clip", render)
    monkeypatch.setattr(runner, "_prepare_auto_render_after_preview", lambda **kw: pytest.fail("obsolete work must never finalize"))
    result = run_subtitle_review_preview(data.id, "normal0", old_hash, session_factory=data.factory, paths=data.paths)
    assert result == ["superseded"] and not old_paths.video_path.exists()
    with data.factory() as db:
        assert db.get(Job, data.id).status == ("awaiting_subtitle_review" if reapprove else "awaiting_clip_review")


@pytest.mark.parametrize("failure", ["file", "database"])
def test_return_file_failure_rolls_back_without_losing_review(client, monkeypatch, failure):
    from app.jobs import return_to_clip_plan as operation
    data = approved(client)
    before = {name: (data.output / name).read_bytes() for name in ("clip_plan.json", "selected_clips.json", "subtitle_review.json")}
    if failure == "file":
        monkeypatch.setattr(operation, "write_selected_clips", lambda *a: (_ for _ in ()).throw(OSError("synthetic")))
    else:
        from sqlalchemy.orm import Session
        monkeypatch.setattr(Session, "commit", lambda *a: (_ for _ in ()).throw(OSError("synthetic")))
    with pytest.raises(OSError, match="synthetic"):
        client.post(data.endpoint)
    assert all((data.output / name).read_bytes() == content for name, content in before.items())
    assert not list(data.output.glob(".discarded-review-*"))
    with data.factory() as db:
        assert db.get(Job, data.id).status == "awaiting_subtitle_review"


def test_reselection_preserves_review_generation_for_kept_clips(client, monkeypatch):
    from app.jobs.pipeline_common import _prepare_clip_plan_review
    from app.candidates.select_candidates import CandidateSelection
    data = approved(client)
    assert client.post(data.endpoint).status_code == 200
    old_plan = load_clip_plan(data.output / "clip_plan.json")
    selection = CandidateSelection.model_validate_json((data.output / "selected_clips.json").read_text(encoding="utf-8"))
    with data.factory() as db:
        job = db.get(Job, data.id)
        video = db.get(Video, job.video_id)
        settings = {**job.settings_json, "keptClipIds": ["normal0"]}
        def preview(source, target, **kw):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"preview")
            return target
        _prepare_clip_plan_review(db=db, job=job, input_path=data.paths.resolve_stored_file(video.stored_path),
            selection=selection, settings=settings, job_dir=data.output, preview_renderer=preview,
            source_duration=300, kept_plan=old_plan)
    rebuilt = load_clip_plan(data.output / "clip_plan.json")
    assert rebuilt.subtitle_review_generation == old_plan.subtitle_review_generation
    assert rebuilt.clips[0].model_dump(exclude={"preview_video_url"}) == old_plan.clips[0].model_dump(exclude={"preview_video_url"})


@pytest.mark.parametrize("keep_ids,expected", [(["normal1"], 200), (["missing"], 422)])
def test_next_persists_keep_choices_for_return_without_reselection(client, keep_ids, expected):
    job_id, output = seed_plan(client, duration=100)
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Video, db.get(Job, job_id).video_id).duration = 300
        db.commit()
    response = client.post(f"/api/jobs/{job_id}/clip-plan/approve", json={"keptClipIds": keep_ids})
    assert response.status_code == expected, response.text
    if expected == 200:
        assert client.post(f"/api/jobs/{job_id}/subtitle-review/return-to-clip-plan").status_code == 200
        assert load_clip_plan(output / "clip_plan.json").settings["keptClipIds"] == keep_ids
