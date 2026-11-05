"""Confirmed cue styles preserve shared captions and manual decisions."""
import pytest

from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review
from app.storage.paths import get_storage_paths
from app.db import get_db
from app.main import app
from app.models import Job
from test_api_routes import client as client
from test_subtitle_anytime import prepare
from test_guarded_quality_gate_integration import guarded_client as guarded_client


def payload(doc):
    cue = doc.segments[0]
    return {"clipId": "short", "segments": [], "beforeSubtitleStyles": [],
            "subtitleStyles": [{"start": cue.start, "end": cue.end,
                                "style": {"fontName": "Arial", "primaryColor": "#FF0000"}}]}


@pytest.mark.parametrize("state", ["awaiting_review", "rendering", "completed"])
def test_confirmed_cue_styles_preserve_other_clips_and_skip_codex(client, state):  # noqa: F811
    from app.jobs.pending_subtitle_edits import activate_pending
    job_id, path, before, _, _, queued = prepare(client, True)
    paths = app.dependency_overrides[get_storage_paths]()
    before.state = state
    write_subtitle_review(before, path)
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = {
            "awaiting_review": "awaiting_subtitle_review", "rendering": "rendering_shorts", "completed": "completed",
        }[state]
        db.commit()
    snapshot = path.read_bytes()
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json=payload(before))
    assert response.status_code == 200, response.text
    if state == "rendering":
        assert path.read_bytes() == snapshot and not queued
        with next(app.dependency_overrides[get_db]()) as db:
            db.get(Job, job_id).status = "completed"
            db.commit()
            assert activate_pending(db, job_id, paths, lambda *args: queued.append(args))
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    previous = next(c for c in before.clips if c.id == "short")
    assert target.confirmed and target.subtitle_styles[0].style.font_name == "Arial"
    assert target.subtitle_styles[0].style.primary_color == "#FF0000"
    assert target.manual_decision_fields == previous.manual_decision_fields
    assert target.automatic_decision_targets == [] and len(queued) == 1
    assert target.preview_state == "stale"
    assert [s.model_dump() for s in after.segments] == [s.model_dump() for s in before.segments]
    assert [c.model_dump() for c in after.clips if c.id != "short"] == [c.model_dump() for c in before.clips if c.id != "short"]
    if state == "completed":
        assert after.render_clip_ids == ["short"]


def test_stale_cue_styles_are_atomic_and_invalid_ranges_rejected(client):  # noqa: F811
    job_id, path, before, _, _, queued = prepare(client, True)
    request = payload(before)
    request["beforeSubtitleStyles"] = request["subtitleStyles"]
    snapshot = path.read_bytes()
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json=request).status_code == 409
    request = payload(before)
    request["subtitleStyles"][0].update(start=100, end=101)
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json=request).status_code == 422
    assert path.read_bytes() == snapshot and not queued


