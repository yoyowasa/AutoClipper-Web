import json
from types import SimpleNamespace

import pytest

from test_api_routes import client as client
from test_thumbnail_text_styles import seed_thumbnail, real_test_renderer
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.queue import get_enqueue_thumbnail_copy, get_enqueue_thumbnail_regeneration
from app.jobs.subtitle_review import build_subtitle_review, write_subtitle_review, subtitle_review_output_path
from app.jobs.thumbnail_copy import build_copy_input, run_thumbnail_copy_generation
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.main import app
from app.models import ExportItem, Job
from app.scoring.thumbnail_copy import ThumbnailCopyResult, THUMBNAIL_COPY_SCHEMA, CodexThumbnailCopyGenerator


def seed(client):  # noqa: F811 - imported pytest fixture is passed to this helper
    storage, factory, metadata_path, image, video = seed_thumbnail(client)
    selection = CandidateSelection(
        normalClips=[
            Candidate(
                id="normal",
                type="normal",
                start=10,
                end=30,
                duration=20,
                title="確定した公開タイトル",
                overlay_title="",
                hook_text="",
                transcript_text="旧文字",
            )
        ],
        shorts=[],
    )
    review = build_subtitle_review(
        "job_thumbnail_style",
        selection,
        [
            TranscriptSegment(start=11, end=14, text="２人でプリンを食べました。"),
            TranscriptSegment(start=35, end=38, text="動画の範囲外の宝くじ１００万円"),
        ],
    )
    review.state = "completed"
    review.segments[0].original_text = "２人でプリソを食べました。"
    review.segments[0].edited = True
    review_path = subtitle_review_output_path(storage.job_outputs(review.job_id))
    write_subtitle_review(review, review_path)
    queued = []
    app.dependency_overrides[get_enqueue_thumbnail_copy] = lambda: lambda *args: queued.append(args)
    return SimpleNamespace(
        storage=storage,
        factory=factory,
        metadata=metadata_path,
        image=image,
        video=video,
        review=review,
        review_path=review_path,
        queued=queued,
    )


def generated(payload):
    segment = payload["segments"][0]
    return ThumbnailCopyResult.model_validate(
        {
            "suggestions": [
                {
                    "id": f"copy_{i}",
                    "heading": "２人で",
                    "upper": "プリンを",
                    "lower": "食べました",
                    "reason": "保存済み字幕に基づく",
                    "evidence": [{"segmentId": segment["segmentId"], "quote": "プリンを食べました"}],
                }
                for i in range(1, 4)
            ],
            "recommendedId": "copy_2",
        }
    )


def test_completed_scope_corrected_text_and_empty_overlays(client):  # noqa: F811
    case = seed(client)
    with case.factory() as db:
        payload = build_copy_input(db, case.storage, db.get(ExportItem, "exp_thumbnail_style"))["payload"]
    assert [s["text"] for s in payload["segments"]] == ["２人でプリンを食べました。"]
    assert payload["segments"][0]["start"] == 1
    assert not {"overlayTitle", "hookText"}.intersection(payload)
    assert "プリソ" not in json.dumps(payload, ensure_ascii=False)


def test_generation_selection_manual_edit_and_thumbnail_only_save(client):  # noqa: F811
    case = seed(client)
    review_before = case.review_path.read_bytes()
    metadata_before = case.metadata.read_bytes()
    video_before = case.video.read_bytes()
    endpoint = "/api/exports/exp_thumbnail_style/thumbnail/copy"
    assert client.get(endpoint).json()["state"] == "idle"
    response = client.post(endpoint)
    assert response.status_code == 202, response.text
    assert client.post(endpoint).json()["requestId"] == response.json()["requestId"]
    assert len(case.queued) == 1
    run_thumbnail_copy_generation(
        *case.queued[-1],
        session_factory=case.factory,
        paths=case.storage,
        generator=SimpleNamespace(generate=lambda payload, images: generated(payload)),
    )
    result = client.get(endpoint).json()
    assert result["state"] == "ready", result
    assert len(result["suggestions"]) == 3
    assert result["recommendedId"] == "copy_2"
    assert case.metadata.read_bytes() == metadata_before
    selected = result["suggestions"][1]
    render_queue = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: render_queue.append(args)
    text = {key: selected[key] for key in ("heading", "upper", "lower")}
    text["lower"] = "一緒に食べた"
    response = client.post("/api/exports/exp_thumbnail_style/thumbnail/regenerate", json={"frameSeconds": 4, "text": text})
    assert response.status_code == 202, response.text
    run_export_thumbnail_regeneration(
        *render_queue[-1], session_factory=case.factory, paths=case.storage, normal_renderer=real_test_renderer
    )
    saved = client.get("/api/jobs/job_thumbnail_style/results").json()["normalClips"][0]
    assert saved["thumbnailLine2"] == "一緒に食べた"
    assert saved["thumbnailKicker"] == "２人で"
    assert case.video.read_bytes() == video_before
    assert case.review_path.read_bytes() == review_before
    assert client.post(endpoint).json()["requestId"] == result["requestId"]
    assert client.post(endpoint + "?force=true").json()["requestId"] != result["requestId"]


@pytest.mark.parametrize("invalid", ["foreign_segment", "invented_quote", "invented_number", "new_video"])
def test_rejects_ungrounded_or_stale_generation(client, invalid):  # noqa: F811
    case = seed(client)

    def generate(payload, images):
        output = generated(payload)
        if invalid == "foreign_segment":
            output.suggestions[0].evidence[0].segment_id = "foreign"
        elif invalid == "invented_quote":
            output.suggestions[0].evidence[0].quote = "宝くじが当たった"
        elif invalid == "invented_number":
            output.suggestions[0].heading = "１００万円"
        else:
            case.video.write_bytes(b"new published video")
        return output

    endpoint = "/api/exports/exp_thumbnail_style/thumbnail/copy"
    client.post(endpoint)
    before = case.metadata.read_bytes()
    run_thumbnail_copy_generation(
        *case.queued[-1], session_factory=case.factory, paths=case.storage, generator=SimpleNamespace(generate=generate)
    )
    result = client.get(endpoint).json()
    assert result["state"] == "failed"
    assert result["suggestions"] == []
    assert case.metadata.read_bytes() == before


def test_generation_rejects_unfinished_job_and_missing_subtitles(client):  # noqa: F811
    case = seed(client)
    with case.factory() as db:
        db.get(Job, "job_thumbnail_style").status = "awaiting_subtitle_review"
        db.commit()
    assert client.post("/api/exports/exp_thumbnail_style/thumbnail/copy").status_code == 409
    assert not case.queued


def test_thumbnail_copy_bridge_schema_is_allowlisted(tmp_path):
    from launcher.codex_bridge import validate_request

    request = {
        "schemaVersion": 1,
        "task": "thumbnail_copy_suggestions",
        "requestId": "a" * 32,
        "prompt": "copy only",
        "responseSchema": THUMBNAIL_COPY_SCHEMA,
        "images": [],
        "threadScope": "job:thumb_exp",
    }
    parsed = validate_request(request, storage_root=tmp_path)
    assert parsed.task == "thumbnail_copy_suggestions"
    generator = CodexThumbnailCopyGenerator(storage_root=tmp_path, job_id="job", clip_id="thumb_exp")
    assert generator.task == parsed.task
    assert generator.response_schema == THUMBNAIL_COPY_SCHEMA
