"""Task238: atomic drafts, confirmed COW, selective refresh and render races."""
import pytest

from app.db import get_db
from app.jobs.automation import AUTOMATION_POLICY_SETTING, SUBTITLE_ONLY_AUTO_POLICY
from app.jobs.queue import get_enqueue_confirmed_clip_decisions
from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review, apply_reviewed_text
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths
from test_api_routes import client as client
from test_subtitle_structure import seed_structure, items
from test_subtitle_only_auto import setup_auto, confirm, decide
from test_guarded_quality_gate_integration import guarded_client as guarded_client


def prepare(api, confirmed=False):
    job_id, path, doc, original, normal = seed_structure(api)
    doc.subtitle_only_auto = True
    for clip in doc.clips:
        clip.confirmed = clip.id != "short" or confirmed
        clip.automatic_decision_state = "ready"
        clip.preview_state = "ready"
        clip.preview_spec_hash = f"saved-{clip.id}"
        clip.preview_video_url = f"/saved/{clip.id}.mp4"
    target = next(c for c in doc.clips if c.id == "short")
    target.manual_decision_fields = ["framing", "publication_title"]
    target.framing_offset_x = 13
    target.publication_title = "人が指定したタイトル"
    write_subtitle_review(doc, path)
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        job.settings_json = {**job.settings_json, "automationMode": "auto", AUTOMATION_POLICY_SETTING: SUBTITLE_ONLY_AUTO_POLICY}
        db.commit()
    queued = []
    app.dependency_overrides[get_enqueue_confirmed_clip_decisions] = lambda: lambda *args: queued.append(args)
    return job_id, path, doc, original, normal, queued


@pytest.mark.parametrize("confirmed", [False, True])
def test_insert_saves_overlapping_and_nonoverlapping_drafts_atomically(client, confirmed):  # noqa: F811
    job_id, path, before, original, normal, queued = prepare(client, confirmed)
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "clipId": "short", "action": "insert_at_time", "segments": [], "start": 1.4, "end": 1.8, "text": "追加する文字",
        "edits": [{"segmentId": s.id, "before": s.text, "text": f"手直し{i}"} for i, s in enumerate(before.segments[:2])],
    })
    assert response.status_code == 200, response.text
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    assert target.confirmed is confirmed
    assert len(queued) == int(confirmed)
    assert all(a.model_dump() == b.model_dump() for a, b in zip(after.clips[:2], before.clips[:2], strict=True))
    text = [s.text for s in after.segments if "short" in s.affected_clip_ids]
    assert set(text) == {"手直し0", "手直し1", "追加する文字"}
    assert target.manual_decision_fields == ["framing", "publication_title"]
    assert target.framing_offset_x == 13 and target.publication_title == "人が指定したタイトル"
    from app.render.subtitles_ass import build_ass_document
    rendered = apply_reviewed_text(original, after)
    assert build_ass_document(normal, rendered) == build_ass_document(normal, apply_reviewed_text(original, before))
    assert "追加する文字" in build_ass_document(normal.model_copy(update={"id": "short", "type": "short"}), rendered)


@pytest.mark.parametrize("action", ["text", "line", "split", "merge", "delete", "insert", "insert_at_time"])
def test_confirmed_edits_keep_confirmation_and_only_refresh_target(client, action):  # noqa: F811
    job_id, path, before, _, _, queued = prepare(client, True)
    base = f"/api/jobs/{job_id}/subtitle-review"
    if action == "text":
        response = client.patch(f"{base}/segments", json={"clipId": "short", "segments": [
            {"segmentId": before.segments[0].id, "before": before.segments[0].text, "text": "修正した文字"}]})
    else:
        payload = {"clipId": "short", "action": action, "segments": items(before.segments[0])}
        if action == "line":
            payload["segments"][0]["text"] = "修正した文字"
        if action == "split":
            payload.update(splitOffset=1, splitTime=1.5)
        if action == "merge":
            payload["segments"] = items(*before.segments[:2])
        if action == "insert":
            payload.update(splitTime=1.5, insertPosition="after")
        if action == "insert_at_time":
            payload.update(segments=[], start=4, end=5, text="新しい字幕")
        response = client.post(f"{base}/segment-structure", json=payload)
    assert response.status_code == 200, response.text
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    assert target.confirmed and target.automatic_decision_state == "queued" and target.preview_state == "stale"
    assert len(queued) == 1 and queued[0][1] == "short"
    assert "framing" not in target.automatic_decision_targets
    assert all(a.model_dump() == b.model_dump() for a, b in zip(after.clips[:2], before.clips[:2], strict=True))
    assert target.framing_offset_x == 13 and target.publication_title == "人が指定したタイトル"


def test_stale_atomic_edit_does_not_partially_save(client):  # noqa: F811
    job_id, path, before, _, _, queued = prepare(client)
    snapshot = path.read_bytes()
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "clipId": "short", "action": "insert_at_time", "segments": [], "start": 4, "end": 5, "text": "追加",
        "edits": [{"segmentId": s.id, "before": "古い文字" if i else s.text, "text": "修正"}
                  for i, s in enumerate(before.segments[:2])],
    })
    assert response.status_code == 409
    assert path.read_bytes() == snapshot and not queued


