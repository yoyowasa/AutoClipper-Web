"""Worker publication boundaries; fake encoders, real inspection controller."""

from collections import Counter
from dataclasses import replace
from functools import partial
from pathlib import Path
import hashlib
import json
import pytest
from sqlalchemy import select
import app.jobs.runner as runner
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.inspection.media import file_hash
from app.inspection.models import Check, InspectionRecord
from app.inspection.service import inspect_final_outputs
from app.jobs.automation import AUTOMATION_POLICY_SETTING, SUBTITLE_ONLY_AUTO_POLICY
from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review, subtitle_review_output_path
from app.models import ExportItem, Job
from app.storage.json_io import write_json_atomic
from test_guarded_quality_gate_integration import (
    guarded_client as guarded_client,
    _create_review_job,
    _dependencies,
    _patch_auto_gate_outcomes,
    _queue_guarded_subtitle_render,
)


@pytest.fixture
def prepared(guarded_client, tmp_path, monkeypatch):
    client, paths, factory = guarded_client
    job_id = _create_review_job(client, automation_mode="auto")
    _patch_auto_gate_outcomes(monkeypatch, content="unknown")
    initial = runner.run_autoclipper_job(job_id, session_factory=factory, paths=paths, dependencies=_dependencies(tmp_path))
    assert initial[-1] == "awaiting_subtitle_review"
    directory = paths.job_outputs(job_id)
    selection = CandidateSelection.model_validate_json((directory / "selected_clips.json").read_text(encoding="utf-8"))
    original = selection.normal_clips[0]
    other = original.model_copy(update={"id": "cand_other", "start": 15, "end": 105})
    selection.normal_clips.append(other)
    write_selected_clips(selection, directory / "selected_clips.json")
    review_path = subtitle_review_output_path(directory)
    review = load_subtitle_review(review_path)
    review.clips.append(review.clips[0].model_copy(update={"id": other.id, "start": 15, "end": 105}, deep=True))
    for clip in review.clips:
        clip.automatic_decision_state = "ready"
    for segment in review.segments:
        segment.affected_clip_ids.append(other.id)
    write_subtitle_review(review, review_path)
    _patch_auto_gate_outcomes(monkeypatch)

    def thumbnails(**kwargs):
        for export in kwargs["exports"]:
            path = Path(export.video_path).with_suffix(".jpg")
            from PIL import Image

            Image.new("RGB", (64, 36), "blue").save(path)
            meta = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
            meta.update(thumbnail_status="ready", thumbnail_path=str(path), thumbnail_subject_source="video")
            write_json_atomic(Path(export.metadata_path), meta)

    monkeypatch.setattr(runner, "generate_export_thumbnails", thumbnails)
    calls = []

    def encode(_source, target, **kwargs):
        target = Path(target)
        calls.append(target.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"{target.name} render {calls.count(target.name)}".encode())
        return target

    deps = replace(_dependencies(tmp_path), normal_renderer=encode)
    revision = _queue_guarded_subtitle_render(job_id, storage=paths, session_factory=factory)
    with factory() as db:
        job = db.get(Job, job_id)
        job.settings_json = {**job.settings_json, "normalClipCount": 2, AUTOMATION_POLICY_SETTING: SUBTITLE_ONLY_AUTO_POLICY}
        db.commit()
    review = load_subtitle_review(review_path)
    review.subtitle_only_auto = True
    write_subtitle_review(review, review_path)
    return client, paths, factory, job_id, original.id, other.id, revision, deps, calls


def execute(prepared, inspect):
    _client, paths, factory, job_id, _first, _other, revision, deps, _calls = prepared
    return runner.run_subtitle_review_render(
        job_id,
        render_revision=revision,
        paths=paths,
        session_factory=factory,
        dependencies=replace(deps, final_output_inspector=partial(inspect_final_outputs, inspector=inspect)),
    )


def test_only_defective_clip_is_rerendered_and_rechecked_before_completion(prepared):
    client, paths, factory, job_id, first, other, _revision, _deps, calls = prepared
    seen = Counter()

    def inspect(export, candidate, **kw):
        seen[candidate.id] += 1
        outcome = "fail" if candidate.id == first and seen[first] == 1 else "pass"
        return file_hash(export.video_path), [Check(code="DURATION_MISMATCH", outcome=outcome)]

    statuses = execute(prepared, inspect)
    assert statuses[-1] == "completed"
    assert seen == {first: 2, other: 1}
    assert Counter(calls) == {"normal_01.mp4": 2, "normal_02.mp4": 1}
    with factory() as db:
        assert db.get(Job, job_id).status == "completed"
        exports = list(db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)))
        assert len(exports) == 2
        for export in exports:
            record = json.loads(paths.production_record(export.id).read_text(encoding="utf-8"))
            assert record["finalInspection"]["outcome"] == "pass"
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"


