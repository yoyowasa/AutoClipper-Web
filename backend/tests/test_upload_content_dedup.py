from collections.abc import Generator
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.storage.content as content_storage
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Video
from app.storage.paths import StoragePaths, get_storage_paths


@pytest.fixture()
def upload_client(
    tmp_path: Path,
) -> Generator[tuple[TestClient, StoragePaths, sessionmaker[Session]], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    app.dependency_overrides[get_settings] = lambda: Settings()

    try:
        yield TestClient(app), storage, testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _heatmap_payload(media: bytes, value: float) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "dedup-test",
                "fetched_at": "2026-08-28T00:00:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.08.28",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 120.0,
            "heatmap_available": True,
            "heatmap": [{"start_time": 10.0, "end_time": 15.0, "value": value}],
        }
    ).encode("utf-8")


def _video_path(
    session_factory: sessionmaker[Session],
    video_id: str,
) -> Path:
    with session_factory() as db:
        video = db.get(Video, video_id)
        assert video is not None
        return Path(video.stored_path)


def test_duplicate_uploads_share_one_content_blob(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, session_factory = upload_client
    media = b"same video content"

    first = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", media, "video/mp4")},
    )
    second = client.post(
        "/api/videos/upload",
        files={"file": ("renamed.mp4", media, "video/mp4")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["videoId"] != second.json()["videoId"]
    first_path = _video_path(session_factory, first.json()["videoId"])
    second_path = _video_path(session_factory, second.json()["videoId"])
    blobs = list((storage.uploads / ".blobs").iterdir())
    assert first_path == second_path
    assert len(blobs) == 1
    assert first_path == blobs[0]
    assert not (storage.uploads / ".incoming").exists()


def test_duplicate_uploads_keep_adjacent_heatmap_sidecars_isolated(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, session_factory = upload_client
    media = b"same video with separate heatmaps"

    first = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_payload(media, 0.25),
                "application/json",
            ),
        },
    )
    second = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_payload(media, 0.75),
                "application/json",
            ),
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_path = _video_path(session_factory, first.json()["videoId"])
    second_path = _video_path(session_factory, second.json()["videoId"])
    first_sidecar = storage.video_heatmap(first.json()["videoId"])
    second_sidecar = storage.video_heatmap(second.json()["videoId"])
    assert first_path == second_path
    assert first_sidecar != second_sidecar
    assert json.loads(first_sidecar.read_text(encoding="utf-8"))["heatmap"][0]["value"] == 0.25
    assert json.loads(second_sidecar.read_text(encoding="utf-8"))["heatmap"][0]["value"] == 0.75
    assert len(list((storage.uploads / ".blobs").iterdir())) == 1


def test_invalid_heatmap_removes_incoming_upload_without_publishing(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, _session_factory = upload_client
    media = b"invalid heatmap upload"
    payload = json.loads(_heatmap_payload(media, 0.5))
    payload["media"]["sha256"] = "0" * 64

    response = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            ),
        },
    )

    assert response.status_code == 422
    assert not (storage.uploads / ".incoming").exists()
    assert not (storage.uploads / ".blobs").exists()
    assert list(storage.uploads.iterdir()) == []


def test_hardlink_failure_falls_back_to_exclusive_blob_copy(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, storage, _session_factory = upload_client

    def fail_hardlink(_source: Path, _target: Path) -> None:
        raise OSError("hard links unavailable")

    monkeypatch.setattr(content_storage.os, "link", fail_hardlink)
    response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"video", "video/mp4")},
    )

    assert response.status_code == 201
    stored_path = _video_path(_session_factory, response.json()["videoId"])
    assert stored_path.read_bytes() == b"video"
    assert len(list((storage.uploads / ".blobs").iterdir())) == 1
    assert not (storage.uploads / ".incoming").exists()


def test_oversized_upload_keeps_existing_limit_and_removes_incoming(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, _session_factory = upload_client
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_bytes=4)

    response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"too large", "video/mp4")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "file_too_large",
        "message": "upload exceeds maximum size of 4 bytes",
    }
    assert not (storage.uploads / ".incoming").exists()
    assert list(storage.uploads.iterdir()) == []


def test_duplicate_upload_rejects_same_size_corrupted_blob(
    upload_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, session_factory = upload_client
    original = b"AAAA"
    first = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", original, "video/mp4")},
    )
    assert first.status_code == 201
    first_path = _video_path(session_factory, first.json()["videoId"])
    first_path.write_bytes(b"BBBB")

    second = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", original, "video/mp4")},
    )

    assert second.status_code == 500
    assert second.json()["detail"]["code"] == "upload_blob_conflict"
    assert not (storage.uploads / ".incoming").exists()
    assert len(list((storage.uploads / ".blobs").iterdir())) == 1
    with session_factory() as db:
        assert len(db.query(Video).all()) == 1
