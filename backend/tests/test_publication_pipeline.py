import pytest
from sqlalchemy import select
import app.jobs.runner as runner
from app.candidates.select_candidates import CandidateSelection
from app.jobs.clip_plan import load_clip_plan, clip_plan_output_path
from app.jobs.clip_plan_runner import run_clip_plan_boundary_update
from app.jobs.queue import get_enqueue_clip_plan_boundary_update
from app.jobs.subtitle_review import load_subtitle_review, subtitle_review_output_path
from app.models import ExportItem, Job
from app.publication.models import POLICY_SETTING, PublicationPolicy
from app.publication.storage import read_report
from test_publication_decisions import candidate
from test_guarded_quality_gate_integration import (
    guarded_client as guarded_client,
    _create_review_job,
    _dependencies,
    _patch_auto_gate_outcomes,
)


@pytest.fixture
def context(guarded_client, monkeypatch, tmp_path):
    client, paths, factory = guarded_client
    job_id = _create_review_job(client, automation_mode="auto", legacy_auto=False)
    _patch_auto_gate_outcomes(monkeypatch)
    with factory() as db:
        job = db.get(Job, job_id)
        job.settings_json = {
            **job.settings_json,
            "clipAllocationMode": "ai",
            "totalClipCount": 2,
            "minNormalClipCount": 2,
            "normalClipCount": 2,
            POLICY_SETTING: PublicationPolicy().model_dump(by_alias=True),
        }
        db.commit()
    deps = _dependencies(tmp_path)

    def run(items):
        selection = CandidateSelection(
            normalClips=items, requestedTotal=2, selectedTotal=len(items), selectedByType={"normal": len(items), "short": 0}
        )
        monkeypatch.setattr(runner, "_selection_with_fallback_titles", lambda *_: (selection, items))
        return runner.run_autoclipper_job(job_id, session_factory=factory, paths=paths, dependencies=deps)

    return client, paths, factory, job_id, deps, run


@pytest.mark.parametrize(
    "scores,expected_count,status",
    [
        ([80, 85], 2, "awaiting_subtitle_review"),
        ([62, 85], 1, "awaiting_subtitle_review"),
        ([62, 63], 0, "completed"),
        ([None, 85], 1, "awaiting_clip_review"),
    ],
)
def test_new_jobs_make_only_publishable_outputs_and_distinguish_no_publication(context, scores, expected_count, status):
    client, paths, factory, id, deps, run = context
    items = [candidate("first", score=scores[0]), candidate("second", score=scores[1], start=20, end=110)]
    visited = run(items)
    assert visited[-1] == status
    report = read_report(paths, id)
    assert report.selected_count == expected_count
    with factory() as db:
        job = db.get(Job, id)
        assert job.status == status and job.error_code is None
        assert not list(db.scalars(select(ExportItem).where(ExportItem.job_id == id)))
    data = client.get(f"/api/jobs/{id}").json()
    assert data["details"]["publication"]["selectedCount"] == expected_count
    if status == "completed":
        assert report.outcome == "no_publication"
        assert "投稿なし" in data["currentStep"]
        assert client.get(f"/api/jobs/{id}/results").status_code == 200
        assert not (paths.job_outputs(id) / "subtitle_review.json").exists()
        assert not list(paths.job_outputs(id).rglob("normal_*.mp4"))
    elif status == "awaiting_subtitle_review":
        document = load_subtitle_review(subtitle_review_output_path(paths.job_outputs(id)))
        assert len(document.clips) == expected_count
        assert all(c.id != "first" for c in document.clips) if scores[0] == 62 else True
    else:
        assert report.outcome == "needs_review" and report.decisions[0].decision == "unknown"
    plan = load_clip_plan(clip_plan_output_path(paths.job_outputs(id)))
    assert plan.selected_total == expected_count
    assert len(plan.clips) == 2  # Deferred candidates remain visible/editable, without being rendered.