def test_edit_during_render_is_durable_then_activates_without_overwriting_decisions(client):  # noqa: F811
    from app.jobs.pending_subtitle_edits import activate_pending
    job_id, path, before, _, _, queued = prepare(client, True)
    paths = app.dependency_overrides[get_storage_paths]()
    before.state = "rendering"
    write_subtitle_review(before, path)
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = "rendering_shorts"
        db.commit()
    snapshot = path.read_bytes()
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "clipId": "short", "action": "insert_at_time", "segments": [], "start": 4, "end": 5, "text": "書き出し中の追加"})
    assert response.status_code == 200, response.text
    assert path.read_bytes() == snapshot and paths.pending_subtitle_edits(job_id).is_file() and not queued
    response = client.get(f"/api/jobs/{job_id}/subtitle-review")
    assert response.status_code == 200 and response.json()["pendingSubtitleClipIds"] == ["short"]
    with next(app.dependency_overrides[get_db]()) as db:
        assert not activate_pending(db, job_id, paths, lambda *args: queued.append(args))
        # A renderer can finish/repair noncaption fields while edits wait.
        latest = load_subtitle_review(path)
        latest.state = "completed"
        target = next(c for c in latest.clips if c.id == "short")
        target.hook_text = "書き出し工程が直した値を残す"
        write_subtitle_review(latest, path)
        db.get(Job, job_id).status = "completed"
        db.commit()
        assert activate_pending(db, job_id, paths, lambda *args: queued.append(args))
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    assert target.confirmed and target.hook_text == "書き出し工程が直した値を残す"
    assert after.has_saved_review_changes
    assert any(s.text == "書き出し中の追加" for s in after.segments)
    assert after.clips[0].model_dump() == latest.clips[0].model_dump()
    assert len(queued) == 1 and not paths.pending_subtitle_edits(job_id).exists()


def test_completed_edit_uses_partial_render_and_rebuilds_exact_preview(guarded_client, monkeypatch, tmp_path):  # noqa: F811
    from test_guarded_quality_gate_integration import _decision
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
    first = before.segments[0]
    with data.factory() as db:
        export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
        old_id = export.id
    response = data.client.patch(f"/api/jobs/{data.job_id}/subtitle-review/segments", json={"clipId": clip.id,
        "segments": [{"segmentId": first.id, "before": first.text, "text": "完成した後でも字幕を修正する"}]})
    assert response.status_code == 200, response.text
    updated = load_subtitle_review(data.review_path)
    assert updated.render_clip_ids == [clip.id] and updated.render_revision == before.render_revision + 1
    assert updated.clips[0].confirmed
    assert "thumbnail_image" not in updated.clips[0].automatic_decision_targets
    # Existing frame candidates/asset geometry do not need another full scan.
    assert run_decisions_without_scan(data) == "ready"
    assert data.previews[-1][2] != data.previews[0][2]
    runner.run_subtitle_review_preview(*data.previews[-1], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    assert runner.run_subtitle_review_render(data.renders[-1][0], render_revision=data.renders[-1][1],
                                            paths=data.storage, session_factory=data.factory,
                                            dependencies=data.deps)[-1] == "completed"
    with data.factory() as db:
        export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
        assert export.id != old_id
        assert data.storage.production_record(export.id).is_file()


def run_decisions_without_scan(data):
    from app.jobs.confirmed_clip_decisions import run_confirmed_clip_decisions
    return run_confirmed_clip_decisions(*data.decisions[-1], paths=data.storage, session_factory=data.factory,
        generator=data.deps.auto_title_hook_generator, thumbnail_generator=data.deps.thumbnail_copy_generator,
        candidate_extractor=lambda *a, **kw: pytest.fail("字幕で動画コマを再走査しない"),
        enqueue_preview=lambda *args: data.previews.append(args))


def test_selective_inputs_do_not_redo_range_only_thumbnail_or_base_fonts(client):  # noqa: F811
    from app.jobs.subtitle_decision_inputs import changed_targets, decision_inputs
    _, _, before, _, _, _ = prepare(client, True)
    target = next(c for c in before.clips if c.id == "short")
    target.manual_decision_fields = []
    target.type = "normal"
    target.automatic_thumbnail = {"thumbnail_frame_candidates": [{"id": "existing-frame"}]}
    target.automatic_decision_inputs = decision_inputs(before, target)
    after = before.model_copy(deep=True)
    after.segments[0].text = "字幕を変えた"
    updated = next(c for c in after.clips if c.id == "short")
    assert changed_targets(before, target, after, updated) == {"title_hook", "thumbnail_copy", "framing", "effects"}
    target.automatic_thumbnail = {"thumbnail_frame_candidates": [], "thumbnail_character_asset_id": "asset"}
    target.automatic_decision_inputs = decision_inputs(before, target)
    updated.automatic_thumbnail = dict(target.automatic_thumbnail)
    assert "thumbnail_image" in changed_targets(before, target, after, updated)


def test_insert_preserves_manual_row_styles_for_all_new_ranges(client):  # noqa: F811
    from app.candidates.merge_boundaries import ClipTextStyle, SubtitleStyleOverride
    job_id, path, before, _, _, _ = prepare(client, True)
    target = next(c for c in before.clips if c.id == "short")
    target.manual_decision_fields.append("subtitle_styles")
    target.subtitle_styles = [SubtitleStyleOverride(start=1, end=2, style=ClipTextStyle(fontSize=98))]
    write_subtitle_review(before, path)
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "clipId": "short", "action": "insert_at_time", "segments": [], "start": 1.3, "end": 1.7, "text": "追加"})
    assert response.status_code == 200, response.text
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    rows = [s for s in after.segments if s.start < 2 and "short" in s.affected_clip_ids]
    assert {(s.start, s.end) for s in target.subtitle_styles} == {(s.start, s.end) for s in rows}
    assert all(style.style.font_size == 98 for style in target.subtitle_styles)
    assert "effects" not in target.automatic_decision_targets
    assert target.confirmed


