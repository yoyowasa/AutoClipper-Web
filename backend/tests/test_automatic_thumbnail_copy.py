import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_api_routes import client as client
from test_thumbnail_copy import seed
from test_thumbnail_text_styles import real_test_renderer
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.automation import AUTOMATION_POLICY_SETTING, HUMAN_SUBTITLE_REVIEW_POLICY
from app.jobs.subtitle_review import write_subtitle_review
from app.jobs.thumbnail_copy import build_copy_input, copy_state_path, read_copy_state, queue_copy_generation
from app.jobs.thumbnails import generate_export_thumbnails, read_export_metadata
from app.models import ExportItem, Job
from app.production_records import record_completed_productions
from app.scoring.thumbnail_copy import ThumbnailCopyResult


def result_for(payload, *, invalid=False):
    segment = payload["segments"][0]
    return ThumbnailCopyResult.model_validate({"subjectName": "イヴ・クライン", "recommendedId": "copy_2", "suggestions": [
        {"id": f"copy_{i}", "heading": "人物紹介", "upper": "青い作品" if invalid else "イヴ・クライン",
         "lower": "青い作品", "reason": "確定字幕の中心人物", "evidence": [{"segmentId": segment["segmentId"], "quote": segment["text"]}]}
        for i in range(1, 4)
    ]})


def prepare(client, monkeypatch):  # noqa: F811
    case = seed(client)
    case.review.state = "rendering"
    case.review.clips[0].confirmed = True
    case.review.clips[0].thumbnail_line1 = "初期の文言"
    case.review.segments[0].text = "イヴ・クラインの青い作品について紹介します。"
    write_subtitle_review(case.review, case.review_path, choice_source="automatic")
    with case.factory() as db:
        job = db.get(Job, case.review.job_id)
        job.status = "rendering_normal"
        job.settings_json = {**(job.settings_json or {}), "automationMode": "auto",
                             AUTOMATION_POLICY_SETTING: HUMAN_SUBTITLE_REVIEW_POLICY}
        db.commit()
    monkeypatch.setattr("app.jobs.thumbnails.ensure_thumbnail_candidates", lambda *args: [])
    monkeypatch.setattr("app.jobs.thumbnail_regeneration.ensure_thumbnail_candidates", lambda *args: [])
    return case


def render(case, generator, *, renderer=real_test_renderer):
    clip = case.review.clips[0]
    candidate = Candidate(id=clip.id, type="normal", start=clip.start, end=clip.end, duration=clip.duration,
                          title=clip.title, transcript_text="", thumbnail_kicker=clip.thumbnail_kicker,
                          thumbnail_line1=clip.thumbnail_line1, thumbnail_line2=clip.thumbnail_line2)
    with case.factory() as db:
        export = db.get(ExportItem, "exp_thumbnail_style")
        batch = generate_export_thumbnails(exports=[export], selection=CandidateSelection(normalClips=[candidate]),
            input_path=case.video, job_output_dir=case.storage.job_outputs(export.job_id), normal_renderer=renderer,
            character_style=(db.get(Job, export.job_id).settings_json or {}).get("normalThumbnailStyle"),
            db=db, job=db.get(Job, export.job_id), paths=case.storage, review_document=case.review, copy_generator=generator)
        return batch, read_export_metadata(export)


