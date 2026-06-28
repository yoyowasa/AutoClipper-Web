from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.jobs.queue import get_enqueue_job
from app.jobs.runner import run_dummy_autoclipper_job
from app.jobs.status import SUCCESS_STATUSES
from app.main import app
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths, get_storage_paths


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


def test_upload_video_creates_video_record(client: TestClient) -> None:
    response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["videoId"].startswith("vid_")
    assert payload["filename"] == "sample.mp4"

    with next(app.dependency_overrides[get_db]()) as db:
        video = db.get(Video, payload["videoId"])
        assert video is not None
        assert video.original_filename == "sample.mp4"
        assert Path(video.stored_path).is_file()
    assert Path(video.stored_path).read_bytes() == b"fake video bytes"


def test_upload_video_rejects_invalid_file_type(client: TestClient) -> None:
    response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.txt", b"not video", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "invalid_file_type"


def test_upload_video_rejects_oversized_file_and_removes_partial_file(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_bytes=4)

    response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"too large", "video/mp4")},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
    storage = app.dependency_overrides[get_storage_paths]()
    assert list(storage.uploads.iterdir()) == []


def test_create_job_and_fetch_status(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    create_response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "mode": "high_quality",
                "normalClipCount": 6,
                "shortCount": 12,
            },
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["jobId"].startswith("job_")
    assert created["status"] == "queued"

    status_response = client.get(f"/api/jobs/{created['jobId']}")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload == {
        "id": created["jobId"],
        "status": "queued",
        "progress": 5,
        "currentStep": "Queued",
        "details": {},
        "error": None,
    }

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.video_id == upload["videoId"]
        assert job.settings_json["mode"] == "high_quality"
        assert job.settings_json["normalMinDuration"] == 90.0
        assert job.settings_json["normalMaxDuration"] == 600.0
        assert job.settings_json["shortMinDuration"] == 20.0
        assert job.settings_json["shortMaxDuration"] == 75.0
        assert job.settings_json["selectionPolicy"] == "fill_requested"
        assert job.settings_json["crossTypeOverlapDedupe"] is False
        assert job.settings_json["openaiCandidateLimit"] == 40
        assert job.settings_json["openaiModel"] == "gpt-5.5"
        assert job.settings_json["openaiFallbackToRuleScore"] is True


def test_create_job_persists_advanced_duration_settings(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 20,
                "normalMaxDuration": 60,
                "shortMinDuration": 15,
                "shortMaxDuration": 45,
                "selectionPolicy": "strict_quality",
                "crossTypeOverlapDedupe": True,
                "useOpenAIScoring": True,
                "openaiCandidateLimit": 7,
                "openaiModel": "gpt-test",
                "openaiFallbackToRuleScore": False,
                "minFinalScore": 0,
            },
        },
    )

    assert response.status_code == 201
    created = response.json()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.settings_json["normalMinDuration"] == 20.0
        assert job.settings_json["normalMaxDuration"] == 60.0
        assert job.settings_json["shortMinDuration"] == 15.0
        assert job.settings_json["shortMaxDuration"] == 45.0
        assert job.settings_json["selectionPolicy"] == "strict_quality"
        assert job.settings_json["crossTypeOverlapDedupe"] is True
        assert job.settings_json["useOpenAIScoring"] is True
        assert job.settings_json["openaiCandidateLimit"] == 7
        assert job.settings_json["openaiModel"] == "gpt-test"
        assert job.settings_json["openaiFallbackToRuleScore"] is False
        assert job.settings_json["minFinalScore"] == 0


def test_create_job_rejects_invalid_duration_ranges(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalMinDuration": 60,
                "normalMaxDuration": 20,
            },
        },
    )

    assert response.status_code == 422