def test_pending_generation_does_not_leak_into_a_new_review(client):  # noqa: F811
    from app.jobs.pending_subtitle_edits import pending_view, save_pending
    job_id, _, before, _, _, _ = prepare(client, True)
    paths = app.dependency_overrides[get_storage_paths]()
    save_pending(before, {"short"}, paths)
    replacement = before.model_copy(deep=True)
    replacement.preview_generation = "new-generation"
    assert pending_view(replacement, paths).pending_subtitle_clip_ids == []
    save_pending(replacement, {"normal"}, paths)
    assert pending_view(replacement, paths).pending_subtitle_clip_ids == ["normal"]
    assert paths.pending_subtitle_edits(job_id).is_file()


def test_pending_legacy_inputs_are_compared_to_the_last_rendered_snapshot(client):  # noqa: F811
    from app.jobs.pending_subtitle_edits import save_pending
    job_id, path, before, _, _, queued = prepare(client, True)
    paths = app.dependency_overrides[get_storage_paths]()
    pending = before.model_copy(deep=True)
    from app.jobs.subtitle_review import update_review_segment
    update_review_segment(pending, before.segments[0].id, "書き出し中に保存した字幕", clip_id="short")
    save_pending(pending, {"short"}, paths)
    target = next(c for c in pending.clips if c.id == "short")
    second = next(s for s in pending.segments if s.id == target.segment_ids[1])
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"clipId": "short", "segments": [
        {"segmentId": second.id, "before": second.text, "text": "続けて修正した字幕"}]})
    assert response.status_code == 200, response.text
    after = load_subtitle_review(path)
    target = next(c for c in after.clips if c.id == "short")
    assert "title_hook" in target.automatic_decision_targets
    assert target.confirmed and len(queued) == 1
    assert not paths.pending_subtitle_edits(job_id).exists()
    assert any(s.text == "書き出し中に保存した字幕" for s in after.segments)
    assert any(s.text == "続けて修正した字幕" for s in after.segments)


def test_preview_enqueue_failure_does_not_unconfirm_an_edited_auto_clip(guarded_client, monkeypatch, tmp_path):  # noqa: F811
    from app.jobs.queue import get_enqueue_subtitle_review_preview
    from app.jobs.subtitle_review_preview import current_subtitle_review_preview_spec
    from app.render.render_exact_review_preview import build_live_subtitle_review_preview_spec, live_subtitle_review_preview_paths
    from app.render.render_exact_review_preview import subtitle_review_preview_spec_hash
    from app.models import Video
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    before = load_subtitle_review(data.review_path)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        spec, _, _ = current_subtitle_review_preview_spec(job=job, video=db.get(Video, job.video_id),
            document=before, paths=data.storage, clip_id=clip.id)
    live = build_live_subtitle_review_preview_spec(spec)
    paths = live_subtitle_review_preview_paths(data.review_path.parent, clip.id, subtitle_review_preview_spec_hash(live))
    paths.video_path.unlink(missing_ok=True)
    def unavailable(*args):
        raise ConnectionError("test queue unavailable")
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: unavailable
    segment = before.segments[0]
    response = data.client.patch(f"/api/jobs/{data.job_id}/subtitle-review/segments", json={"clipId": clip.id, "segments": [
        {"segmentId": segment.id, "before": segment.text, "text": "プレビューの登録失敗でも確定を保つ"}]})
    assert response.status_code == 200, response.text
    after = load_subtitle_review(data.review_path)
    assert after.clips[0].confirmed and after.clips[0].preview_state == "failed"
    assert after.clips[0].automatic_decision_state == "queued"
    assert after.segments[0].text == "プレビューの登録失敗でも確定を保つ"
