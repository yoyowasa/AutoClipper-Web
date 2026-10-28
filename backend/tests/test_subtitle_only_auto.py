"""New auto policy: only subtitle confirmation is required from the operator."""
import pytest
from types import SimpleNamespace

from app.jobs.automation import AUTOMATION_POLICY_SETTING, SUBTITLE_ONLY_AUTO_POLICY
from app.jobs.confirmed_clip_decisions import run_confirmed_clip_decisions
from app.jobs.content_framing import choose_content_framing
from app.jobs.queue import get_enqueue_confirmed_clip_decisions
from app.jobs.subtitle_review import load_subtitle_review
from app.main import app
from app.models import Job
from test_auto_human_review import prepare
from test_guarded_quality_gate_integration import guarded_client as guarded_client


def setup_auto(guarded_client, monkeypatch, tmp_path, **kwargs):
    from app.scoring.short_framing import ShortFramingChoice
    def framing(document, clip, **kw):
        return ShortFramingChoice(strategy="blur_background", highlightType="screen_content", reason="全体を見せる",
                                  evidenceIds=[clip.segment_ids[0], "frame-0"]), "test-framing-input"
    monkeypatch.setattr("app.jobs.content_framing.choose_content_framing", framing)
    data = prepare(guarded_client, monkeypatch, tmp_path, **kwargs)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.settings_json = {**job.settings_json, AUTOMATION_POLICY_SETTING: SUBTITLE_ONLY_AUTO_POLICY}
        db.commit()
    data.decisions = []
    app.dependency_overrides[get_enqueue_confirmed_clip_decisions] = lambda: lambda *args: data.decisions.append(args)
    return data


@pytest.mark.parametrize("short", [True, False])
def test_confirmed_subtitles_drive_per_clip_decisions(guarded_client, monkeypatch, tmp_path, short):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=short)
    assert data.run()[-1] == "awaiting_subtitle_review"
    review = load_subtitle_review(data.review_path)
    assert review.subtitle_only_auto and not data.calls
    clip = review.clips[0]
    response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/apply", json={
        "segments": [{"segmentId": clip.segment_ids[0], "text": "人が確定した字幕から生成する"}],
    })
    assert response.status_code == 200, response.text
    assert response.json()["clips"][0]["confirmed"]
    assert not data.calls and not data.previews and len(data.decisions) == 1
    polled = data.client.get(f"/api/jobs/{data.job_id}/subtitle-review")
    assert polled.json()["clips"][0]["confirmed"]
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/finalize").status_code == 409
    result = run_confirmed_clip_decisions(*data.decisions[0], paths=data.storage, session_factory=data.factory,
                                         generator=data.deps.auto_title_hook_generator,
                                         thumbnail_generator=data.deps.thumbnail_copy_generator, candidate_extractor=lambda *a, **kw: [],
                                         enqueue_preview=lambda *args: data.previews.append(args))
    updated = load_subtitle_review(data.review_path)
    assert result == "ready", updated.clips[0].automatic_decision_error
    assert updated.clips[0].automatic_decision_state == "ready"
    assert updated.clips[0].confirmed and updated.clips[0].post_metadata_source == "codex"
    assert len(data.previews) == 1
    import app.jobs.queue as queue
    from app.jobs.runner import run_subtitle_review_preview
    monkeypatch.setattr(queue, "enqueue_subtitle_review_render", lambda *args: data.renders.append(args))
    run_subtitle_review_preview(*data.previews[0], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    from app.jobs.quality_gate import load_quality_gate_decision, quality_gate_decision_path
    gate = load_quality_gate_decision(quality_gate_decision_path(data.storage.job_outputs(data.job_id), "content"))
    assert len(data.renders) == 1, [c.model_dump() for c in gate.checks if c.outcome != "pass"]
    if not short:
        import json
        import app.jobs.runner as runner
        from sqlalchemy import select
        from app.models import ExportItem
        from test_guarded_quality_gate_integration import _decision
        # The media renderer is fake; post-render media/visual validation is tested separately.
        monkeypatch.setattr(runner, "evaluate_post_render_quality_gate", lambda **kw: _decision(
            kw["job_id"], stage="post_render", outcome="pass", mode="auto"))
        statuses = runner.run_subtitle_review_render(data.job_id, render_revision=data.renders[0][1],
            session_factory=data.factory, paths=data.storage, dependencies=data.deps)
        assert statuses[-1] == "completed" and len(data.calls) == 1
        with data.factory() as db:
            export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
            metadata = json.loads(data.storage.resolve_stored_file(export.metadata_path).read_text(encoding="utf-8"))
            record = json.loads(data.storage.production_record(export.id).read_text(encoding="utf-8"))
        assert metadata["thumbnail_copy_selected_id"] == "copy_2"
        assert metadata["thumbnail_line1"] == "人が確定した字幕から生成する"
        assert record["recordId"] == export.id


def test_empty_subtitle_rejected_before_any_save(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    before = data.review_path.read_bytes()
    response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/apply", json={
        "segments": [{"segmentId": clip.segment_ids[0], "text": "  "}],
    })
    assert response.status_code == 422
    assert "字幕が空" in response.json()["detail"] and clip.id in response.json()["detail"]
    assert data.review_path.read_bytes() == before and not data.decisions