def test_confirmed_copy_published_once_and_reused_by_completed_editor(client, monkeypatch):  # noqa: F811
    case = prepare(client, monkeypatch)
    calls = []
    def generate(payload, images):
        calls.append(payload)
        assert images == []
        assert payload["segments"][0]["text"] == case.review.segments[0].text
        return result_for(payload)
    generator = SimpleNamespace(generate=generate)
    batch, metadata = render(case, generator)
    assert batch.failures == []
    assert metadata["thumbnail_line1"] == "イヴ・クライン"
    assert metadata["thumbnail_copy_selected_id"] == metadata["thumbnail_copy_recommended_id"] == "copy_2"
    assert metadata["thumbnail_subject_source"] == "legacy"
    assert len(calls) == 1
    assert render(case, generator)[0].failures == []
    assert len(calls) == 1
    case.review.state = "completed"
    write_subtitle_review(case.review, case.review_path)
    with case.factory() as db:
        job = db.get(Job, case.review.job_id)
        job.status = "completed"
        db.commit()
        export = db.get(ExportItem, "exp_thumbnail_style")
        state = read_copy_state(copy_state_path(case.storage, export))
        assert state["inputHash"] == build_copy_input(db, case.storage, export)["inputHash"]
        queued = []
        assert queue_copy_generation(db, case.storage, export, lambda *args: queued.append(args), force=False).state == "ready"
        assert not queued
        record_completed_productions(db, job, case.storage)
    record = json.loads(case.storage.production_record("exp_thumbnail_style").read_text(encoding="utf-8"))
    assert record["thumbnailLine1"] == metadata["thumbnail_line1"]
    applied = [c for c in record["choiceHistory"] if c["kind"] == "thumbnail" and c["stage"] == "applied"]
    assert applied[-1]["selectedIds"] == ["copy_2"]
    assert applied[-1]["recommendedId"] == "copy_2"


@pytest.mark.parametrize("correct_retry", [True, False])
def test_subject_retry_failure_visible_and_not_retried_on_same_input(client, monkeypatch, correct_retry):  # noqa: F811
    case = prepare(client, monkeypatch)
    calls = []
    def generate(payload, images):
        calls.append(payload)
        return result_for(payload, invalid=len(calls) == 1 or not correct_retry)
    generator = SimpleNamespace(generate=generate)
    batch, metadata = render(case, generator)
    assert batch.failures == []
    assert len(calls) == 2 and "correction" in calls[1]
    assert metadata["thumbnail_copy_source"] == ("automatic" if correct_retry else "fallback")
    if not correct_retry:
        assert metadata["thumbnail_copy_selected_id"] is None
        assert metadata["thumbnail_line1"] == "初期の文言"
        assert "1回作り直し" in metadata["thumbnail_copy_error"]
        assert any("初期文言" in w for w in metadata["thumbnail_warnings"])
        response = client.get(f"/api/jobs/{case.review.job_id}/results")
        assert response.status_code == 200
        assert response.json()["normalClips"][0]["thumbnailWarnings"] == metadata["thumbnail_warnings"]
    render(case, generator)
    assert len(calls) == 2


def test_manual_copy_preserved_but_subtitle_only_edit_generates(client, monkeypatch):  # noqa: F811
    case = prepare(client, monkeypatch)
    case.review.segments[0].text += "確認しました。"
    write_subtitle_review(case.review, case.review_path, choice_source="manual")
    calls = []
    generator = SimpleNamespace(generate=lambda payload, images: calls.append(payload) or result_for(payload))
    assert render(case, generator)[1]["thumbnail_copy_source"] == "automatic"
    case.review.clips[0].thumbnail_line1 = "手動で選んだ見出し"
    write_subtitle_review(case.review, case.review_path, choice_source="manual")
    batch, metadata = render(case, generator)
    assert batch.failures == [] and len(calls) == 1
    assert metadata["thumbnail_line1"] == "手動で選んだ見出し"
    assert metadata["thumbnail_copy_source"] == "manual"


def test_changed_confirmed_input_generates_again_legacy_does_not(client, monkeypatch):  # noqa: F811
    case = prepare(client, monkeypatch)
    calls = []
    generator = SimpleNamespace(generate=lambda payload, images: calls.append(payload) or result_for(payload))
    render(case, generator)
    previous_text = case.review.segments[0].text
    case.review.segments[0].text += "話の続き。"
    render(case, generator)
    assert len(calls) == 2
    case.review.segments[0].text = previous_text
    render(case, generator)
    assert len(calls) == 2
    with case.factory() as db:
        job = db.get(Job, case.review.job_id)
        job.settings_json = {"automationMode": "auto"}
        db.commit()
    render(case, generator)
    assert len(calls) == 2


def test_unconfirmed_input_never_sent(client, monkeypatch):  # noqa: F811
    case = prepare(client, monkeypatch)
    case.review.clips[0].confirmed = False
    calls = []
    batch, _ = render(case, SimpleNamespace(generate=lambda *args: calls.append(args)))
    assert len(batch.failures) == 1 and not calls


