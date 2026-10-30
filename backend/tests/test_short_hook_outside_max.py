from final_output_fixtures import passing_final_inspection

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, partition_candidates_by_duration
from app.db import get_db
from app.duration_rules import clip_body_duration, completed_clip_duration
from app.jobs.clip_plan import load_clip_plan, write_clip_plan
from app.jobs.clip_plan_runner import run_clip_plan_boundary_update, run_clip_plan_hook_scene_update
from app.jobs.pipeline_common import AutoClipperPipelineDependencies
from app.jobs.queue import (
    get_enqueue_clip_plan_boundary_update, get_enqueue_clip_plan_hook_scene_update,
    get_enqueue_subtitle_review_hook_scene_update, get_enqueue_subtitle_review_preview,
)
from app.jobs.quality_gate import evaluate_selection_quality_gate
from app.jobs.subtitle_review import load_subtitle_review, update_review_hook_scene, write_subtitle_review
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths
from app.schemas import ClipPlanHookSceneUpdateRequest, SubtitleReviewClipApplyRequest
from test_api_routes import client as client
from test_duration_rules_api import editable_plan
from test_subtitle_bulk_correction import seed_review


@pytest.mark.parametrize("duration,valid", [(72.4, True), (75, True), (75.1, False)])
def test_selection_body_cap_and_finished_duration(duration, valid):
    item = Candidate(id="short", type="short", start=0, end=duration, duration=duration,
                     transcript_text="内容のまとまった字幕", hook_scene_start=1, hook_scene_end=4)
    accepted, rejected = partition_candidates_by_duration([item], {"shortMaxDuration": 75})
    assert bool(accepted) is valid and bool(rejected) is not valid
    assert completed_clip_duration("short", 0, duration, 1, 4) == duration + 3
    assert clip_body_duration(0, duration) == duration


@pytest.mark.parametrize("duration,valid", [(.49, False), (.5, True), (3, True), (3.1, False)])
def test_hook_limit_in_candidate_and_request_models(duration, valid):
    factories = [
        lambda: Candidate(id="short", type="short", start=0, end=75, duration=75, transcript_text="字幕",
                          hook_scene_start=1, hook_scene_end=1 + duration),
        lambda: ClipPlanHookSceneUpdateRequest(start=1, end=1 + duration),
        lambda: SubtitleReviewClipApplyRequest(title="字幕", hookSceneStart=1, hookSceneEnd=1 + duration),
    ]
    for build in factories:
        if valid:
            build()
        else:
            with pytest.raises(ValidationError, match="フック映像は"):
                build()


@pytest.mark.parametrize("action", ["hook", "boundary", "manual"])
@pytest.mark.parametrize("duration,valid", [(72.4, True), (75, True), (75.1, False)])
def test_clip_plan_paths_accept_body_plus_three_second_hook(client, action, duration, valid):  # noqa: F811
    job_id, output = editable_plan(client, manual=action == "manual", clip_type="short", duration=duration)
    document = load_clip_plan(output / "clip_plan.json")
    document.clips[1].hook_scene_start, document.clips[1].hook_scene_end = 1, 4
    write_clip_plan(document, output / "clip_plan.json")
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: queued.append(args)
    app.dependency_overrides[get_enqueue_clip_plan_hook_scene_update] = lambda: lambda *args: queued.append(args)
    if action == "hook":
        response = client.patch(f"/api/jobs/{job_id}/clip-plan/clips/short0/hook-scene", json={"start": 2, "end": 5})
    elif action == "boundary":
        response = client.patch(f"/api/jobs/{job_id}/clip-plan/clips/short0/boundary", json={"start": 0, "end": duration})
    else:
        response = client.patch(f"/api/jobs/{job_id}/clip-plan/clips/short0", json={"type": "short", "start": 0, "end": duration})
    expected = (200 if action == "manual" else 202) if valid else 422
    assert response.status_code == expected, response.text
    if not valid:
        assert "ショートの本編は75秒以内" in response.json()["detail"]