def confirm(data, clip, **payload):
    response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/apply", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def decide(data, **kwargs):
    return run_confirmed_clip_decisions(*data.decisions[-1], paths=data.storage, session_factory=data.factory,
                                       generator=kwargs.pop("generator", data.deps.auto_title_hook_generator),
                                       thumbnail_generator=data.deps.thumbnail_copy_generator,
                                       candidate_extractor=lambda *a, **kw: [],
                                       enqueue_preview=lambda *args: data.previews.append(args), **kwargs)


def test_pause_after_selection_is_optional(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.settings_json = {**job.settings_json, "pauseAfterSelection": True}
        db.commit()
    assert data.run()[-1] == "awaiting_clip_review"
    assert data.calls == []
    assert data.client.post(f"/api/jobs/{data.job_id}/clip-plan/approve").status_code == 200
    assert data.run()[-1] == "awaiting_subtitle_review"
    assert data.calls == []


def test_manual_framing_does_not_request_a_content_override(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip, framing={"framingOffsetX": 10, "framingOffsetY": 0, "framingZoom": 1})
    monkeypatch.setattr("app.jobs.content_framing.choose_content_framing", lambda *a, **kw: pytest.fail("manual framing"))
    assert decide(data) == "ready"
    assert load_subtitle_review(data.review_path).clips[0].framing_offset_x == 10


@pytest.mark.parametrize("failure,reason", [
    ("timeout", "時間切れ"),
    ("host_timeout", "時間切れ"),
    ("bridge_error", "Codex中継のエラー"),
    ("wrapped_schema", "検証失敗"),
    ("schema", "検証失敗"),
    ("evidence", "検証失敗"),
    ("timeout_builtin", "時間切れ"),
    ("io_error", "読み書きエラー"),
    ("unexpected", "内容判断の処理エラー"),
])
def test_content_framing_failure_continues_with_visual_selection(guarded_client, monkeypatch, tmp_path, failure, reason):
    from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionError
    from app.scoring.short_framing import ShortFramingChoice
    from test_automatic_visual_decisions import resolver

    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    private = "untrusted model body must not appear"
    calls = []
    def generate(payload, images):
        calls.append(payload)
        if failure in {"timeout", "host_timeout", "bridge_error", "wrapped_schema"}:
            code = {"timeout": "timeout", "host_timeout": "codex_timeout", "bridge_error": "codex_failed",
                    "wrapped_schema": "output_invalid"}[failure]
            raise CodexTitleHookSuggestionError(f"codex_title_hook_{code}", private)
        if failure == "timeout_builtin":
            raise TimeoutError(private)
        if failure == "io_error":
            raise OSError(private)
        if failure == "unexpected":
            raise RuntimeError(private)
        return ShortFramingChoice(strategy=private if failure == "schema" else "face_tracking_crop",
            highlightType="expression_reaction", reason=private, evidenceIds=["unknown", "frame-0"])
    def extract(source, path, second):
        path.write_bytes(b"frame")
        return path
    monkeypatch.setattr("app.jobs.content_framing.choose_content_framing",
        lambda *args, **kwargs: choose_content_framing(*args, **kwargs, extractor=extract))
    resolved = []
    def visual(*args, **kwargs):
        assert kwargs["layout"] == "auto" and "preferred_strategy" not in kwargs
        result = resolver(*args, **kwargs)
        resolved.append(result)
        return result
    assert decide(data, framing_selector=SimpleNamespace(generate=generate), crop_resolver=visual) == "ready"
    updated = load_subtitle_review(data.review_path)
    current = updated.clips[0]
    assert current.confirmed and current.automatic_decision_state == "ready" and current.automatic_decision_error is None
    assert len(calls) == len(resolved) == len(data.previews) == 1
    assert current.automatic_crop.plan == resolved[0][0]  # use the legacy resolver's choice, not forced blur
    # Saving also appends observed snapshots; inspect the applied framing decision.
    framing = [c for c in updated.choice_history if c.kind == "framing" and c.clipId == clip.id and c.stage == "applied"][-1]
    assert framing.source == "fallback" and framing.values["resolvedLayout"] == "face_tracking_crop"
    assert "内容による画角判断ができなかった" in framing.reason and reason in framing.reason
    assert "contentPreferredLayout" not in framing.values and "framingEvidenceIds" not in framing.values
    assert private not in data.review_path.read_text(encoding="utf-8")
    # The regular preview/quality gate path still queues final rendering.
    import app.jobs.queue as queue
    from app.jobs.runner import run_subtitle_review_preview
    monkeypatch.setattr(queue, "enqueue_subtitle_review_render", lambda *args: data.renders.append(args))
    run_subtitle_review_preview(*data.previews[0], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    assert len(data.renders) == 1


def test_visual_selection_error_is_not_hidden_by_content_fallback(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    def unavailable(*args, **kwargs):
        raise TimeoutError("private details")
    monkeypatch.setattr("app.jobs.content_framing.choose_content_framing", unavailable)
    assert decide(data, crop_resolver=unavailable) == "failed"
    current = load_subtitle_review(data.review_path).clips[0]
    assert current.automatic_decision_state == "failed" and "画角" in current.automatic_decision_error
    assert not data.previews


def test_failure_is_visible_and_retry_does_not_need_title_input(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    confirm(data, clip, segments=[])
    assert len(data.decisions) == 1

    def fail(**kwargs):
        raise ValueError("must not expose Codex output")

    assert decide(data, generator=fail) == "failed"
    current = data.client.get(f"/api/jobs/{data.job_id}/subtitle-review").json()["clips"][0]
    assert current["automaticDecisionState"] == "failed"
    assert "タイトル・フック" in current["automaticDecisionError"]
    assert clip.id in current["automaticDecisionError"] and "秒" in current["automaticDecisionError"]
    assert "must not expose" not in current["automaticDecisionError"]
    confirm(data, clip)
    assert len(data.decisions) == 2
    assert decide(data) == "ready"


def test_changed_subtitles_supersede_inflight_decision(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)

    def generate(**kwargs):
        artifact = data.deps.auto_title_hook_generator(**kwargs)
        # This request must finish while Codex is running: no document lock is held.
        confirm(data, clip, segments=[{"segmentId": clip.segment_ids[0], "text": "さらに修正した字幕"}])
        return artifact

    assert decide(data, generator=generate) == "superseded"
    current = load_subtitle_review(data.review_path)
    assert current.clips[0].automatic_decision_state == "queued"
    assert current.segments[0].text == "さらに修正した字幕"
    assert not data.previews
    assert decide(data) == "ready"


def test_manual_thumbnail_override_survives_automatic_title_selection(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip, thumbnailKicker="指定", thumbnailLine1="手動の文言", thumbnailLine2="残す")
    assert decide(data) == "ready"
    current = load_subtitle_review(data.review_path).clips[0]
    assert current.thumbnail_line1 == "手動の文言"
    assert current.post_metadata_source == "codex"


def test_quality_stop_identifies_clip_time_and_reason(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip, subtitleStyle={"fontSize": 200, "yPercent": 95, "positionMode": "explicit"})
    assert decide(data) == "ready"
    from app.jobs.runner import run_subtitle_review_preview
    run_subtitle_review_preview(*data.previews[0], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    response = data.client.get(f"/api/jobs/{data.job_id}/subtitle-review")
    reasons = response.json()["automaticStopReasons"]
    assert any("ショート1" in reason and "秒" in reason and "安全な表示範囲" in reason for reason in reasons)
    assert all(clip.id not in reason for reason in reasons)
    assert not data.renders


def test_unconfirm_revokes_worker_and_blocks_finalization(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)

    def generate(**kwargs):
        artifact = data.deps.auto_title_hook_generator(**kwargs)
        response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/unconfirm")
        assert response.status_code == 200
        assert not response.json()["clips"][0]["confirmed"]
        return artifact

    assert decide(data, generator=generate) == "superseded"
    current = load_subtitle_review(data.review_path)
    assert not current.clips[0].confirmed and current.confirmed_clip_count == 0
    assert current.clips[0].automatic_decision_state == "idle"
    assert not data.previews
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/finalize").status_code == 409


def test_second_unconfirmed_clip_prevents_automatic_render(guarded_client, monkeypatch, tmp_path):
    from app.jobs.runner import _prepare_auto_render_after_preview
    from app.jobs.subtitle_review import write_subtitle_review
    from app.models import Video

    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    document = load_subtitle_review(data.review_path)
    document.clips[0].confirmed = True
    document.clips[0].automatic_decision_state = "ready"
    second = document.clips[0].model_copy(update={"id": "other", "confirmed": False, "automatic_decision_state": "idle"})
    document.clips.append(second)
    write_subtitle_review(document, data.review_path)
    monkeypatch.setattr("app.jobs.runner.refresh_subtitle_review_preview_states", lambda **kw: (kw["document"], [], False))
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        assert _prepare_auto_render_after_preview(db=db, job=job, video=db.get(Video, job.video_id), storage_paths=data.storage) is None
        assert job.status == "awaiting_subtitle_review"


def test_thumbnail_copy_and_frame_decisions_reused_at_publication(guarded_client, monkeypatch, tmp_path):
    from app.jobs.confirmed_thumbnail import prepare_confirmed_thumbnail, reuse_confirmed_thumbnail
    from app.jobs.automatic_thumbnail_copy import decide_thumbnail_copy
    from app.models import ExportItem, Video

    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    review = load_subtitle_review(data.review_path)
    clip = review.clips[0]
    video_path = data.storage.job_outputs(data.job_id) / "normal.mp4"
    video_path.write_bytes(b"test rendered file")
    export = ExportItem(id="test-export", job_id=data.job_id, candidate_id=clip.id, title=clip.publication_title,
                        video_path=str(video_path), type="normal", duration=clip.duration)
    review.state = "render_queued"
    def must_not_generate(*args, **kwargs):
        raise AssertionError("the confirmed input must be reused")
    from types import SimpleNamespace
    metadata = decide_thumbnail_copy(review=review, export=export, paths=data.storage, metadata={},
                                     generator=SimpleNamespace(generate=must_not_generate))
    assert metadata["thumbnail_line1"] == clip.thumbnail_line1
    assert metadata["thumbnail_copy_source"] == "automatic"

    directory = data.storage.confirmed_thumbnail_frames(data.job_id, clip.id, clip.start, clip.end)
    (directory / "c.json").unlink()
    def extract(source, *, directory, **kwargs):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "frame_00.jpg").write_bytes(b"full frame")
        (directory / "frame_00.small.jpg").write_bytes(b"small frame")
        return [{"id": "frame_00", "second": 2, "score": 1, "face": [.2, .2, .2, .2], "close_available": True}]
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        video = db.get(Video, job.video_id)
        prepare_confirmed_thumbnail(db, data.storage, job, video, review, clip, extractor=extract)
        prepare_confirmed_thumbnail(db, data.storage, job, video, review, clip, extractor=must_not_generate)
        output = data.storage.job_outputs(data.job_id)
        metadata, frames, asset = reuse_confirmed_thumbnail(db, data.storage, data.job_id, clip, export, output)
        from app.jobs.thumbnail_candidates import candidate_directory
        assert (candidate_directory(output, export.id) / "frame_00.jpg").read_bytes() == b"full frame"
        assert frames[0]["id"] == "frame_00" and asset is None
        assert metadata["thumbnail_candidates_version"] == 1


def test_manual_posting_override_uses_current_subtitle_revision(guarded_client, monkeypatch, tmp_path):
    from app.jobs.runner import run_subtitle_review_preview
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip, publicationTitle="手で指定した公開タイトル", postMetadataSource="manual",
            postMetadataRevisionHash=None, selectedTitleId=None, recommendedTitleId=None)
    assert decide(data) == "ready"
    monkeypatch.setattr("app.jobs.queue.enqueue_subtitle_review_render", lambda *args: data.renders.append(args))
    run_subtitle_review_preview(*data.previews[0], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    updated = load_subtitle_review(data.review_path)
    assert updated.clips[0].publication_title == "手で指定した公開タイトル" + updated.clips[0].normal_title_suffix
    assert any(c.source == "manual" and c.reason == "explicit_manual_override_preserved" for c in updated.choice_history)
    assert len(data.renders) == 1


def test_preview_retry_preserves_confirmed_subtitles(guarded_client, monkeypatch, tmp_path):
    from app.jobs.subtitle_review import write_subtitle_review
    from app.jobs.runner import run_subtitle_review_preview
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    document = load_subtitle_review(data.review_path)
    document.clips[0].preview_state = "failed"
    document.clips[0].preview_error = "test preview failure"
    write_subtitle_review(document, data.review_path)
    result = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/preview/retry")
    assert result.status_code == 200, result.text
    assert result.json()["clips"][0]["confirmed"]
    monkeypatch.setattr("app.jobs.queue.enqueue_subtitle_review_render", lambda *args: data.renders.append(args))
    run_subtitle_review_preview(*data.previews[-1], paths=data.storage, session_factory=data.factory, dependencies=data.deps)
    assert len(data.renders) == 1


def test_killed_decision_task_records_failure_without_failing_job(guarded_client, monkeypatch, tmp_path):
    from unittest.mock import Mock
    from rq.job import Job as RQJob, JobStatus
    from rq import Worker
    import app.jobs.worker as worker
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    task = RQJob.create("app.jobs.confirmed_clip_decisions.run_confirmed_clip_decisions",
                        args=data.decisions[0], connection=Mock())
    task.get_status = Mock(return_value=JobStatus.FAILED)
    monkeypatch.setattr(Worker, "handle_job_failure", lambda *a: None)
    monkeypatch.setattr(worker, "SessionLocal", data.factory)
    monkeypatch.setattr(worker, "get_storage_paths", lambda: data.storage)
    instance = object.__new__(worker.CharacterAssetWorker)
    instance.log = Mock()
    instance.handle_job_failure(task, Mock(), exc_string="JobTimeoutException")
    document = load_subtitle_review(data.review_path)
    assert document.clips[0].automatic_decision_state == "failed"
    assert "時間切れ" in document.clips[0].automatic_decision_error
    with data.factory() as db:
        assert db.get(Job, data.job_id).status == "awaiting_subtitle_review"


def test_subtitle_confirmation_never_counts_as_visual_acceptance(tmp_path):
    import json
    from app.jobs.quality_gate import _post_render_visual_check
    from test_guarded_quality_gate import _ready_content_document
    document = _ready_content_document()
    clip = document.clips[0]
    clip.confirmed = True
    metadata = tmp_path / "export.json"
    metadata.write_text(json.dumps({"crop_strategy": "face_tracking_crop", "crop_confidence": 0.99,
                                    "top_banner_rendered": False, "bottom_banner_rendered": False}), encoding="utf-8")
    export = {"id": "export", "candidate_id": clip.id, "type": "short", "metadata_path": str(metadata)}
    assert _post_render_visual_check([export], document).outcome == "pass"  # Legacy confirmed visual review.
    document.subtitle_only_auto = True
    check = _post_render_visual_check([export], document)
    assert check.outcome == "unknown"
    assert check.reason_code == "post_render_visual_evidence_insufficient"
    assert not check.evidence["inspected"][0]["humanPreviewAccepted"]


def test_new_auto_creation_stamps_policy_without_changing_manual_jobs(guarded_client):
    from test_guarded_quality_gate_integration import _create_review_job
    client, _storage, factory = guarded_client
    auto_id = _create_review_job(client, automation_mode="auto", legacy_auto=False)
    manual_id = _create_review_job(client, automation_mode="manual", legacy_auto=False)
    with factory() as db:
        assert db.get(Job, auto_id).settings_json[AUTOMATION_POLICY_SETTING] == SUBTITLE_ONLY_AUTO_POLICY
        assert AUTOMATION_POLICY_SETTING not in db.get(Job, manual_id).settings_json