@pytest.mark.parametrize("design", ["raden", "sopia"])
def test_asset_fallback_keeps_expression_and_final_copy_matches_image(client, monkeypatch, tmp_path, design):  # noqa: F811
    from test_thumbnail_character_assets import add_asset
    case = prepare(client, monkeypatch)
    response = client.put("/api/preferences/character-presets", json={
        "presets": [{"name": "素材", "settings": {}}], "selectedName": "素材"})
    assert response.status_code == 200
    case.preset = response.json()["presets"][0]["id"]
    asset_id, asset_path = add_asset(case)
    with case.factory() as db:
        job = db.get(Job, case.review.job_id)
        job.settings_json = {**job.settings_json, "characterPresetId": case.preset, "normalThumbnailStyle": {"design": design}}
        db.commit()
    batch, metadata = render(case, SimpleNamespace(generate=lambda payload, images: result_for(payload)))
    assert not batch.failures
    assert metadata["thumbnail_subject_source"] == "asset"
    assert metadata["thumbnail_character_asset_id"] == asset_id
    assert metadata["thumbnail_emotion_selection_source"] == "single_emotion"
    assert "予備素材" in metadata["thumbnail_subject_reason"]
    published = [c for c in metadata["choiceHistory"] if c["kind"] == "thumbnail" and c["stage"] == "published"]
    assert published[-1]["values"]["templateDesign"] == design
    expected = tmp_path / "expected.jpg"
    real_test_renderer(case.video, expected, frame_time=metadata["thumbnail_source_time"],
                       character_style={"design": design},
                       eyebrow=metadata["thumbnail_kicker"], title_first_line=metadata["thumbnail_line1"],
                       title_second_line=metadata["thumbnail_line2"], character_asset_path=asset_path,
                       character_asset_face_box=None)
    assert expected.read_bytes() == Path(metadata["thumbnail_path"]).read_bytes()


def test_timeout_reserves_bounded_generation_only_for_new_auto(client, monkeypatch):  # noqa: F811
    from app.jobs import timeouts
    case = prepare(client, monkeypatch)
    monkeypatch.setattr(timeouts, "SessionLocal", case.factory)
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: case.storage)
    assert timeouts.automatic_thumbnail_copy_timeout(case.review.job_id) == 480
    with case.factory() as db:
        db.get(Job, case.review.job_id).settings_json = {"automationMode": "auto"}
        db.commit()
    assert timeouts.automatic_thumbnail_copy_timeout(case.review.job_id) == 0


def test_completed_manual_edit_replaces_automatic_decision_and_record(client, monkeypatch):  # noqa: F811
    from app.jobs.queue import get_enqueue_thumbnail_regeneration
    from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
    from app.main import app
    case = prepare(client, monkeypatch)
    render(case, SimpleNamespace(generate=lambda payload, images: result_for(payload)))
    case.review.state = "completed"
    write_subtitle_review(case.review, case.review_path)
    with case.factory() as db:
        job = db.get(Job, case.review.job_id)
        job.status = "completed"
        db.commit()
        record_completed_productions(db, job, case.storage)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queue.append(args)
    response = client.post("/api/exports/exp_thumbnail_style/thumbnail/regenerate", json={
        "frameSeconds": 4, "text": {"heading": "手動指定", "upper": "イヴ・クライン", "lower": "人が編集した文言"}})
    assert response.status_code == 202
    run_export_thumbnail_regeneration(*queue[0], session_factory=case.factory, paths=case.storage, normal_renderer=real_test_renderer)
    record = json.loads(case.storage.production_record("exp_thumbnail_style").read_text(encoding="utf-8"))
    assert record["revision"] == 2 and record["thumbnailLine2"] == "人が編集した文言"
    choices = [c for c in record["choiceHistory"] if c["kind"] == "thumbnail" and c["stage"] == "applied"]
    assert choices[-1]["source"] == "manual" and choices[-1]["selectedIds"] == []
