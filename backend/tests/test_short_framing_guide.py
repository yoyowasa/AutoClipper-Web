
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.framing_guide import get_enqueue_guide, router
from app.audio.transcribe_faster_whisper import TranscriptSegment, transcript_output_path, write_transcript_segments
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import Base, get_db
from app.jobs import short_framing_guide as guide
from app.jobs.subtitle_review import build_subtitle_review, subtitle_review_output_path, write_subtitle_review
from app.models import Job, Video
from app.render.crop_strategy import CropPlan
from app.storage.paths import StoragePaths, get_storage_paths


@pytest.fixture
def scene(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source = storage.uploads / "source.mp4"
    source.write_bytes(b"source video")
    output = storage.job_outputs("job_guide")
    selection = CandidateSelection(normalClips=[], shorts=[Candidate(
        id="short_1", type="short", start=1, end=21, duration=20, transcript_text="字幕", title="タイトル",
    )])
    segments = [TranscriptSegment(start=1, end=21, text="字幕", confidence=.9)]
    write_selected_clips(selection, output / "selected_clips.json")
    write_transcript_segments(segments, transcript_output_path(output))
    document = build_subtitle_review("job_guide", selection, segments)
    document.state = "completed"
    review_file = subtitle_review_output_path(output)
    write_subtitle_review(document, review_file)
    with sessions() as db:
        db.add(Video(id="video_guide", stored_path=str(source), original_filename="source.mp4",
                     width=1920, height=1080, duration=25, fps=30, has_audio=True))
        db.add(Job(id="job_guide", video_id="video_guide", status="completed", settings_json={}))
        db.commit()
    yield storage, sessions, document, review_file
    engine.dispose()


def test_cached_analysis_reused_for_offsets_zoom_and_completed_review_untouched(scene):
    storage, sessions, document, file = scene
    queue = []
    with sessions() as db:
        first = guide.prepare_framing_guide(db, storage, "job_guide", "short_1", lambda *args: queue.append(args))
        assert first.state == "queued"
        guide.prepare_framing_guide(db, storage, "job_guide", "short_1", lambda *args: queue.append(args))
        assert len(queue) == 1
        document.clips[0].framing_offset_x = 45
        document.clips[0].framing_offset_y = -20
        document.clips[0].framing_zoom = 2.1
        write_subtitle_review(document, file)
        assert guide.guide_context(db, storage, "job_guide", "short_1")["key"] == first.key
    before = file.read_bytes()
    calls = []

    def resolve(*args, **kwargs):
        calls.append((args, kwargs))
        return CropPlan(strategy_order=("person_tracking_crop",), person_center=(.7, .35)), []

    guide.run_short_framing_guide(*queue[0], paths=storage, session_factory=sessions, resolver=resolve)
    with sessions() as db:
        ready = guide.prepare_framing_guide(db, storage, "job_guide", "short_1", lambda *args: queue.append(args))
    assert ready.state == "ready" and ready.center == (.7, .35)
    assert len(queue) == len(calls) == 1
    assert file.read_bytes() == before
    assert not list(storage.outputs.rglob("*.mp4"))


@pytest.mark.parametrize("change", ["range", "layout", "bands"])
def test_context_invalidates_when_composition_changes(scene, change):
    storage, sessions, document, file = scene
    with sessions() as db:
        old = guide.guide_context(db, storage, "job_guide", "short_1")
        if change == "range":
            document.clips[0].start = 4
            selection_file = file.parent / "selected_clips.json"
            selection = json.loads(selection_file.read_text(encoding="utf-8"))
            selection["shorts"][0].update(start=4, duration=17)
            selection_file.write_text(json.dumps(selection), encoding="utf-8")
        elif change == "layout":
            document.short_layout = "blur_background"
        else:
            document.short_top_banner_enabled = not document.short_top_banner_enabled
        write_subtitle_review(document, file)
        assert guide.guide_context(db, storage, "job_guide", "short_1")["key"] != old["key"]


def test_old_worker_cannot_publish_over_new_request(scene):
    storage, sessions, _, _ = scene
    queue = []
    with sessions() as db:
        guide.prepare_framing_guide(db, storage, "job_guide", "short_1", lambda *args: queue.append(args))
    directory = guide.guide_dir(storage, "job_guide", "short_1")

    def resolve(*args, **kwargs):
        guide.write_state(directory, {**guide.read_state(directory), "requestId": "new-request"})
        return CropPlan(strategy_order=("center_crop",)), []

    guide.run_short_framing_guide(*queue[0], paths=storage, session_factory=sessions, resolver=resolve)
    assert guide.read_state(directory)["requestId"] == "new-request"
    assert guide.read_state(directory)["state"] == "queued"


def test_api_queues_once_and_exposes_no_internal_paths(scene):
    storage, sessions, _, file = scene
    app = FastAPI()
    app.include_router(router)

    def db():
        with sessions() as session:
            yield session

    queued = []
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    app.dependency_overrides[get_enqueue_guide] = lambda: lambda *args: queued.append(args)
    before = file.read_bytes()
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post("/api/jobs/job_guide/subtitle-review/clips/short_1/framing-guide")
            assert response.status_code == 200
            assert response.json()["contentHeight"] > 0
            assert "source" not in response.json() and "requestId" not in response.json()
        assert client.post("/api/jobs/missing/subtitle-review/clips/short_1/framing-guide").status_code == 404
        assert client.post("/api/jobs/job_guide/subtitle-review/clips/missing/framing-guide").status_code == 409
    assert len(queued) == 1
    assert file.read_bytes() == before
