"""Only deliberate, confirmed framing overrides bypass automatic geometry checks."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.jobs.runner as runner
from app.jobs.quality_gate import _post_render_visual_check
from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review
from app.models import ExportItem, Job
from test_guarded_quality_gate_integration import guarded_client as guarded_client, _decision
from test_subtitle_only_auto import setup_auto, confirm, decide


FRAMING = {"framingOffsetX": 20, "framingOffsetY": 0, "framingZoom": 1.1}


@pytest.mark.parametrize("entry", ["framing", "apply", "framing-guide", "settings"])
def test_unconfirmed_auto_cannot_change_framing(guarded_client, monkeypatch, tmp_path, entry):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    before = data.review_path.read_bytes()
    base = f"/api/jobs/{data.job_id}/subtitle-review"
    if entry == "settings":
        response = data.client.patch(base + "/settings", json={"shortLayout": "center_crop",
                                                               "shortTopBannerEnabled": False, "shortBottomBannerEnabled": False})
    elif entry == "apply":
        response = data.client.post(base + f"/clips/{clip.id}/apply", json={"framing": FRAMING})
    elif entry == "framing-guide":
        response = data.client.post(base + f"/clips/{clip.id}/framing-guide")
    else:
        response = data.client.patch(base + f"/clips/{clip.id}/framing", json=FRAMING)
    assert response.status_code == 409, response.text
    assert "字幕" in response.json()["detail"]
    assert data.review_path.read_bytes() == before


def ready(data):
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    confirm(data, clip)
    assert decide(data) == "ready"
    return load_subtitle_review(data.review_path)


def test_identical_save_is_not_manual_and_rendering_rejects_changes(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    clip = ready(data).clips[0]
    before = data.review_path.read_bytes()
    data.previews.clear()
    url = f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/framing"
    response = data.client.patch(url, json={"framingOffsetX": clip.framing_offset_x,
                                          "framingOffsetY": clip.framing_offset_y, "framingZoom": clip.framing_zoom})
    assert response.status_code == 200, response.text
    assert data.review_path.read_bytes() == before and data.previews == []
    with data.factory() as db:
        db.get(Job, data.job_id).status = "rendering_shorts"
        db.commit()
    response = data.client.patch(url, json=FRAMING)
    assert response.status_code == 409
    assert "書き出し中" in response.json()["detail"]
    assert data.review_path.read_bytes() == before and data.previews == []


def test_saved_job_manual_overrides_are_approved_without_changing_automatic_checks(monkeypatch):
    fixture = json.loads((Path(__file__).parent / "fixtures/task233_manual_framing.json").read_text(encoding="utf-8"))
    inspected = {r["clipId"]: r for r in fixture.pop("inspected")}
    document = SimpleNamespace(**{**fixture, "clips": [SimpleNamespace(**c) for c in fixture["clips"]]})
    exports = [SimpleNamespace(candidate_id=c.id, type="short") for c in document.clips]
    calls = []

    def metadata(export):
        row = inspected[export.candidate_id]
        return {"clip_id": export.candidate_id, "crop_strategy": row["strategy"],
                "crop_confidence": row["cropConfidence"], "top_banner_rendered": row["topBannerExpected"],
                "bottom_banner_rendered": row["bottomBannerExpected"]}, None

    def geometry(value, **kwargs):
        calls.append(value["clip_id"])
        row = inspected[value["clip_id"]]
        return row["trackingContainment"], row["trackingEvidence"]

    monkeypatch.setattr("app.jobs.quality_gate._load_export_metadata", metadata)
    monkeypatch.setattr("app.jobs.quality_gate._tracking_crop_containment", geometry)
    result = _post_render_visual_check(exports, document)
    assert result.outcome == "pass"
    manual = {c.id for c in document.clips if "framing" in c.manual_decision_fields}
    assert len(manual) == 2 and not manual.intersection(calls)
    assert {r["clipId"] for r in result.evidence["inspected"] if r.get("approvalSource") == "manual_framing"} == manual
    # The actually outside crop still fails as soon as its human approval is absent.
    outside = next(c for c in document.clips if inspected[c.id]["trackingContainment"] is False)
    outside.manual_decision_fields = []
    assert _post_render_visual_check(exports, document).outcome == "fail"


def test_ready_framing_save_only_queues_target_preview_and_records_baseline(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    document = ready(data)
    clip = document.clips[0]
    other = clip.model_copy(deep=True, update={"id": "other"})
    document.clips.append(other)
    write_subtitle_review(document, data.review_path)
    before_other = other.model_dump()
    data.previews.clear()
    response = data.client.patch(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/framing", json=FRAMING)
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(data.review_path)
    assert saved.clips[0].confirmed and saved.clips[0].manual_decision_fields == ["framing"]
    assert saved.clips[1].model_dump() == before_other
    assert len(data.previews) == 1 and data.previews[0][1] == clip.id
    assert len(data.decisions) == 1, "a manual adjustment must not rerun title/content decisions"
    history = [c for c in saved.choice_history if c.clipId == clip.id and c.kind == "framing" and c.source == "manual"]
    assert len(history) == 1
    assert history[0].candidates[0].id == history[0].recommendedId
    assert history[0].candidates[0].values != history[0].values


@pytest.mark.parametrize("manual,confirmed,automatic", [(True, True, True), (False, True, True),
                                                        (True, False, True), (True, True, False)])
def test_manual_approval_is_scoped_and_does_not_disable_overlay_contract(
    guarded_client, monkeypatch, tmp_path, manual, confirmed, automatic,
):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    document = ready(data)
    clip = document.clips[0]
    document.subtitle_only_auto = automatic
    clip.manual_decision_fields = ["framing"] if manual else []
    clip.confirmed = confirmed
    clip.preview_state = "ready"
    clip.preview_spec_hash = "current"
    clip.preview_video_url = "/current.mp4"
    metadata = tmp_path / "export.json"
    metadata.write_text(json.dumps({"crop_strategy": "subject_tracking_crop", "crop_confidence": 0,
                                    "top_banner_rendered": document.short_top_banner_enabled,
                                    "bottom_banner_rendered": document.short_bottom_banner_enabled}), encoding="utf-8")
    export = SimpleNamespace(candidate_id=clip.id, type="short", metadata_path=str(metadata))
    check = _post_render_visual_check([export], document)
    if manual and confirmed and automatic:
        assert check.outcome == "pass"
        assert check.evidence["inspected"][0]["approvalSource"] == "manual_framing"
        metadata.write_text(json.dumps({"crop_strategy": "subject_tracking_crop",
                                       "top_banner_rendered": not document.short_top_banner_enabled,
                                       "bottom_banner_rendered": document.short_bottom_banner_enabled}), encoding="utf-8")
        assert _post_render_visual_check([export], document).outcome == "fail"
    elif automatic or not confirmed:
        assert check.outcome != "pass"


@pytest.mark.parametrize("target_index", [0, 1])
def test_completed_manual_framing_reuses_other_exports_and_records(guarded_client, monkeypatch, tmp_path, target_index):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    document = ready(data)
    clip = document.clips[0]
    original = document.clips[0].model_copy(deep=True, update={"id": "other"})
    document.clips.append(original)
    clip = document.clips[target_index]
    other_id = document.clips[1 - target_index].id
    selected_path = data.storage.job_outputs(data.job_id) / "selected_clips.json"
    selection = json.loads(selected_path.read_text(encoding="utf-8"))
    selection["shorts"].append({**selection["shorts"][0], "id": "other"})
    selected_path.write_text(json.dumps(selection), encoding="utf-8")
    document.state = "render_queued"
    write_subtitle_review(document, data.review_path)
    monkeypatch.setattr(runner, "evaluate_content_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="content", outcome="pass", mode="auto"))
    monkeypatch.setattr(runner, "evaluate_post_render_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="post_render", outcome="pass", mode="auto"))
    monkeypatch.setattr(runner, "generate_export_thumbnails", lambda **kw: None)
    assert runner.run_subtitle_review_render(data.job_id, render_revision=document.render_revision,
        session_factory=data.factory, paths=data.storage, dependencies=data.deps)[-1] == "completed"
    with data.factory() as db:
        exports = list(db.scalars(select(ExportItem).where(ExportItem.job_id == data.job_id)))
    other_export = next(e for e in exports if e.candidate_id == other_id)
    protected = [data.storage.resolve_stored_file(p) for p in
                 (other_export.video_path, other_export.subtitle_path, other_export.metadata_path) if p]
    protected.append(data.storage.production_record(other_export.id))
    before = {p: p.read_bytes() for p in protected}
    data.previews.clear()
    response = data.client.patch(f"/api/jobs/{data.job_id}/subtitle-review/clips/{clip.id}/framing", json=FRAMING)
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(data.review_path)
    assert saved.render_clip_ids == [clip.id]
    assert saved.clips[0].confirmed and saved.clips[1].confirmed
    assert len(data.previews) == 1 and data.previews[0][1] == clip.id
    import app.jobs.queue as queue
    queued = []
    monkeypatch.setattr(queue, "enqueue_subtitle_review_render", lambda *args: queued.append(args))
    runner.run_subtitle_review_preview(*data.previews[-1], paths=data.storage,
                                      session_factory=data.factory, dependencies=data.deps)
    assert len(queued) == 1
    saved = load_subtitle_review(data.review_path)
    rendered = []
    renderer = data.deps.short_renderer
    def track(source, target, **kwargs):
        rendered.append(target.name)
        return renderer(source, target, **kwargs)
    statuses = runner.run_subtitle_review_render(data.job_id, render_revision=saved.render_revision,
        session_factory=data.factory, paths=data.storage, dependencies=replace(data.deps, short_renderer=track))
    assert statuses[-1] == "completed"
    assert rendered == [f"short_{target_index + 1:02d}.mp4"]
    assert all(p.read_bytes() == content for p, content in before.items())
    with data.factory() as db:
        assert db.get(ExportItem, other_export.id) is not None
        assert db.get(Job, data.job_id).status == "completed"