def test_openapi_exposes_advanced_job_duration_settings(client: TestClient) -> None:
    payload = client.get("/openapi.json").json()
    properties = payload["components"]["schemas"]["JobSettings"]["properties"]

    assert properties["normalMinDuration"]["default"] == 90.0
    assert properties["normalMaxDuration"]["default"] == 600.0
    assert properties["shortMinDuration"]["default"] == 20.0
    assert properties["shortMaxDuration"]["default"] == 75.0
    assert properties["selectionPolicy"]["default"] == "fill_requested"
    assert properties["crossTypeOverlapDedupe"]["default"] is False
    assert properties["openaiCandidateLimit"]["default"] == 40
    assert properties["openaiModel"]["default"] == "gpt-5.5"
    assert properties["openaiFallbackToRuleScore"]["default"] is True


def test_results_zip_download_and_export_download(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()

    storage = app.dependency_overrides[get_storage_paths]()
    job_output_dir = storage.outputs / created["jobId"]
    job_output_dir.mkdir(parents=True, exist_ok=True)
    normal_path = job_output_dir / "normal.mp4"
    short_path = job_output_dir / "short.mp4"
    zip_path = job_output_dir / "download.zip"
    normal_path.write_bytes(b"normal mp4")
    short_path.write_bytes(b"short mp4")
    zip_path.write_bytes(b"zip bytes")

    with next(app.dependency_overrides[get_db]()) as db:
        video = db.get(Video, upload["videoId"])
        assert video is not None
        db.add_all(
            [
                ExportItem(
                    id="exp_normal",
                    job_id=created["jobId"],
                    video_id=video.id,
                    candidate_id=None,
                    type="normal",
                    title="Normal Clip",
                    duration=120.5,
                    score=84.0,
                    video_path=str(normal_path),
                ),
                ExportItem(
                    id="exp_short",
                    job_id=created["jobId"],
                    video_id=video.id,
                    candidate_id=None,
                    type="short",
                    title="Short Clip",
                    duration=42.0,
                    score=88.0,
                    video_path=str(short_path),
                ),
            ]
        )
        db.commit()

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")

    assert results_response.status_code == 200
    results = results_response.json()
    assert results["jobId"] == created["jobId"]
    assert results["zipDownloadUrl"] == f"/api/jobs/{created['jobId']}/download.zip"
    assert results["normalClips"][0]["downloadUrl"] == "/api/exports/exp_normal/download"
    assert results["shorts"][0]["videoUrl"] == "/api/exports/exp_short/download"

    zip_response = client.get(f"/api/jobs/{created['jobId']}/download.zip")
    assert zip_response.status_code == 200
    assert zip_response.content == b"zip bytes"

    normal_download = client.get("/api/exports/exp_normal/download")
    assert normal_download.status_code == 200
    assert normal_download.content == b"normal mp4"

    short_download = client.get("/api/exports/exp_short/download")
    assert short_download.status_code == 200
    assert short_download.content == b"short mp4"


def test_dummy_job_completes_and_results_are_downloadable(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()

    storage = app.dependency_overrides[get_storage_paths]()
    visited_statuses = run_dummy_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
    )

    assert visited_statuses == SUCCESS_STATUSES

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["progress"] == 100

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert len(results["normalClips"]) == 2
    assert len(results["shorts"]) == 3

    zip_response = client.get(results["zipDownloadUrl"])
    assert zip_response.status_code == 200
    assert zip_response.content

    normal_download = client.get(results["normalClips"][0]["downloadUrl"])
    assert normal_download.status_code == 200
    assert normal_download.content.startswith(b"AutoClipper dummy MP4")


def test_create_job_rejects_missing_video(client: TestClient) -> None:
    response = client.post("/api/jobs", json={"videoId": "vid_missing", "settings": {}})

    assert response.status_code == 404
    assert response.json()["detail"] == "video not found"


def test_missing_downloads_return_404(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()

    zip_response = client.get(f"/api/jobs/{created['jobId']}/download.zip")
    export_response = client.get("/api/exports/exp_missing/download")

    assert zip_response.status_code == 404
    assert export_response.status_code == 404


def test_upload_and_job_records_are_queryable(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()

    with next(app.dependency_overrides[get_db]()) as db:
        videos = db.scalars(select(Video)).all()
        jobs = db.scalars(select(Job)).all()

    assert [video.id for video in videos] == [upload["videoId"]]
    assert [job.id for job in jobs] == [created["jobId"]]
