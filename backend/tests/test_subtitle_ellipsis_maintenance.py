import json

import pytest
from sqlalchemy.orm import Session

from app import maintenance
from app.db import get_db
from app.jobs.subtitle_ellipsis import strip_subtitle_ellipsis
from app.jobs.subtitle_review import _refresh_counts, load_subtitle_review, write_subtitle_review
from app.jobs.quality_gate import quality_gate_decision_path
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths
from test_api_routes import client as client
from test_subtitle_bulk_correction import seed_review


def prepare(api):
    job_id, path, review = seed_review(api)
    review.segments[0].text = review.segments[0].original_text = "明．．．明治"
    review.segments[1].text = review.segments[1].original_text = "・・・"
    review.segments[2].text = "手で追加した…余韻"
    review.segments[2].edited = True
    for clip in review.clips:
        clip.live_preview_video_url = "/unchanged-live"
        clip.live_preview_spec_hash = "live-hash"
        clip.preview_video_url = "/old-exact"
        clip.preview_error = "old-error"
    _refresh_counts(review)
    write_subtitle_review(review, path)
    return job_id, path, review


def test_cli_defaults_to_dry_run_and_execute_preserves_edits_and_defers_only_affected_clips(client, monkeypatch, capsys):
    import app.jobs.queue as queue

    job_id, path, original = prepare(client)
    paths = app.dependency_overrides[get_storage_paths]()
    gates = [quality_gate_decision_path(path.parent, stage) for stage in ("selection", "content", "post_render")]
    for gate in gates:
        gate.parent.mkdir(exist_ok=True)
        gate.write_bytes(b"old decision")
    with next(app.dependency_overrides[get_db]()) as db:
        monkeypatch.setattr(maintenance, "SessionLocal", lambda: Session(db.get_bind()))
        monkeypatch.setattr(maintenance, "get_settings", lambda: type("Config", (), {"storage_root": str(paths.root)})())
        monkeypatch.setattr(queue, "enqueue_subtitle_review_preview", lambda *a: pytest.fail("must not enqueue"))
        before, stamp = path.read_bytes(), path.stat().st_mtime_ns
        job_before = db.get(Job, job_id).updated_at
        assert maintenance.main(["strip-subtitle-ellipsis", "--job", job_id]) == 0
        dry = json.loads(capsys.readouterr().out)
        assert dry["dry_run"] and dry["changed_segment_count"] == 2 and dry["skipped_edited_segment_count"] == 1
        assert dry["affected_clip_ids"] == ["normal", "short"]
        assert [(item["before"], item["after"]) for item in dry["examples"]] == [("明．．．明治", "明、明治"), ("・・・", "")]
        assert path.read_bytes() == before and path.stat().st_mtime_ns == stamp
        assert all(gate.read_bytes() == b"old decision" for gate in gates)
        assert maintenance.main(["strip-subtitle-ellipsis", "--job", job_id, "--execute"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report == {**dry, "dry_run": False}
        saved = load_subtitle_review(path)
        assert [(s.text, s.original_text, s.edited) for s in saved.segments[:2]] == [("明、明治", "明、明治", False), ("", "", False)]
        assert saved.segments[2] == original.segments[2]
        for clip in saved.clips:
            assert clip.live_preview_video_url == "/unchanged-live" and clip.live_preview_spec_hash == "live-hash"
            if clip.id in {"normal", "short"}:
                assert not clip.confirmed and clip.preview_deferred and clip.preview_state == "stale"
                assert clip.preview_video_url is None and clip.preview_error is None
            else:
                assert clip == next(item for item in original.clips if item.id == clip.id)
        assert saved.confirmed_clip_count == 1 and saved.edited_segment_count == 1 and saved.has_saved_review_changes
        assert gates[0].exists() and not any(gate.exists() for gate in gates[1:])
        summary = json.loads((path.parent / "subtitle_review_summary.json").read_text(encoding="utf-8"))
        assert summary["confirmed_clip_count"] == 1 and summary["edited_segment_count"] == 1
        assert db.get(Job, job_id, populate_existing=True).updated_at == job_before
        assert db.get(Job, job_id).status == "awaiting_subtitle_review"
        after = path.read_bytes()
        assert strip_subtitle_ellipsis(db, paths, job_id, execute=True)["changed_segment_count"] == 0
        assert path.read_bytes() == after


@pytest.mark.parametrize("state", ["completed", "rendering_normal_clips", "queued", "awaiting_clip_review"])
def test_non_review_job_is_not_changed(client, state):
    job_id, path, _ = prepare(client)
    before = path.read_bytes()
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = state
        db.commit()
        with pytest.raises(ValueError, match="字幕確認待ち"):
            strip_subtitle_ellipsis(db, app.dependency_overrides[get_storage_paths](), job_id, execute=True)
    assert path.read_bytes() == before


def test_render_queued_review_and_unsafe_identifier_are_refused(client):
    job_id, path, review = prepare(client)
    review.state = "render_queued"
    write_subtitle_review(review, path)
    before = path.read_bytes()
    with next(app.dependency_overrides[get_db]()) as db:
        paths = app.dependency_overrides[get_storage_paths]()
        with pytest.raises(ValueError, match="編集中"):
            strip_subtitle_ellipsis(db, paths, job_id, execute=True)
        with pytest.raises(ValueError, match="identifier"):
            strip_subtitle_ellipsis(db, paths, "../outside", execute=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("setting", ["transcriptNormalizePunctuation", "enableTranscriptPostProcessing"])
def test_disabled_normalization_does_not_modify_existing_review(client, setting):
    job_id, path, _ = prepare(client)
    before = path.read_bytes()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        job.settings_json = {**job.settings_json, setting: False}
        db.commit()
        report = strip_subtitle_ellipsis(db, app.dependency_overrides[get_storage_paths](), job_id, execute=True)
    assert report["skipped_reason"] == "punctuation_normalization_disabled"
    assert report["changed_segment_count"] == 0 and path.read_bytes() == before


def test_atomic_write_failure_leaves_review_and_job_unchanged(client, monkeypatch):
    import app.jobs.subtitle_ellipsis as operation

    job_id, path, _ = prepare(client)
    before = path.read_bytes()
    monkeypatch.setattr(operation, "write_subtitle_review", lambda *a: (_ for _ in ()).throw(OSError("failed")))
    with next(app.dependency_overrides[get_db]()) as db:
        with pytest.raises(OSError):
            strip_subtitle_ellipsis(db, app.dependency_overrides[get_storage_paths](), job_id, execute=True)
        assert db.get(Job, job_id).status == "awaiting_subtitle_review"
    assert path.read_bytes() == before
