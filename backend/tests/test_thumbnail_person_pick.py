import json

import numpy as np
from PIL import Image
import pytest

from app.jobs import thumbnail_candidates as candidates
from app.jobs.queue import get_enqueue_thumbnail_regeneration
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.main import app
from app.render import anime_subject
from test_api_routes import client as client
from test_thumbnail_candidates import ENDPOINT, FACE, seed_frames
from test_thumbnail_text_styles import seed_thumbnail, real_test_renderer


LEFT = (.2, .32, .15, .18)       # another character on the left, fits the same 2x half-body gate
TINY = (.85, .4, .03, .05)       # too small: would need more than 2x upscale
DUPLICATE = (.51, .31, .14, .17)  # the automatic face detected again


@pytest.fixture(autouse=True)
def detected_people(monkeypatch):
    candidates._people_in_still.cache_clear()
    monkeypatch.setattr(candidates, "detect_anime_faces", lambda image: [DUPLICATE, TINY, LEFT])
    yield
    candidates._people_in_still.cache_clear()


def run_queued(queue, storage, factory):
    seen = {}

    def render(*args, **kwargs):
        seen.update(kwargs)
        return real_test_renderer(*args, **kwargs)
    run_export_thumbnail_regeneration(*queue[-1], paths=storage, session_factory=factory, normal_renderer=render,
                                     frame_selector=lambda *a, **k: pytest.fail("legacy search"))
    return seen


def test_people_lists_the_automatic_face_first_and_only_faces_that_fit(client):  # noqa: F811
    storage, _, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata)
    before = metadata.read_bytes()
    people = client.get(ENDPOINT + "/candidates/frame_00/people").json()["people"]
    assert [(p["index"], p["x"], p["y"]) for p in people] == [(0, FACE[0], FACE[1]), (1, LEFT[0], LEFT[1])]
    assert all(isinstance(p["closeAvailable"], bool) for p in people)
    assert client.get(ENDPOINT + "/candidates/frame_99/people").status_code == 404
    assert metadata.read_bytes() == before  # detection only, nothing is saved


def test_saving_with_another_person_centers_on_that_face_and_records_it(client):  # noqa: F811
    storage, factory, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queue.append(args)
    assert client.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "frameCandidateId": "frame_00", "subjectFaceIndex": 1, "subjectSource": "video",
    }).status_code == 202
    seen = run_queued(queue, storage, factory)
    assert seen["video_face"] == LEFT
    saved = json.loads(metadata.read_text(encoding="utf-8"))
    assert saved["thumbnail_status"] == "ready" and saved["thumbnail_subject_face_index"] == 1
    item = client.get("/api/jobs/job_thumbnail_style/results").json()["normalClips"][0]
    assert item["thumbnailSubjectFaceIndex"] == 1
    choice = [c for c in saved["choiceHistory"] if c["kind"] == "thumbnail"][-1]
    assert choice["values"]["subjectFaceIndex"] == 1


def test_another_frame_or_codex_choice_returns_to_the_automatic_person(client):  # noqa: F811
    storage, factory, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata)
    queue = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = lambda: lambda *args: queue.append(args)
    assert client.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "frameCandidateId": "frame_00", "subjectFaceIndex": 1, "advanceFrame": True,
    }).status_code == 202
    seen = run_queued(queue, storage, factory)
    assert seen["video_face"] == FACE
    assert json.loads(metadata.read_text(encoding="utf-8"))["thumbnail_subject_face_index"] is None


def test_a_person_missing_from_the_still_is_rejected(client):  # noqa: F811
    storage, _, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata)
    assert client.post(ENDPOINT + "/regenerate", json={
        "frameSeconds": 4, "frameCandidateId": "frame_00", "subjectFaceIndex": 2,
    }).status_code == 422
    with pytest.raises(ValueError, match="人物"):
        candidates.video_candidate_kwargs(json.loads(metadata.read_text(encoding="utf-8")),
                                          storage.job_outputs("job_thumbnail_style"), "exp_thumbnail_style",
                                          candidate_id="frame_00", face_index=2)
    kwargs = candidates.video_candidate_kwargs(json.loads(metadata.read_text(encoding="utf-8")),
                                               storage.job_outputs("job_thumbnail_style"), "exp_thumbnail_style",
                                               candidate_id="frame_00", face_index=1)
    assert kwargs["video_face"] == LEFT


def test_preview_uses_the_chosen_person(client, monkeypatch):  # noqa: F811
    storage, _, metadata, _, _ = seed_thumbnail(client)
    seed_frames(storage, metadata)
    from app.jobs import thumbnail_preview
    seen = {}
    real = thumbnail_preview.render_normal_thumbnail

    def render(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)
    monkeypatch.setattr(thumbnail_preview, "render_normal_thumbnail", render)
    prepared = client.post(ENDPOINT + "/preview/prepare?frameCandidateId=frame_00").json()
    assert prepared["state"] == "ready"
    from test_thumbnail_text_styles import TEXT_STYLES
    response = client.post(ENDPOINT + "/preview", json={
        "frameKey": prepared["frameKey"], "frameCandidateId": "frame_00", "subjectFaceIndex": 1,
        "text": {"heading": "", "upper": "人物", "lower": ""}, "textStyles": TEXT_STYLES})
    assert response.status_code == 200
    assert seen["video_face"] == LEFT


def test_anime_faces_are_largest_first_and_the_single_face_api_is_unchanged(monkeypatch):
    class Detector:
        def detectMultiScale(self, gray, **kwargs):
            return np.array([[100, 100, 60, 60], [500, 120, 90, 90], [300, 900, 90, 90]])
    monkeypatch.setattr(anime_subject, "_anime_cascade", lambda: Detector())
    image = Image.new("RGB", (960, 1000))
    faces = anime_subject.detect_anime_faces(image)
    assert [round(face[2] * 960) for face in faces] == [90, 60]  # the face at y=0.94 is outside the usable band
    assert anime_subject.detect_anime_face(image) == faces[0]
