import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
from threading import Lock
import time
from urllib.parse import unquote
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.jobs as jobs_api
from app.db import Base, get_db
from app.downloads import TemporaryArchiveResponse, create_download_archive, upload_ready_name
from app.main import app
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths, get_storage_paths


@pytest.mark.parametrize(
    ("title", "expected", "truncated"),
    [
        ('動画?:/\\*"<>|', "動画？：／＼＊＂＜＞｜", False),
        ("公開\x00用\nタ\x7fイトル\u202e . \u3000", "公開用タイトル", False),
    ("CON", "_CON", False),
    ("CON .txt", "_CON .txt", False),
        ("nul.mp4", "_nul.mp4", False),
        ("COM¹", "_COM¹", False),
        ("LPT9.txt", "_LPT9.txt", False),
        ("conclusion", "conclusion", False),
        ("CON." + "a" * 96, "_CON." + "a" * 95, True),
        ("あ" * 100, "あ" * 100, False),
        ("😀" * 101, "😀" * 100, True),
        (None, "normal_01", False),
        ("", "normal_01", False),
        ("   ", "normal_01", False),
        ("\x00.", "normal_01", False),
    ],
)
def test_upload_ready_name(title, expected, truncated):
    result = upload_ready_name(title, fallback="normal_01")
    assert result.stem == expected
    assert result.truncated is truncated


@pytest.fixture()
def download_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    output = storage.job_outputs("job_download")
    video_path = output / "normal" / "normal_01.mp4"
    video_path.parent.mkdir()
    video_path.write_bytes(b"video")
    thumbnail = output / "thumbnails" / "normal_01.png"
    thumbnail.parent.mkdir()
    thumbnail.write_bytes(b"thumbnail")
    metadata = video_path.with_suffix(".json")
    metadata.write_text(
        json.dumps(
            {
                "thumbnail_status": "ready",
                "thumbnail_path": str(thumbnail),
                "thumbnail_filename": thumbnail.name,
                "youtube_description": "説明文",
                "youtube_tags": ["らでん", "切り抜き"],
                "youtube_hashtags": ["#らでん", "切り抜き"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with sessions() as db:
        db.add(Video(id="vid_download", original_filename="source.mp4", stored_path="source.mp4"))
        db.add(Job(id="job_download", video_id="vid_download", status="completed", settings_json={}))
        db.add(
            ExportItem(
                id="exp_download",
                job_id="job_download",
                video_id="vid_download",
                type="normal",
                title="公開タイトル？:話題",
                duration=120,
                score=90,
                video_path=str(video_path),
                metadata_path=str(metadata),
            )
        )
        db.commit()

    def get_session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_storage_paths] = lambda: storage
    try:
        yield TestClient(app), storage, sessions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def disposition_name(response):
    header = response.headers["content-disposition"]
    return unquote(header.split("filename*=utf-8''", 1)[1]) if "filename*=" in header else header.split('filename="')[1].rstrip('"')


@pytest.mark.parametrize("extension", [".png", ".jpg"])
def test_names_in_results_manifest_and_download_headers_match(download_client, extension):
    client, _, sessions = download_client
    if extension == ".jpg":
        with sessions() as db:
            metadata_path = Path(db.get(ExportItem, "exp_download").metadata_path)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            thumbnail = Path(metadata["thumbnail_path"])
            new_path = thumbnail.with_suffix(extension)
            thumbnail.rename(new_path)
            metadata.update(thumbnail_path=str(new_path), thumbnail_filename=new_path.name)
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    item = client.get("/api/jobs/job_download/results").json()["normalClips"][0]
    assert item["downloadFilename"] == "公開タイトル？：話題.mp4"
    assert item["thumbnailFilename"] == "公開タイトル？：話題" + extension
    assert item["downloadNameTruncated"] is False
    manifest = client.get("/api/exports/exp_download/posting-set").json()
    for file in manifest["files"]:
        response = client.get(file["url"])
        assert response.status_code == 200
        assert disposition_name(response) == file["name"]
        assert response.headers["content-type"].startswith(file["mimeType"])
    text = client.get("/api/exports/exp_download/posting-text").text
    assert "公開タイトル？:話題" in text  # Only filenames are converted.
    assert "説明文" in text and "らでん, 切り抜き" in text and "#らでん #切り抜き" in text


def test_truncation_notice_and_absent_title_fallback(download_client):
    client, _, sessions = download_client
    for title, expected, truncated in [("あ" * 101, "あ" * 100, True), ("", "normal_01", False)]:
        with sessions() as db:
            db.get(ExportItem, "exp_download").title = title
            db.commit()
        item = client.get("/api/jobs/job_download/results").json()["normalClips"][0]
        assert item["downloadFilename"] == expected + ".mp4"
        assert item["thumbnailFilename"] == expected + ".png"
        assert item["downloadNameTruncated"] is truncated
        assert disposition_name(client.get("/api/exports/exp_download/download")) == expected + ".mp4"


def test_posting_set_zip_contains_exact_three_files_and_is_removed(download_client):
    client, storage, _ = download_client
    response = client.get("/api/exports/exp_download/posting-set.zip")
    assert response.status_code == 200
    assert disposition_name(response) == "公開タイトル？：話題.zip"
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"公開タイトル？：話題.mp4", "公開タイトル？：話題.png", "公開タイトル？：話題_投稿文.txt"}
        assert archive.read("公開タイトル？：話題.mp4") == b"video"
        assert archive.read("公開タイトル？：話題.png") == b"thumbnail"
        assert "説明文" in archive.read("公開タイトル？：話題_投稿文.txt").decode("utf-8")
    assert not list(storage.temp.glob("download-*.zip"))


def test_full_zip_is_created_only_on_download_and_removed(download_client):
    client, storage, _ = download_client
    assert not storage.zip_path("job_download").exists()
    response = client.get("/api/jobs/job_download/download.zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.read("videos/normal/公開タイトル？：話題.mp4") == b"video"
        assert archive.read("thumbnails/normal/公開タイトル？：話題.png") == b"thumbnail"
    assert not storage.zip_path("job_download").exists()
    assert not list(storage.temp.glob("download-*.zip"))
    assert (storage.outputs / "job_download" / "normal" / "normal_01.mp4").read_bytes() == b"video"


def test_concurrent_zip_creation_is_locked_and_each_response_is_cleaned(download_client, monkeypatch):
    client, storage, _ = download_client
    original = jobs_api.create_download_archive
    mutex = Lock()
    active = 0
    maximum = 0
    paths = []

    def create(path, *args, **kwargs):
        nonlocal active, maximum
        with mutex:
            paths.append(path)
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.05)
            original(path, *args, **kwargs)
        finally:
            with mutex:
                active -= 1

    monkeypatch.setattr(jobs_api, "create_download_archive", create)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.get("/api/jobs/job_download/download.zip"), range(2)))
    assert maximum == 1
    assert len(set(paths)) == 2
    for response in responses:
        assert response.status_code == 200
        with ZipFile(BytesIO(response.content)) as archive:
            assert archive.testzip() is None
    assert not list(storage.temp.glob("download-*.zip"))


