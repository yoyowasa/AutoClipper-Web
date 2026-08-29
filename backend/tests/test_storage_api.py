from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Job, Video
from app.storage.paths import StoragePaths, get_storage_paths


@pytest.fixture()
def storage_client(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], StoragePaths], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'storage-api.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure()
    settings = Settings(
        _env_file=None,
        storage_root=str(paths.root),
        source_library_root=str(tmp_path / "youtube"),
        storage_limit_bytes=1,
        storage_min_free_percent=0,
        storage_terminal_retention_days=7,
        storage_orphan_retention_hours=24,
        storage_cleanup_on_upload=True,
    )

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = lambda: paths
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app), testing_session, paths
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_expired_job(
    session_factory: sessionmaker[Session],
    paths: StoragePaths,
) -> tuple[str, Path]:
    old = datetime.utcnow() - timedelta(days=8)
    video_id = "vid_expired"
    job_id = "job_expired"
    upload = paths.uploads / f"{video_id}.mp4"
    upload.write_bytes(b"expired-source")
    output = paths.outputs / job_id / "result.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"expired-output")
    temp = paths.temp / job_id / "audio.wav"
    temp.parent.mkdir(parents=True)
    temp.write_bytes(b"expired-temp")
    with session_factory() as session:
        session.add(
            Video(
                id=video_id,
                original_filename=upload.name,
                stored_path=str(upload),
                created_at=old,
            )
        )
        session.add(
            Job(
                id=job_id,
                video_id=video_id,
                status="completed",
                progress=100,
                current_step="completed",
                settings_json={},
                created_at=old,
                updated_at=old,
            )
        )
        session.commit()
    return job_id, upload


def test_storage_status_and_cleanup_contract(
    storage_client: tuple[TestClient, sessionmaker[Session], StoragePaths],
) -> None:
    client, session_factory, paths = storage_client
    job_id, upload = _seed_expired_job(session_factory, paths)

    status_response = client.get("/api/storage/status")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["storageBytes"] > 1
    assert status_payload["storageLimitBytes"] == 1
    assert status_payload["warning"] is True
    assert status_payload["cleanupEligibleJobs"] == 1
    assert status_payload["cleanupEligibleVideos"] == 1

    forbidden_response = client.post("/api/storage/cleanup")
    assert forbidden_response.status_code == 403

    cleanup_response = client.post(
        "/api/storage/cleanup",
        headers={"X-AutoClipper-Action": "storage-cleanup"},
    )

    assert cleanup_response.status_code == 200
    cleanup_payload = cleanup_response.json()
    assert cleanup_payload["removedJobs"] == 1
    assert cleanup_payload["removedVideos"] == 1
    assert cleanup_payload["removedFiles"] == 3
    assert cleanup_payload["reclaimedBytes"] > 0
    assert cleanup_payload["errors"] == []
    assert not upload.exists()
    with session_factory() as session:
        assert session.get(Job, job_id) is None


def test_upload_runs_expired_cleanup_before_saving_new_video(
    storage_client: tuple[TestClient, sessionmaker[Session], StoragePaths],
) -> None:
    client, session_factory, paths = storage_client
    job_id, old_upload = _seed_expired_job(session_factory, paths)

    response = client.post(
        "/api/videos/upload",
        files={"file": ("new.mp4", b"new-video", "video/mp4")},
    )

    assert response.status_code == 201
    assert not old_upload.exists()
    with session_factory() as session:
        assert session.get(Job, job_id) is None
        new_video = session.get(Video, response.json()["videoId"])
        assert new_video is not None
        assert Path(new_video.stored_path).is_file()