def review_for_short(api, duration):
    job_id, path, document = seed_review(api)
    clip = next(clip for clip in document.clips if clip.id == "short")
    clip.start, clip.end, clip.duration = 0, duration, duration
    document.short_max_duration = 75
    write_subtitle_review(document, path)
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        job.settings_json = {**job.settings_json, "shortMaxDuration": 75}
        db.commit()
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: lambda *args: None
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: lambda *args: None
    return job_id, path, document


@pytest.mark.parametrize("action", ["apply", "hook", "document"])
@pytest.mark.parametrize("duration,valid", [(72.4, True), (75, True), (75.1, False)])
def test_subtitle_save_and_jobs_final_validation_use_body_cap(client, action, duration, valid):  # noqa: F811
    job_id, path, document = review_for_short(client, duration)
    before = path.read_bytes()
    if action == "document":
        if valid:
            update_review_hook_scene(document, "short", start=1, end=4)
        else:
            with pytest.raises(ValueError, match="ショートの本編は75秒"):
                update_review_hook_scene(document, "short", start=1, end=4)
        return
    if action == "apply":
        response = client.post(f"/api/jobs/{job_id}/subtitle-review/clips/short/apply", json={
            "title": "題材", "hookSceneStart": 1, "hookSceneEnd": 4, "segments": [],
        })
    else:
        response = client.patch(f"/api/jobs/{job_id}/subtitle-review/clips/short/hook-scene", json={"start": 1, "end": 4})
    expected = (200 if action == "apply" else 202) if valid else 422
    assert response.status_code == expected, response.text
    if not valid:
        assert "ショートの本編は75秒以内" in response.json()["detail"]
        assert path.read_bytes() == before
    elif action == "apply":
        saved = next(item for item in load_subtitle_review(path).clips if item.id == "short")
        assert saved.duration == duration and saved.confirmed


@pytest.mark.parametrize("duration", [18, 75])
def test_quality_minimum_uses_finished_duration_and_maximum_uses_body(duration):
    item = Candidate(id="short", type="short", start=0, end=duration, duration=duration, transcript_text="字幕",
                     hook_scene_start=1, hook_scene_end=4)
    decision = evaluate_selection_quality_gate(job_id="job", selection=CandidateSelection(shorts=[item]),
        transcript_segments=[TranscriptSegment(start=0, end=duration, text="字幕")], source_duration=100,
        settings={"shortMinDuration": 20, "shortMaxDuration": 75})
    assert next(check for check in decision.checks if check.code == "selection.range_duration").outcome == "pass"


@pytest.mark.parametrize("action", ["boundary", "hook"])
@pytest.mark.parametrize("duration,valid", [(72.4, True), (75, True), (75.1, False)])
def test_worker_paths_use_the_same_body_cap(client, action, duration, valid):  # noqa: F811
    job_id, output = editable_plan(client, clip_type="short", duration=duration)
    plan = load_clip_plan(output / "clip_plan.json")
    plan.clips[1].hook_scene_start, plan.clips[1].hook_scene_end = 1, 4
    write_clip_plan(plan, output / "clip_plan.json")
    selection_path = output / "selected_clips.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["shorts"][0].update(start=0, end=duration, duration=duration, hook_scene_start=1, hook_scene_end=4)
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    calls = []
    def preview(source, target, **options):
        calls.append(options)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"preview")
        return target
    options = dict(session_factory=lambda: next(app.dependency_overrides[get_db]()),
                   paths=app.dependency_overrides[get_storage_paths](),
                   dependencies=AutoClipperPipelineDependencies(final_output_inspector=passing_final_inspection,
                                                               subtitle_review_preview_renderer=preview))
    run = (lambda: run_clip_plan_boundary_update(job_id, "short0", 0, duration, **options)) if action == "boundary" else (
        lambda: run_clip_plan_hook_scene_update(job_id, "short0", 1, 4, **options))
    if valid:
        assert run()[-1] == "awaiting_clip_review"
        assert calls[0]["duration"] == duration and calls[0]["hook_duration"] == 3
    else:
        with pytest.raises(ValueError, match="ショートの本編は75秒以内"):
            run()
        assert calls == []