def test_archive_failure_removes_partial_temporary_file(download_client, monkeypatch):
    client, storage, _ = download_client

    def fail(path, *args, **kwargs):
        path.write_bytes(b"partial zip")
        raise OSError("archive failure")

    monkeypatch.setattr(jobs_api, "create_download_archive", fail)
    with pytest.raises(OSError, match="archive failure"):
        client.get("/api/jobs/job_download/download.zip")
    assert not list(storage.temp.glob("download-*.zip"))


def test_response_send_failure_removes_temporary_archive(tmp_path):
    path = tmp_path / "download.zip"
    path.write_bytes(b"zip")
    response = TemporaryArchiveResponse(path, filename="test.zip")

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        raise RuntimeError("client disconnected")

    with pytest.raises(RuntimeError, match="disconnected"):
        asyncio.run(response({"type": "http", "method": "GET", "headers": []}, receive, send))
    assert not path.exists()


def test_response_streams_and_cleans_even_with_path_send_extension(tmp_path):
    path = tmp_path / "download.zip"
    path.write_bytes(b"zip")
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        assert message["type"] != "http.response.pathsend"
        sent.append(message)

    asyncio.run(
        TemporaryArchiveResponse(path, filename="test.zip")(
            {"type": "http", "method": "GET", "headers": [], "extensions": {"http.response.pathsend": {}}},
            receive,
            send,
        )
    )
    assert b"".join(message.get("body", b"") for message in sent) == b"zip"
    assert not path.exists()


def test_legacy_selected_posting_fields_are_preserved(download_client):
    client, storage, sessions = download_client
    with sessions() as db:
        export = db.get(ExportItem, "exp_download")
        export.candidate_id = "candidate_legacy"
        metadata_path = Path(export.metadata_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for key in ["youtube_description", "youtube_tags", "youtube_hashtags"]:
            metadata.pop(key)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        db.commit()
    (storage.outputs / "job_download" / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [
                    {
                        "id": "candidate_legacy",
                        "youtube_description": "過去の説明",
                        "youtube_tags": ["旧タグ"],
                        "youtube_hashtags": ["旧ハッシュタグ"],
                    }
                ],
                "shorts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    text = client.get("/api/exports/exp_download/posting-text").text
    assert "過去の説明" in text and "旧タグ" in text and "#旧ハッシュタグ" in text


def test_existing_zip_is_served_without_rebuilding(download_client, monkeypatch):
    client, storage, _ = download_client
    existing = storage.zip_path("job_download")
    existing.write_bytes(b"legacy zip")
    before = existing.stat().st_mtime_ns
    monkeypatch.setattr(jobs_api, "create_download_archive", lambda *a, **kw: pytest.fail("must not rebuild"))
    assert client.get("/api/jobs/job_download/download.zip").content == b"legacy zip"
    assert existing.stat().st_mtime_ns == before


def test_equal_titles_keep_distinct_files_without_renaming_title(download_client):
    _, storage, sessions = download_client
    with sessions() as db:
        first = db.get(ExportItem, "exp_download")
        second_path = Path(first.video_path).with_name("normal_02.mp4")
        second_path.write_bytes(b"second video")
        second = ExportItem(id="exp_second", job_id=first.job_id, type="normal", title=first.title, video_path=str(second_path))
        path = storage.temp / "duplicate.zip"
        create_download_archive(path, [first, second], job_dir=storage.outputs / first.job_id)
    with ZipFile(path) as archive:
        assert archive.read("videos/normal/exp_download/公開タイトル？：話題.mp4") == b"video"
        assert archive.read("videos/normal/exp_second/公開タイトル？：話題.mp4") == b"second video"
        assert len(archive.namelist()) == len(set(archive.namelist()))


def test_missing_thumbnail_refuses_incomplete_posting_set(download_client):
    client, storage, _ = download_client
    (storage.outputs / "job_download" / "thumbnails" / "normal_01.png").unlink()
    assert client.get("/api/exports/exp_download/posting-set").status_code == 404
    assert client.get("/api/exports/exp_download/posting-set.zip").status_code == 404
    assert not list(storage.temp.glob("download-*.zip"))
