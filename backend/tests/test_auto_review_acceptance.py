"""1-E: real API/state/ASS/PIL/record/download chain; no Codex, GPU or FFmpeg."""

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import select

import app.jobs.runner as runner
from app.jobs.subtitle_review import load_subtitle_review
from app.jobs.thumbnails import read_export_metadata
from app.models import ExportItem
from app.production_records import ProductionRecord
from app.render.render_thumbnail import render_short_thumbnail
from test_auto_human_review import prepare, guarded_client as guarded_client
from test_guarded_quality_gate_integration import _decision
from test_thumbnail_text_styles import real_test_renderer, frame_runner
from test_upload_ready_downloads import disposition_name


@pytest.mark.parametrize("short", [False, True], ids=["normal", "short"])
def test_confirmed_choices_reach_record_and_exact_posting_set(guarded_client, monkeypatch, tmp_path, short):
    data = prepare(guarded_client, monkeypatch, tmp_path, short=short)
    # Media/model execution are explicit test doubles. API, ASS, PIL, publication and downloads are real.
    monkeypatch.setattr("app.jobs.thumbnails.ensure_thumbnail_candidates", lambda *_: [])
    data.deps = replace(data.deps, normal_thumbnail_renderer=real_test_renderer,
                        short_thumbnail_renderer=lambda *a, **kw: render_short_thumbnail(*a, **kw, command_runner=frame_runner))
    assert runner.run_autoclipper_job(data.job_id, session_factory=data.factory, paths=data.storage,
                                      dependencies=data.deps)[-1] == "awaiting_subtitle_review"
    review = load_subtitle_review(data.review_path)
    clip = review.clips[0]
    assert not clip.confirmed and not data.previews and not data.renders
    assert clip.selected_title_id == clip.recommended_title_id == "suggestion_1"
    prefix = f"/api/jobs/{data.job_id}/subtitle-review"
    # One apply carries all edits. Keep the automatically chosen thumbnail copy unmodified.
    payload = {
        "title": "画面用の題材", "publicationTitle": "投稿用？:受入確認", "hookText": "確認手順の要点" if short else "",
        "thumbnailKicker": clip.thumbnail_kicker, "thumbnailLine1": clip.thumbnail_line1, "thumbnailLine2": clip.thumbnail_line2,
        "youtubeDescription": "人が確認した投稿文", "youtubeTags": ["確認"], "youtubeHashtags": ["#確認"],
        "segments": [{"segmentId": clip.segment_ids[0], "text": "人が確認して修正した字幕"}],
        "subtitleStyle": {"fontSize": 72, "primaryColor": "#FFF200", "positionMode": "explicit", "xPercent": 48, "yPercent": 75},
        **({"hookSceneStart": clip.start + 1, "hookSceneEnd": clip.start + 3,
            "framing": {"framingOffsetX": 8, "framingOffsetY": -4, "framingZoom": 1.2}} if short else {}),
    }
    response = data.client.post(f"{prefix}/clips/{clip.id}/apply", json=payload)
    assert response.status_code == 200, response.text
    assert len(data.previews) == 1 and not data.renders
    assert data.client.post(f"{prefix}/finalize").status_code == 409  # Exact preview still required.
    assert len(data.previews) == 1
    assert runner.run_subtitle_review_preview(*data.previews[0], session_factory=data.factory,
                                             paths=data.storage, dependencies=data.deps) == ["ready"]
    confirmed = load_subtitle_review(data.review_path)
    assert confirmed.clips[0].confirmed and confirmed.clips[0].preview_state == "ready"
    assert confirmed.segments[0].text == payload["segments"][0]["text"]
    # Only the physical-video gate is stubbed: test media are not genuine MP4s.
    monkeypatch.setattr(runner, "evaluate_post_render_quality_gate", lambda **kw: _decision(
        kw["job_id"], stage="post_render", outcome="pass", mode="auto"))
    response = data.client.post(f"{prefix}/finalize")
    assert response.status_code == 202, response.text
    assert len(data.renders) == 1
    assert runner.run_subtitle_review_render(data.job_id, render_revision=data.renders[0][1],
        session_factory=data.factory, paths=data.storage, dependencies=data.deps)[-1] == "completed"
    assert len(data.calls) == 1
    with data.factory() as db:
        export = db.scalar(select(ExportItem).where(ExportItem.job_id == data.job_id))
        metadata = read_export_metadata(export)
        export_id = export.id
        video = Path(export.video_path).read_bytes()
    record = ProductionRecord.model_validate_json(data.storage.production_record(export_id).read_bytes())
    assert record.publicationTitle == "投稿用？：受入確認" + ("" if short else "儒烏風亭らでん【ReGLOSS切り抜き】")
    assert record.overlayTitle == payload["title"]
    assert record.hookText == (payload["hookText"] or None)
    assert (record.hookSceneStart, record.hookSceneEnd) == ((1, 3) if short else (None, None))
    assert record.completedDurationSeconds == pytest.approx(record.bodyDurationSeconds + (2 if short else 0))
    history = record.choiceHistory
    assert {"range", "title_hook", "post_copy", "thumbnail", "framing", "text_style", "effects", "publication"} <= {
        c.kind for c in history}
    assert any(c.kind == "title_hook" and c.source == "automatic" and c.selectedIds == ["suggestion_1"] for c in history)
    manual = [c for c in history if c.kind == "title_hook" and c.source == "manual"]
    assert manual[-1].values["publicationTitle"] == confirmed.clips[0].publication_title and manual[-1].selectedIds == []
    styles = [c for c in history if c.kind == "text_style" and c.stage == "published"][-1].values["renderedTextStyles"]
    assert any(s["role"] == "subtitle" and s["primaryColor"] == "#FFF200" and s["fontSize"] == 72 for s in styles)
    assert all(c.policyVersion and c.inputRevision for c in history if c.stage == "published")
    if not short:
        assert metadata["thumbnail_copy_selected_id"] == "copy_2"
        assert record.thumbnailLine1 == payload["segments"][0]["text"]
    result = data.client.get(f"/api/jobs/{data.job_id}/results")
    assert result.status_code == 200
    item = result.json()["shorts" if short else "normalClips"][0]
    assert item["downloadFilename"] == record.publicationTitle + ".mp4"
    manifest = data.client.get(f"/api/exports/{export_id}/posting-set").json()
    assert len(manifest["files"]) == 3
    bodies = {}
    for file in manifest["files"]:
        downloaded = data.client.get(file["url"])
        assert downloaded.status_code == 200 and disposition_name(downloaded) == file["name"]
        bodies[file["name"]] = downloaded.content
    assert bodies[item["downloadFilename"]] == video
    with Image.open(BytesIO(bodies[item["thumbnailFilename"]])) as image:
        assert image.width > 0 and image.height > 0
    posting = bodies[record.publicationTitle + "_投稿文.txt"].decode("utf-8")
    assert payload["publicationTitle"] in posting and payload["youtubeDescription"] in posting
    archive = data.client.get(f"/api/exports/{export_id}/posting-set.zip")
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zipped:
        assert {name: zipped.read(name) for name in zipped.namelist()} == bodies
    assert not list(data.storage.temp.glob("download-*.zip"))
    assert not data.storage.zip_path(data.job_id).exists()
