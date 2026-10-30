"""Repair adapters reuse existing generators/settings; they cannot rewrite captions."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json

from test_guarded_quality_gate_integration import guarded_client as guarded_client
from test_auto_human_review import prepare
from test_manual_workflow import manual_environment as manual_environment
from app.jobs.subtitle_review import load_subtitle_review
from app.jobs.final_output_inspection import regenerate_content, refit_subtitle
from app.jobs.timeouts import final_output_inspection_timeout
from app.storage.paths import StoragePaths


def test_content_regeneration_bypasses_cache_and_preserves_manual_values(guarded_client, tmp_path, monkeypatch):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    assert data.run()[-1] == "awaiting_subtitle_review"
    document = load_subtitle_review(data.review_path)
    clip = document.clips[0]
    clip.manual_decision_fields = ["framing", "framing_offset_x", "subtitle_style"]
    clip.framing_offset_x = 23
    original = deepcopy(document.segments), clip.framing_offset_x, deepcopy(clip.subtitle_style)
    calls = []
    original_generator = data.deps.auto_title_hook_generator

    def generate(**kwargs):
        calls.append(kwargs["force_regenerate"])
        return original_generator(**kwargs)

    regenerate_content(
        document,
        clip,
        source=tmp_path / "source.mp4",
        paths=data.storage,
        settings={},
        dependencies=replace(data.deps, auto_title_hook_generator=generate),
    )
    assert calls == [True]
    assert (document.segments, clip.framing_offset_x, clip.subtitle_style) == original
    assert document.choice_history[-1].source == "fallback"
    assert document.choice_history[-1].reason == "final_output_content_mismatch"


def test_subtitle_refit_keeps_caption_text_other_roles_and_manual_emphasis(guarded_client, tmp_path, monkeypatch):
    data = prepare(guarded_client, monkeypatch, tmp_path)
    data.run()
    document = load_subtitle_review(data.review_path)
    clip = document.clips[0]
    clip.manual_decision_fields = ["title_style", "hook_style", "subtitle_styles"]
    original = deepcopy((document.segments, clip.title_style, clip.hook_style, clip.subtitle_styles))
    refit_subtitle(document, clip, settings={}, video=SimpleNamespace(width=1920, height=1080))
    assert (document.segments, clip.title_style, clip.hook_style, clip.subtitle_styles) == original
    assert clip.manual_decision_fields == ["title_style", "hook_style", "subtitle_styles"]
    assert document.choice_history[-1].kind == "text_style" and document.choice_history[-1].source == "fallback"


def test_timeout_budget_only_counts_render_targets_and_scales_to_longform(tmp_path, monkeypatch):
    from app.jobs import timeouts

    paths = StoragePaths(tmp_path)
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: paths)
    path = paths.job_outputs("job_budget") / "subtitle_review.json"
    document = {
        "renderClipIds": ["one"],
        "clips": [
            {"id": "one", "start": 0, "end": 90},
            {"id": "retained", "start": 0, "end": 1800},
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    one = final_output_inspection_timeout("job_budget")
    document["clips"][0]["end"] = 1800
    path.write_text(json.dumps(document), encoding="utf-8")
    long = final_output_inspection_timeout("job_budget")
    assert long > one + 10_000
    document["renderClipIds"] = []
    path.write_text(json.dumps(document), encoding="utf-8")
    assert final_output_inspection_timeout("job_budget") == 0


def test_failed_inspection_reopens_manual_editor_without_changing_user_ranges(manual_environment):
    from test_manual_workflow import _seed_job
    from app.candidates.merge_boundaries import Candidate
    from app.candidates.select_candidates import CandidateSelection
    from app.jobs.clip_plan import build_clip_plan, load_clip_plan, write_clip_plan
    from app.jobs.final_output_inspection import restore_manual_editor
    from app.models import Job
    from app.schemas import JobSettings

    factory, paths = manual_environment
    settings = JobSettings(workflowMode="manual", normalClipCount=0, shortCount=1).model_dump(by_alias=True, mode="json")
    settings["manualEditFinalized"] = True
    _seed_job(factory, paths, settings=settings)
    candidate = Candidate(
        id="manual_one", type="short", title="Human title", start=2, end=12, duration=10, transcript_text="", boundary_refined=False
    )
    plan = build_clip_plan("job_manual", CandidateSelection(shorts=[candidate]), settings, source_duration=30)
    plan.state = "approved"
    path = paths.job_outputs("job_manual") / "clip_plan.json"
    write_clip_plan(plan, path)
    before = deepcopy(plan.clips)
    with factory() as db:
        job = db.get(Job, "job_manual")
        restore_manual_editor(db, job, paths, "ショート1：完成検査で停止しました。")
        assert job.status == "awaiting_manual_edit" and job.error_code == "final_output_incomplete"
        assert job.settings_json["manualEditFinalized"] is False
    restored = load_clip_plan(path)
    assert restored.state == "manual_editing" and restored.settings["manualEditFinalized"] is False
    assert restored.clips == before