def test_human_keep_reuses_boundary_queue_and_records_manual_override(context, monkeypatch):
    client, paths, factory, id, deps, run = context
    assert run([candidate("first", score=62), candidate("second", score=63, start=20, end=110)])[-1] == "completed"
    requests = []
    monkeypatch.setitem(
        __import__("app.main", fromlist=["app"]).app.dependency_overrides,
        get_enqueue_clip_plan_boundary_update,
        lambda: lambda *args, **kw: requests.append((args, kw)),
    )
    response = client.patch(f"/api/jobs/{id}/clip-plan/clips/first/boundary", json={"start": 0, "end": 90})
    assert response.status_code == 202, response.text
    assert len(requests) == 1
    args, kwargs = requests[0]
    statuses = run_clip_plan_boundary_update(*args, **kwargs, session_factory=factory, paths=paths, dependencies=deps)
    assert statuses[-1] == "awaiting_clip_review"
    selected = CandidateSelection.model_validate_json((paths.job_outputs(id) / "selected_clips.json").read_text(encoding="utf-8"))
    assert [c.id for c in selected.normal_clips] == ["first"]
    decision = read_report(paths, id).decisions[0]
    assert decision.decision == "publish" and decision.source == "manual" and decision.original_decision == "skip"
    assert any(c.kind == "publication_decision" and c.source == "manual" for c in selected.choice_history)
    assert client.post(f"/api/jobs/{id}/clip-plan/approve", json={"keptClipIds": ["first"]}).status_code == 200
    document = load_subtitle_review(subtitle_review_output_path(paths.job_outputs(id)))
    assert [c.id for c in document.clips] == ["first"]


def test_invalid_manual_restore_does_not_override_existing_hard_conditions(context):
    client, paths, factory, id, deps, run = context
    run([candidate("first", score=62)])
    before = paths.publication_decisions(id).read_bytes()
    response = client.patch(f"/api/jobs/{id}/clip-plan/clips/first/boundary", json={"start": 0, "end": 89})
    assert response.status_code == 422
    assert paths.publication_decisions(id).read_bytes() == before


def test_undo_enqueue_failure_keeps_zero_output_completion_and_record(context, monkeypatch):
    from app.main import app

    client, paths, factory, id, deps, run = context
    run([candidate("first", score=62)])
    before = paths.publication_decisions(id).read_bytes()

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic queue unavailable")

    monkeypatch.setitem(app.dependency_overrides, get_enqueue_clip_plan_boundary_update, lambda: fail)
    response = client.patch(f"/api/jobs/{id}/clip-plan/clips/first/boundary", json={"start": 0, "end": 90})
    assert response.status_code == 503
    with factory() as db:
        assert db.get(Job, id).status == "completed"
    assert paths.publication_decisions(id).read_bytes() == before


def test_no_automatic_application_to_persisted_jobs_without_policy(context):
    client, paths, factory, id, deps, run = context
    with factory() as db:
        job = db.get(Job, id)
        job.settings_json = {k: v for k, v in job.settings_json.items() if k != POLICY_SETTING}
        db.commit()
    assert run([candidate("first", score=62)])[-1] == "awaiting_subtitle_review"
    assert not paths.publication_decisions(id).exists()


def test_codex_only_weak_material_reaches_no_publication_in_the_real_selection_path(context):
    from dataclasses import replace
    from app.candidates.codex_initial_selection import convert_codex_initial_selection_response
    from test_codex_initial_selection import _request, _response, _settings

    client, paths, factory, id, deps, _run = context
    request = _request(settings=_settings(**{POLICY_SETTING: PublicationPolicy().model_dump(by_alias=True)}))
    response = _response(request)
    response = response.model_copy(update={"selected_clips": [response.selected_clips[0].model_copy(update={"confidence": 0.59})]})
    result = convert_codex_initial_selection_response(request, response)
    assert result.candidates == [] and len(result.weak_candidates) == 1
    with factory() as db:
        job = db.get(Job, id)
        job.settings_json = {
            **job.settings_json,
            "initialSelectionProvider": "codex",
            "normalClipTimeRanges": [],
            "shortClipTimeRanges": [],
            "enableBoundaryRefinement": False,
        }
        db.commit()
    statuses = runner.run_autoclipper_job(
        id, session_factory=factory, paths=paths, dependencies=replace(deps, codex_initial_selector=lambda **kwargs: result)
    )
    assert statuses[-1] == "completed", read_report(paths, id).model_dump(by_alias=True, mode="json")
    report = read_report(paths, id)
    assert report.outcome == "no_publication" and report.decisions[0].decision == "skip"
    assert report.decisions[0].evidence.score == 59
    assert "MODEL_REJECTED" in report.decisions[0].reasons
    assert client.get(f"/api/jobs/{id}/results").json()["publication"]["selectedCount"] == 0


