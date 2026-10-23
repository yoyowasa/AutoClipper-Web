"""The new default reuses auto decisions but requires explicit human publication."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

import app.jobs.runner as runner
import app.jobs.pipeline_common as pipeline
from app.jobs.automation import (
    AUTOMATION_POLICY_SETTING, HUMAN_SUBTITLE_REVIEW_POLICY, AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING,
    build_automation_manifest, requires_human_subtitle_review,
)
from app.jobs.clip_plan import load_clip_plan, clip_plan_output_path
from app.jobs.quality_gate import evaluate_content_quality_gate, load_quality_gate_decision, quality_gate_decision_path
from app.jobs.queue import get_enqueue_job, get_enqueue_render_job, get_enqueue_retry_job, get_enqueue_subtitle_review_preview
from app.jobs.subtitle_review import load_subtitle_review, subtitle_review_output_path, write_subtitle_review
from app.jobs.title_hook_suggestions import generate_title_hook_suggestions_for_auto
from app.main import app
from app.models import Job
from app.scoring.title_hook_suggestions import TitleHookSuggestionResult
from app.candidates.codex_initial_selection import CodexInitialSelectionResult
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from test_guarded_quality_gate_integration import (
    guarded_client as guarded_client, _create_review_job, _dependencies, _decision,
)
from test_title_hook_suggestions import _suggestion_result
from app.scoring.thumbnail_copy import ThumbnailCopyResult


def prepare(guarded_client, monkeypatch, tmp_path, *, short=False, selection="pass", failure=False):
    client, storage, factory = guarded_client
    job_id = _create_review_job(client, automation_mode="auto", legacy_auto=False)
    if short:
        with factory() as db:
            job = db.get(Job, job_id)
            job.settings_json = {**job.settings_json, "normalClipCount": 0, "shortCount": 1,
                                 "normalClipTimeRanges": [], "shortClipTimeRanges": [{"startSeconds": 5, "endSeconds": 75}]}
            db.commit()
    calls = []

    def generate(**kwargs):
        calls.append(kwargs["clip_id"])
        if failure:
            raise ValueError("invalid test evidence")
        review = kwargs["document"]
        clip = next(item for item in review.clips if item.id == kwargs["clip_id"])
        result = _suggestion_result().model_dump(by_alias=True)
        for suggestion in result["suggestions"]:
            suggestion["evidenceSegmentIds"] = clip.segment_ids[:1]
            if clip.type == "normal":
                suggestion["hookSceneStart"] = suggestion["hookSceneEnd"] = None
                suggestion["hookText"] = ""
        result["descriptionEvidenceSegmentIds"] = clip.segment_ids[:1]
        return generate_title_hook_suggestions_for_auto(
            **kwargs, generator=SimpleNamespace(generate=lambda *_: TitleHookSuggestionResult.model_validate(result)),
            frame_extractor=lambda *args, **kw: [],
        )

    def thumbnail_copy(payload, images):
        segment = payload["segments"][0]
        return ThumbnailCopyResult.model_validate({"recommendedId": "copy_2", "suggestions": [
            {"id": f"copy_{i}", "heading": "", "upper": segment["text"][:40], "lower": "",
             "reason": "確定字幕から選択", "evidence": [{"segmentId": segment["segmentId"], "quote": segment["text"]}]}
            for i in range(1, 4)
        ]})
    deps = replace(_dependencies(tmp_path), auto_title_hook_generator=generate,
                   thumbnail_copy_generator=SimpleNamespace(generate=thumbnail_copy))
    monkeypatch.setattr(pipeline, "evaluate_selection_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="selection", outcome=selection, mode="auto"))
    previews, renders, resumes = [], [], []
    def enqueue_preview(*args):
        # Model the existing content-addressed RQ uniqueness, also exercised by queue tests.
        if args not in previews:
            previews.append(args)
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: enqueue_preview
    app.dependency_overrides[get_enqueue_render_job] = lambda: lambda *args: renders.append(args)
    app.dependency_overrides[get_enqueue_job] = lambda: lambda *args: resumes.append(args)
    def run():
        return runner.run_autoclipper_job(job_id, session_factory=factory, paths=storage, dependencies=deps)
    return SimpleNamespace(client=client, storage=storage, factory=factory, job_id=job_id, deps=deps,
                           calls=calls, previews=previews, renders=renders, resumes=resumes, run=run,
                           review_path=subtitle_review_output_path(storage.job_outputs(job_id)))


@pytest.mark.parametrize("short", [False, True])
def test_auto_recommendation_waits_for_human_apply_and_explicit_finalize(guarded_client, monkeypatch, tmp_path, short):
    data = prepare(guarded_client, monkeypatch, tmp_path, short=short)
    assert data.run()[-1] == "awaiting_subtitle_review"
    review = load_subtitle_review(data.review_path)
    clip = review.clips[0]
    assert not clip.confirmed
    assert clip.preview_deferred and clip.preview_state == "stale" and clip.live_preview_video_url
    assert clip.preview_video_url is None
    assert clip.selected_title_id == clip.recommended_title_id == "suggestion_1"
    assert clip.post_metadata_source == "codex" and clip.youtube_description
    assert any(choice.kind == "title_hook" and choice.source == "automatic" for choice in review.choice_history)
    assert any(choice.policyVersion == HUMAN_SUBTITLE_REVIEW_POLICY for choice in review.choice_history)
    plan = load_clip_plan(clip_plan_output_path(data.storage.job_outputs(data.job_id)))
    assert plan.state == "approved" and not plan.boundary_reedit
    assert data.client.get(f"/api/jobs/{data.job_id}").json()["details"]["humanSubtitleReviewRequired"] is True
    assert data.client.get(f"/api/jobs/{data.job_id}/subtitle-review").status_code == 200
    assert data.previews == []  # No burned preview on entry/poll.
    assert data.run() == ["awaiting_subtitle_review"]  # Redelivery cannot regenerate.
    assert len(data.calls) == 1

    # Force a pass to prove that API polling/apply and preview completion cannot auto-render.
    monkeypatch.setattr(runner, "evaluate_content_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="content", outcome="pass", mode="auto"))
    monkeypatch.setattr("app.api.jobs._evaluate_and_write_content_quality_gate", lambda **kw: _decision(
        kw["job"].id, stage="content", outcome="pass", mode="auto"))
    response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/apply", json={
        "title": "人が修正したタイトル", "hookText": "確認手順の要点" if short else "",
        "thumbnailKicker": clip.thumbnail_kicker, "thumbnailLine1": clip.thumbnail_line1, "thumbnailLine2": clip.thumbnail_line2,
        "segments": [{"segmentId": clip.segment_ids[0], "text": "人が確認して修正した字幕"}],
    })
    assert response.status_code == 200, response.text
    assert response.json()["clips"][0]["confirmed"] is True
    assert len(data.previews) == 1 and data.renders == []
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/finalize").status_code == 409
    assert len(data.previews) == 1
    assert runner.run_subtitle_review_preview(*data.previews[0], session_factory=data.factory,
                                             paths=data.storage, dependencies=data.deps) == ["ready"]
    assert data.renders == []
    assert data.client.get(f"/api/jobs/{data.job_id}/subtitle-review").status_code == 200
    assert data.renders == [] and len(data.calls) == 1
    with data.factory() as db:
        settings = db.get(Job, data.job_id).settings_json
    current = load_subtitle_review(data.review_path)
    assert evaluate_content_quality_gate(job_id=data.job_id, document=current, settings=settings, mode="auto").outcome == "pass"
    monkeypatch.setattr(runner, "evaluate_content_quality_gate", evaluate_content_quality_gate)
    response = data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/finalize")
    assert response.status_code == 202, response.text
    assert len(data.renders) == 1
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/finalize").status_code == 409
    monkeypatch.setattr(runner, "evaluate_post_render_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="post_render", outcome="pass", mode="auto"))
    statuses = runner.run_subtitle_review_render(data.job_id, render_revision=data.renders[0][1],
        session_factory=data.factory, paths=data.storage, dependencies=data.deps)
    assert statuses[-1] == "completed"
    assert len(data.calls) == 1
    if not short:
        from sqlalchemy import select
        from app.models import ExportItem
        from app.jobs.thumbnails import read_export_metadata
        with data.factory() as db:
            export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
            metadata = read_export_metadata(export)
        assert metadata["thumbnail_copy_selected_id"] == "copy_2"
        assert metadata["thumbnail_line1"] == "人が確認して修正した字幕"


def test_passed_quality_gate_still_stops_unconfirmed(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "evaluate_content_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="content", outcome="pass", mode="auto"))
    assert data.run()[-1] == "awaiting_subtitle_review"
    assert not load_subtitle_review(data.review_path).clips[0].confirmed
    assert data.renders == []


@pytest.mark.parametrize("fallback", [False, True])
def test_codex_selection_connects_to_copy_or_returns_fallback_for_review(guarded_client, monkeypatch, tmp_path, fallback):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.settings_json = {**job.settings_json, "normalClipTimeRanges": [], "initialSelectionProvider": "codex"}
        db.commit()
    selection_calls = []
    def select(**kwargs):
        selection_calls.append(kwargs)
        if fallback:
            raise ValueError("fake invalid Codex response")
        candidate = Candidate(id="codex-normal", type="normal", start=0, end=100, duration=100,
            title="確認手順", transcript_text="具体的な確認手順を説明します。", rule_score=95, final_score=95,
            should_use=True, selection_reason="codex_direct", topic_key="procedure")
        return CodexInitialSelectionResult(
            selection=CandidateSelection(normalClips=[candidate], shorts=[], requestedNormalCount=1, requestedShortCount=0),
            candidates=[candidate], summary={"provider": "codex", "status": "completed", "fallbackUsed": False,
                                            "requestedNormalCount": 1, "requestedShortCount": 0},
        )
    deps = replace(data.deps, codex_initial_selector=select)
    statuses = runner.run_autoclipper_job(data.job_id, session_factory=data.factory, paths=data.storage, dependencies=deps)
    assert len(selection_calls) == 1
    assert statuses[-1] == ("awaiting_clip_review" if fallback else "awaiting_subtitle_review")
    assert len(data.calls) == (0 if fallback else 1)
    assert data.renders == []


def test_generation_failure_is_visible_and_leaves_manual_review(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path, failure=True)
    assert data.run()[-1] == "awaiting_subtitle_review"
    document = load_subtitle_review(data.review_path)
    assert document.clips[0].selected_title_id is None
    gate = load_quality_gate_decision(quality_gate_decision_path(data.storage.job_outputs(data.job_id), "content"))
    reasons = {check.reason_code for check in gate.checks}
    assert "title_hook_evidence_unavailable_or_stale" in reasons
    assert "human_subtitle_review_required" in reasons
    assert any(choice.reason == "automatic_copy_failed:ValueError" for choice in document.choice_history)
    assert not document.clips[0].confirmed and data.renders == []


@pytest.mark.parametrize("selection", ["pass", "unknown"])
def test_selection_attention_resume_and_return_keep_existing_operations(guarded_client, monkeypatch, tmp_path, selection):
    data = prepare(guarded_client, monkeypatch, tmp_path, selection=selection)
    first = data.run()
    if selection == "unknown":
        assert first[-1] == "awaiting_clip_review"
        assert data.calls == []
        assert data.client.post(f"/api/jobs/{data.job_id}/clip-plan/approve").status_code == 200
        assert data.client.post(f"/api/jobs/{data.job_id}/clip-plan/approve").status_code == 409
        assert len(data.resumes) == 1
        assert data.run()[-1] == "awaiting_subtitle_review"
    else:
        assert first[-1] == "awaiting_subtitle_review"
    assert len(data.calls) == 1 and data.renders == []
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/return-to-clip-plan").status_code == 200
    plan = load_clip_plan(clip_plan_output_path(data.storage.job_outputs(data.job_id)))
    assert plan.state == "awaiting_review" and not plan.boundary_reedit
    assert data.client.post(f"/api/jobs/{data.job_id}/clip-plan/approve").status_code == 200
    assert data.run()[-1] == "awaiting_subtitle_review"
    assert len(data.calls) == 2  # Explicit discard of the first review permits a fresh generation.


def test_resume_preserves_applied_copy_and_manual_subtitles(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    data.run()
    review = load_subtitle_review(data.review_path)
    review.clips[0].title = "保存済みの手動タイトル"
    review.segments[0].text = "人が修正した字幕"
    review.segments[0].edited = True
    write_subtitle_review(review, data.review_path, choice_source="manual")
    assert data.client.post(f"/api/jobs/{data.job_id}/subtitle-review/reopen-clip-plan").status_code == 200
    assert data.client.post(f"/api/jobs/{data.job_id}/clip-plan/approve").status_code == 200
    assert data.run()[-1] == "awaiting_subtitle_review"
    resumed = load_subtitle_review(data.review_path)
    assert resumed.clips[0].title == "保存済みの手動タイトル"
    assert resumed.segments[0].text == "人が修正した字幕"
    assert len(data.calls) == 1


def test_resume_after_interruption_does_not_repeat_applied_recommendations(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    original = runner._render_exact_subtitle_review_preview_for_clip
    monkeypatch.setattr(runner, "_render_exact_subtitle_review_preview_for_clip",
                        lambda **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        data.run()
    with data.factory() as db:
        assert db.get(Job, data.job_id).settings_json[AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING] is True
    monkeypatch.setattr(runner, "_render_exact_subtitle_review_preview_for_clip", original)
    assert data.run()[-1] == "awaiting_subtitle_review"
    assert len(data.calls) == 1


def test_ai_shortfall_returns_to_clip_review_without_generating_copy(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.settings_json = {**job.settings_json, "clipAllocationMode": "ai", "totalClipCount": 36,
                             "minNormalClipCount": 0, "minShortCount": 0}
        db.commit()
    assert data.run()[-1] == "awaiting_clip_review"
    assert data.calls == []
    plan = load_clip_plan(clip_plan_output_path(data.storage.job_outputs(data.job_id)))
    assert plan.requested_total == 36 and 0 < plan.selected_total < 36 and plan.shortfall_reasons


def test_manual_workflow_does_not_opt_in_even_with_auto_requested(guarded_client):
    client, storage, factory = guarded_client
    job_id = _create_review_job(client)
    with factory() as db:
        video_id = db.get(Job, job_id).video_id
    response = client.post("/api/jobs", json={"videoId": video_id, "settings": {
        "workflowMode": "manual", "automationMode": "auto", "normalClipCount": 0, "shortCount": 0,
        AUTOMATION_POLICY_SETTING: HUMAN_SUBTITLE_REVIEW_POLICY,
    }})
    assert response.status_code == 201, response.text
    with factory() as db:
        settings = db.get(Job, response.json()["jobId"]).settings_json
        assert settings["automationMode"] == "manual" and AUTOMATION_POLICY_SETTING not in settings


@pytest.mark.parametrize("legacy", [False, True])
def test_retry_retains_new_or_legacy_policy_and_enqueue_is_idempotent(guarded_client, legacy):
    client, storage, factory = guarded_client
    job_id = _create_review_job(client, automation_mode="auto", legacy_auto=legacy)
    with factory() as db:
        job = db.get(Job, job_id)
        job.status = "failed"
        job.error_code = "no_usable_selection"
        db.commit()
    calls = []
    app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda *args: calls.append(args)
    response = client.post(f"/api/jobs/{job_id}/retry")
    assert response.status_code == 202, response.text
    with factory() as db:
        retry = db.get(Job, response.json()["jobId"])
        assert requires_human_subtitle_review(retry.settings_json) is not legacy
    # Existing queue's idempotent function protects repeated delivery (covered in retry API tests).
    assert len(calls) == 1


def test_new_policy_manifest_and_gate_require_human_acceptance(guarded_client, monkeypatch, tmp_path):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    data.run()
    with data.factory() as db:
        settings = db.get(Job, data.job_id).settings_json
    assert settings[AUTOMATION_POLICY_SETTING] == HUMAN_SUBTITLE_REVIEW_POLICY
    manifest = build_automation_manifest(job_id=data.job_id, video_id="vid", stored_path="source", settings=settings)
    assert manifest.roles.title_hook == "codex_auto"
    assert manifest.roles.subtitle_review == "manual"
    assert manifest.policy_version == HUMAN_SUBTITLE_REVIEW_POLICY
    document = load_subtitle_review(data.review_path)
    gate = evaluate_content_quality_gate(job_id=data.job_id, document=document, settings=settings, mode="auto")
    assert gate.route == "subtitle_review"
    assert any(c.reason_code == "human_subtitle_review_required" for c in gate.checks)