def test_unrepairable_output_never_completes_and_reopens_editable_review(prepared):
    client, paths, factory, job_id, first, _other, _revision, _deps, calls = prepared
    seen = 0

    def inspect(export, candidate, **kw):
        nonlocal seen
        if candidate.id != first:
            return file_hash(export.video_path), [Check(code="DURATION_MISMATCH", outcome="pass")]
        codes = ["DURATION_MISMATCH", "SUBTITLE_OUT_OF_FRAME", "SUBTITLE_PIXELS_MISMATCH"]
        code = codes[min(seen, 2)]
        seen += 1
        return file_hash(export.video_path), [Check(code=code, outcome="fail", second=1.2)]

    statuses = execute(prepared, inspect)
    assert statuses[-1] == "awaiting_subtitle_review" and "completed" not in statuses
    assert seen == 3 and Counter(calls)["normal_01.mp4"] == 3
    data = client.get(f"/api/jobs/{job_id}").json()
    assert data["status"] == "awaiting_subtitle_review" and data["details"]["finalInspection"][0]["repairCount"] == 2
    assert "通常1" in data["details"]["finalInspection"][0]["reason"]
    review = load_subtitle_review(subtitle_review_output_path(paths.job_outputs(job_id)))
    assert review.state == "awaiting_review" and review.automatic_stop_reasons
    with factory() as db:
        assert not list(db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)))
    assert not list(paths.production_records.glob("*.json"))


def test_old_completed_outputs_are_not_reinspected_on_duplicate_delivery(prepared):
    _client, paths, factory, job_id, _first, _other, revision, deps, _calls = prepared
    assert (
        execute(
            prepared, lambda export, candidate, **kw: (file_hash(export.video_path), [Check(code="DURATION_MISMATCH", outcome="pass")])
        )[-1]
        == "completed"
    )
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.outputs.rglob("*.mp4")}

    def forbidden(**kw):
        pytest.fail("completed delivery must not inspect or demote existing outputs")

    statuses = runner.run_subtitle_review_render(
        job_id, render_revision=revision, paths=paths, session_factory=factory, dependencies=replace(deps, final_output_inspector=forbidden)
    )
    assert statuses == []
    with factory() as db:
        assert db.get(Job, job_id).status == "completed"
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.outputs.rglob("*.mp4")}


def test_failed_targeted_rerender_keeps_all_previously_published_media_and_records(prepared):
    _client, paths, factory, job_id, first, _other, _revision, deps, calls = prepared
    assert (
        execute(
            prepared, lambda export, candidate, **kw: (file_hash(export.video_path), [Check(code="DURATION_MISMATCH", outcome="pass")])
        )[-1]
        == "completed"
    )
    with factory() as db:
        old_ids = set(db.scalars(select(ExportItem.id).where(ExportItem.job_id == job_id)))
    before = {p: p.read_bytes() for p in [*paths.outputs.rglob("*.mp4"), *paths.production_records.glob("*.json")]}
    path = subtitle_review_output_path(paths.job_outputs(job_id))
    review = load_subtitle_review(path)
    review.state, review.render_revision, review.render_clip_ids = "render_queued", review.render_revision + 1, [first]
    write_subtitle_review(review, path)
    with factory() as db:
        db.get(Job, job_id).status = "rendering_normal_clips"
        db.commit()
    calls.clear()

    def inspect(export, candidate, **kw):
        return file_hash(export.video_path), [Check(code="SUBTITLE_PIXELS_MISMATCH", outcome="fail")]

    statuses = runner.run_subtitle_review_render(
        job_id,
        render_revision=review.render_revision,
        paths=paths,
        session_factory=factory,
        dependencies=replace(deps, final_output_inspector=partial(inspect_final_outputs, inspector=inspect)),
    )
    assert "completed" not in statuses
    assert set(calls) == {"normal_01.mp4"}
    with factory() as db:
        assert set(db.scalars(select(ExportItem.id).where(ExportItem.job_id == job_id))) == old_ids
    assert all(p.read_bytes() == data for p, data in before.items())
    record = InspectionRecord.model_validate_json(paths.final_output_inspection(job_id, first).read_text(encoding="utf-8"))
    assert record.outcome == "incomplete"
