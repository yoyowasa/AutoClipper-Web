from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_api_routes import client as client
from app.audio.transcribe_faster_whisper import TranscriptSegment, write_transcript_segments
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import get_db
from app.jobs.subtitle_review import build_subtitle_review, load_subtitle_review, write_subtitle_review
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths


def seed_review(api_client: TestClient):
    video = api_client.post("/api/videos/upload", files={"file": ("test.mp4", b"video", "video/mp4")}).json()
    created = api_client.post("/api/jobs", json={"videoId": video["videoId"], "settings": {}}).json()
    job_id = created["jobId"]
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = "awaiting_subtitle_review"
        db.commit()
    segments = [
        TranscriptSegment(start=1, end=2, text="アカネとアカネです", confidence=0.9),
        TranscriptSegment(start=6, end=7, text="アカネさんの話"),
        TranscriptSegment(start=21, end=22, text="別の言葉"),
    ]
    clips = [Candidate(id=name, type=kind, start=start, end=end, duration=end-start, title=name, transcript_text="話")
             for name, kind, start, end in [("normal", "normal", 0, 10), ("short", "short", 5, 15), ("other", "normal", 20, 30)]]
    selection = CandidateSelection(normalClips=[clips[0], clips[2]], shorts=[clips[1]])
    document = build_subtitle_review(job_id, selection, segments)
    for clip in document.clips:
        clip.confirmed = True
        clip.preview_state = "ready"
    path = app.dependency_overrides[get_storage_paths]().job_outputs(job_id) / "subtitle_review.json"
    write_selected_clips(selection, path.parent / "selected_clips.json")
    write_transcript_segments(segments, path.parent / "transcript_segments.json")
    write_subtitle_review(document, path)
    return job_id, path, document


def test_bulk_correction_saves_shared_segments_and_can_undo(client: TestClient) -> None:  # noqa: F811
    job_id, path, document = seed_review(client)
    updates = [{"segmentId": s.id, "before": s.text, "text": s.text.replace("アカネ", "あかね")} for s in document.segments[:2]]
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": updates})
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    assert [s.text for s in saved.segments] == ["あかねとあかねです", "あかねさんの話", "別の言葉"]
    assert [(s.id, s.start, s.end, s.original_text) for s in saved.segments] == [
        (s.id, s.start, s.end, s.original_text) for s in document.segments
    ]
    assert {c.id: c.confirmed for c in saved.clips} == {"normal": False, "short": False, "other": True}
    assert [c.title for c in saved.clips] == [c.title for c in document.clips]
    assert len({c.id for c in saved.clips if c.preview_state == "queued"}) == 2
    undo = [{"segmentId": item["segmentId"], "before": item["text"], "text": item["before"]} for item in updates]
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": undo}).status_code == 200
    assert [s.text for s in load_subtitle_review(path).segments] == [s.text for s in document.segments]
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": undo}).status_code == 409


@pytest.mark.parametrize("failure,expected", [("stale", 409), ("missing", 404), ("duplicate", 422), ("completed", 409)])
def test_bulk_correction_rejects_entire_batch_without_partial_save(client: TestClient, failure: str, expected: int) -> None:  # noqa: F811
    job_id, path, document = seed_review(client)
    updates = [{"segmentId": s.id, "before": s.text, "text": "修正後"} for s in document.segments[:2]]
    if failure == "stale":
        updates[1]["before"] = "古い本文"
    elif failure == "missing":
        updates[1]["segmentId"] = "missing"
    elif failure == "duplicate":
        updates[1] = updates[0]
    elif failure == "completed":
        with next(app.dependency_overrides[get_db]()) as db:
            db.get(Job, job_id).status = "completed"
            db.commit()
    original = Path(path).read_bytes()
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={"segments": updates}).status_code == expected
    assert Path(path).read_bytes() == original