def test_unknown_only_does_not_claim_no_publication(context):
    client, paths, factory, id, deps, run = context
    assert run([candidate("unknown", score=None)])[-1] == "awaiting_clip_review"
    assert read_report(paths, id).outcome == "needs_review"
    with factory() as db:
        assert db.get(Job, id).status != "completed"


def test_manual_workflow_does_not_receive_a_publication_policy(context):
    client, paths, factory, id, deps, run = context
    with factory() as db:
        old = db.get(Job, id)
        video_id = old.video_id
    response = client.post(
        "/api/jobs",
        json={
            "videoId": video_id,
            "settings": {
                "workflowMode": "manual",
                "normalClipCount": 1,
                "shortCount": 0,
                "normalClipTimeRanges": [{"startSeconds": 0, "endSeconds": 90}],
                POLICY_SETTING: PublicationPolicy().model_dump(by_alias=True),
            },
        },
    )
    assert response.status_code == 201, response.text
    with factory() as db:
        assert POLICY_SETTING not in db.get(Job, response.json()["jobId"]).settings_json


def test_manual_override_of_model_vote_preserves_score_and_checks(context, monkeypatch):
    from app.main import app

    client, paths, factory, id, deps, run = context
    c = candidate(
        "voted-weak",
        score=59,
        should_use=False,
        hard_gate_passed=False,
        hard_gate_evidence={"passed": False, "reasons": ["model_rejected"]},
    )
    assert run([c])[-1] == "completed"
    queued = []
    monkeypatch.setitem(app.dependency_overrides, get_enqueue_clip_plan_boundary_update, lambda: lambda *a, **kw: queued.append((a, kw)))
    assert client.patch(f"/api/jobs/{id}/clip-plan/clips/{c.id}/boundary", json={"start": 0, "end": 90}).status_code == 202
    a, kw = queued[0]
    assert run_clip_plan_boundary_update(*a, **kw, session_factory=factory, paths=paths, dependencies=deps)[-1] == "awaiting_clip_review"
    selected = CandidateSelection.model_validate_json((paths.job_outputs(id) / "selected_clips.json").read_text(encoding="utf-8"))
    assert selected.normal_clips[0].final_score == 59 and selected.normal_clips[0].hard_gate_passed
    report = read_report(paths, id)
    assert report.decisions[0].source == "manual" and report.decisions[0].original_decision == "skip"
    assert report.previous_decisions[0].decisions[0].evidence.hard_gate_passed is False


def test_worker_failure_does_not_publish_deferred_candidate_or_change_report(context, monkeypatch):
    from dataclasses import replace
    from app.main import app

    client, paths, factory, id, deps, run = context
    run([candidate("weak", score=62)])
    before = paths.publication_decisions(id).read_bytes()
    queued = []
    monkeypatch.setitem(app.dependency_overrides, get_enqueue_clip_plan_boundary_update, lambda: lambda *a, **kw: queued.append((a, kw)))
    assert client.patch(f"/api/jobs/{id}/clip-plan/clips/weak/boundary", json={"start": 0, "end": 90}).status_code == 202

    def broken(*a, **kw):
        raise OSError("synthetic preview failure")

    a, kw = queued[0]
    with pytest.raises(OSError, match="synthetic preview failure"):
        run_clip_plan_boundary_update(
            *a, **kw, session_factory=factory, paths=paths, dependencies=replace(deps, subtitle_review_preview_renderer=broken)
        )
    assert paths.publication_decisions(id).read_bytes() == before
    selection = CandidateSelection.model_validate_json((paths.job_outputs(id) / "selected_clips.json").read_text(encoding="utf-8"))
    assert not selection.normal_clips and selection.deferred_candidates[0].id == "weak"