def test_completed_style_only_refresh_reaches_preview_and_export_ass(guarded_client, monkeypatch, tmp_path):  # noqa: F811
    from test_guarded_quality_gate_integration import _decision
    from test_subtitle_only_auto import setup_auto, confirm, decide
    import app.jobs.runner as runner
    import app.jobs.queue as queue
    from sqlalchemy import select
    from app.models import ExportItem
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=False)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    monkeypatch.setattr(queue, "enqueue_subtitle_review_render", lambda *args: data.renders.append(args))
    runner.run_subtitle_review_preview(*data.previews[-1], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    monkeypatch.setattr(runner, "evaluate_post_render_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="post_render", outcome="pass", mode="auto"))
    assert runner.run_subtitle_review_render(data.renders[-1][0], render_revision=data.renders[-1][1],
                                            paths=data.storage, session_factory=data.factory,
                                            dependencies=data.deps)[-1] == "completed"
    before = load_subtitle_review(data.review_path)
    clip = before.clips[0]
    first = before.segments[0]
    with data.factory() as db:
        export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
        old_id = export.id
    response = data.client.patch(f"/api/jobs/{data.job_id}/subtitle-review/segments", json={"clipId": clip.id,
        "segments": [], "beforeSubtitleStyles": [s.model_dump(mode="json", by_alias=True) for s in clip.subtitle_styles],
        "subtitleStyles": [{"start": first.start, "end": first.end, "style": {"fontName": "Arial", "primaryColor": "#FF0000"}}]})
    assert response.status_code == 200, response.text
    updated = load_subtitle_review(data.review_path)
    assert updated.render_clip_ids == [clip.id] and updated.render_revision == before.render_revision + 1
    assert updated.clips[0].confirmed
    assert "thumbnail_image" not in updated.clips[0].automatic_decision_targets
    # Existing frame candidates/asset geometry do not need another full scan.
    assert updated.clips[0].automatic_decision_targets == []
    from app.jobs.confirmed_clip_decisions import run_confirmed_clip_decisions
    assert run_confirmed_clip_decisions(*data.decisions[-1], paths=data.storage, session_factory=data.factory,
        generator=lambda **kw: pytest.fail("style-only edit called Codex"),
        enqueue_preview=lambda *args: data.previews.append(args)) == "ready"
    assert data.previews[-1][2] != data.previews[0][2]
    runner.run_subtitle_review_preview(*data.previews[-1], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    assert runner.run_subtitle_review_render(data.renders[-1][0], render_revision=data.renders[-1][1],
                                            paths=data.storage, session_factory=data.factory,
                                            dependencies=data.deps)[-1] == "completed"
    with data.factory() as db:
        export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
        assert export.id != old_id
        assert data.storage.production_record(export.id).is_file()
    from app.jobs.subtitle_review import apply_reviewed_clip_content
    from app.candidates.select_candidates import CandidateSelection
    from app.render.subtitles_ass import build_ass_document
    import json
    selection = CandidateSelection.model_validate(json.loads(
        (data.review_path.parent / "selected_clips.json").read_text(encoding="utf-8")))
    reviewed = load_subtitle_review(data.review_path)
    candidate = apply_reviewed_clip_content(selection, reviewed).normal_clips[0]
    ass = build_ass_document(candidate, [])
    assert candidate.subtitle_styles[0].style.font_name == "Arial"
    assert candidate.subtitle_styles[0].style.primary_color == "#FF0000"
    assert "[Events]" in ass




def test_style_edit_during_decision_preserves_inflight_request(client):  # noqa: F811
    from app.jobs.pending_subtitle_edits import activate_pending
    job_id, path, before, _, _, queued = prepare(client, True)
    paths = app.dependency_overrides[get_storage_paths]()
    target = next(c for c in before.clips if c.id == "short")
    target.automatic_decision_state = "generating"
    target.automatic_decision_revision = "in-flight"
    write_subtitle_review(before, path)
    snapshot = path.read_bytes()
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json=payload(before))
    assert response.status_code == 200, response.text
    assert path.read_bytes() == snapshot and not queued
    with next(app.dependency_overrides[get_db]()) as db:
        assert not activate_pending(db, job_id, paths, lambda *args: queued.append(args))
        target.automatic_decision_state = "ready"
        target.title = "進行中の自動決定が完了した値"
        write_subtitle_review(before, path)
        assert activate_pending(db, job_id, paths, lambda *args: queued.append(args))
    saved = next(c for c in load_subtitle_review(path).clips if c.id == "short")
    assert saved.title == target.title and saved.automatic_decision_targets == []
    assert saved.subtitle_styles and saved.confirmed and len(queued) == 1


def test_text_and_style_save_together_use_existing_copy_on_write(client):  # noqa: F811
    job_id, path, before, _, _, queued = prepare(client, True)
    request = payload(before)
    cue = before.segments[0]
    request["segments"] = [{"segmentId": cue.id, "before": cue.text, "text": "手で修正した字幕"}]
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json=request)
    assert response.status_code == 200, response.text
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    assert target.confirmed and target.subtitle_styles and len(queued) == 1
    assert "title_hook" in target.automatic_decision_targets  # text changed, unlike style-only
    assert any(s.text == "手で修正した字幕" and s.affected_clip_ids == ["short"] for s in after.segments)
    assert [c.model_dump() for c in after.clips if c.id != "short"] == [c.model_dump() for c in before.clips if c.id != "short"]
