import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import build_audio_features
from app.db import Base, get_db
from app.jobs.queue import get_enqueue_job
from app.jobs.runner import AutoClipperPipelineDependencies, run_autoclipper_job
from app.jobs.status import SUCCESS_STATUSES
from app.main import app
from app.models import Job
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.black_screen import BlackScreenSegment
from app.video.probe import VideoMetadata
from app.video.scene_detect import SceneSegment


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    def override_get_storage_paths() -> StoragePaths:
        return storage

    def override_get_enqueue_job() -> None:
        return lambda job_id: None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = override_get_storage_paths
    app.dependency_overrides[get_enqueue_job] = override_get_enqueue_job

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def fake_transcript() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=30.0, text="why automation mistakes matter before launch"),
        TranscriptSegment(start=35.0, end=80.0, text="how teams can fix the process with a clear checklist"),
        TranscriptSegment(start=85.0, end=140.0, text="the final lesson is to measure progress every week"),
        TranscriptSegment(start=145.0, end=210.0, text="another complete section for a normal clip selection"),
    ]


def test_real_pipeline_produces_results_metadata_and_zip(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": True,
                "normalizeAudio": True,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [
            SilenceSegment(start=30.0, end=35.0, duration=5.0),
            SilenceSegment(start=80.0, end=85.0, duration=5.0),
            SilenceSegment(start=140.0, end=145.0, duration=5.0),
        ],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [BlackScreenSegment(start=220.0, end=225.0, duration=5.0)],
        normal_renderer=fake_render,
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == SUCCESS_STATUSES[1:]
    assert not (storage.temp / created["jobId"]).exists()

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert len(results["normalClips"]) == 1
    assert len(results["shorts"]) == 1

    normal_download = client.get(results["normalClips"][0]["downloadUrl"])
    short_download = client.get(results["shorts"][0]["downloadUrl"])
    assert normal_download.status_code == 200
    assert short_download.status_code == 200
    assert normal_download.content.startswith(b"rendered normal_")
    assert short_download.content.startswith(b"rendered short_")

    job_dir = storage.outputs / created["jobId"]
    for name in [
        "video_metadata.json",
        "transcript_segments.json",
        "scene_segments.json",
        "silence_segments.json",
        "audio_features.json",
        "visual_quality.json",
        "candidates.json",
        "scored_candidates.json",
        "selected_clips.json",
        "render_failures.json",
    ]:
        assert (job_dir / name).is_file()

    selected_payload = json.loads((job_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert len(selected_payload["normalClips"]) == 1
    assert len(selected_payload["shorts"]) == 1
    assert (job_dir / "normal" / "normal_01.json").is_file()
    assert (job_dir / "shorts" / "short_01.json").is_file()

    zip_path = storage.zip_path(created["jobId"])
    assert zip_path.is_file()
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "normal_01.mp4" in names
    assert "short_01.mp4" in names
    assert "normal_01.json" in names
    assert "short_01.json" in names
    assert "selected_clips.json" in names


def test_real_pipeline_openai_failure_falls_back_to_rule_scoring(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": True,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    class BrokenScorer:
        def score(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("OpenAI unavailable")

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
        openai_scorer=BrokenScorer(),  # type: ignore[arg-type]
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.json()["status"] == "completed"
    scored_payload = json.loads(
        (storage.outputs / created["jobId"] / "scored_candidates.json").read_text(encoding="utf-8")
    )
    assert any("openai_fallback_rule_score" in item["risk_flags"] for item in scored_payload)


def test_real_pipeline_fixture_transcript_completes_without_transcriber(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "e2eFixtureTranscript": True,
                "normalClipCount": 0,
                "shortCount": 1,
                "shortMinDuration": 20,
                "shortMaxDuration": 25,
                "shortStepSeconds": 5,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": False,
                "normalizeAudio": False,
                "shortLayout": "center_crop",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fail_if_transcribed(_wav_path: str | Path) -> list[TranscriptSegment]:
        raise AssertionError("fixture transcript mode must not call the transcriber")

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=25.0,
            width=320,
            height=180,
            fps=10.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=fail_if_transcribed,
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=25.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == SUCCESS_STATUSES[1:]
    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.json()["status"] == "completed"

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    results = results_response.json()
    assert results["normalClips"] == []
    assert len(results["shorts"]) == 1
    assert client.get(results["shorts"][0]["downloadUrl"]).content.startswith(b"rendered short_")

    transcript_payload = json.loads(
        (storage.outputs / created["jobId"] / "transcript_segments.json").read_text(encoding="utf-8")
    )
    assert transcript_payload[0]["text"].startswith("Why automation mistakes matter before launch.")
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_marks_failed_without_unhandled_exception_when_no_output_is_usable(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def failing_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        raise RuntimeError("all renders failed")

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=failing_render,
        short_renderer=failing_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "no_usable_output"
    assert visited_statuses[-1] == "rendering_shorts"
    assert not (storage.temp / created["jobId"]).exists()

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.error_message == "Pipeline completed analysis but produced no usable clips."


def test_real_pipeline_marks_failed_for_missing_audio_without_unhandled_exception(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()
    storage = app.dependency_overrides[get_storage_paths]()
    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=False,
        )
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert visited_statuses == ["probing"]
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "missing_audio"
    assert "no audio track" in payload["error"]["message"]
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_marks_failed_when_no_candidates_found(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=10.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: [TranscriptSegment(start=0.0, end=10.0, text="too short")],
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=10.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "no_candidates_found"
    assert "No clip candidates" in payload["error"]["message"]
