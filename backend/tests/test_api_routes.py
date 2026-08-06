from collections.abc import Generator
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.jobs.queue import (
    get_enqueue_job,
    get_enqueue_subtitle_review_hook_scene_update,
)
from app.jobs.runner import run_dummy_autoclipper_job
from app.jobs.status import SUCCESS_STATUSES
from app.main import app
from app.models import AppPreference, ExportItem, Job, Video, utc_now
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.heatmap import heatmap_sidecar_path


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


def _heatmap_upload_payload(
    media: bytes,
    *,
    filename: str = "sample.mp4",
    available: bool = True,
) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "BaW_jenozKc",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": filename,
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 120.0,
            "heatmap_available": available,
            "heatmap": (
                [{"start_time": 10.0, "end_time": 15.0, "value": 0.8}]
                if available
                else []
            ),
        },
        ensure_ascii=False,
    ).encode("utf-8")


def test_upload_video_accepts_and_stores_valid_heatmap_sidecar(client: TestClient) -> None:
    media = b"video with heatmap"
    response = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_upload_payload(media),
                "application/json",
            ),
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        video = db.get(Video, response.json()["videoId"])
        assert video is not None
        stored_sidecar = heatmap_sidecar_path(Path(video.stored_path))
    payload = json.loads(stored_sidecar.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["media"]["filename"] == "sample.mp4"
    assert payload["heatmap"][0]["value"] == 0.8


def test_upload_video_accepts_unavailable_heatmap_for_existing_fallback(
    client: TestClient,
) -> None:
    media = b"video without heatmap data"
    response = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_upload_payload(media, available=False),
                "application/json",
            ),
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        video = db.get(Video, response.json()["videoId"])
        assert video is not None
        payload = json.loads(
            heatmap_sidecar_path(Path(video.stored_path)).read_text(encoding="utf-8")
        )
    assert payload["heatmap_available"] is False
    assert payload["heatmap"] == []


def test_create_job_requires_available_heatmap_for_interval_mode(client: TestClient) -> None:
    media = b"video for interval mode"
    without_sidecar = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", media, "video/mp4")},
    ).json()
    missing_response = client.post(
        "/api/jobs",
        json={
            "videoId": without_sidecar["videoId"],
            "settings": {"heatmapIntervalMode": True},
        },
    )

    unavailable_upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_upload_payload(media, available=False),
                "application/json",
            ),
        },
    ).json()
    unavailable_response = client.post(
        "/api/jobs",
        json={
            "videoId": unavailable_upload["videoId"],
            "settings": {"heatmapIntervalMode": True},
        },
    )

    assert missing_response.status_code == 422
    assert missing_response.json()["detail"] == {
        "code": "heatmap_interval_mode_requires_data",
        "message": "JSON区間モードには有効な人気区間JSONが必要です。",
        "reason": "heatmap_sidecar_not_provided",
    }
    assert unavailable_response.status_code == 422
    assert unavailable_response.json()["detail"]["reason"] == "heatmap_unavailable"


def test_create_job_persists_enabled_heatmap_interval_mode(client: TestClient) -> None:
    media = b"video with enabled interval mode"
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "sample.mp4.heatmap.json",
                _heatmap_upload_payload(media),
                "application/json",
            ),
        },
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"heatmapIntervalMode": True},
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["heatmapIntervalMode"] is True


def test_upload_video_rejects_invalid_heatmap_and_cleans_up_media(client: TestClient) -> None:
    media = b"video with invalid heatmap"
    payload = json.loads(_heatmap_upload_payload(media))
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
    assert response.json()["detail"]["code"] == "heatmap_media_sha256_mismatch"
    storage = app.dependency_overrides[get_storage_paths]()
    assert list(storage.uploads.iterdir()) == []
    with next(app.dependency_overrides[get_db]()) as db:
        assert list(db.scalars(select(Video)).all()) == []


def test_upload_video_rejects_wrong_sidecar_filename_and_cleans_up_media(
    client: TestClient,
) -> None:
    media = b"video with wrongly named heatmap"
    response = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": (
                "other.mp4.heatmap.json",
                _heatmap_upload_payload(media),
                "application/json",
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "heatmap_filename_mismatch"
    storage = app.dependency_overrides[get_storage_paths]()
    assert list(storage.uploads.iterdir()) == []


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
    assert response.json()["detail"]["message"] == "upload exceeds maximum size of 4 bytes"
    storage = app.dependency_overrides[get_storage_paths]()
    assert list(storage.uploads.iterdir()) == []


def _seed_reeditable_export() -> tuple[str, str, bytes]:
    storage = app.dependency_overrides[get_storage_paths]()
    job_id = "job_reedit_upload"
    source_path = storage.uploads / "vid_reedit_source.mp4"
    source_path.write_bytes(b"source video")
    output_dir = storage.job_outputs(job_id)
    rendered_path = output_dir / "shorts" / "short_01.mp4"
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_bytes = b"completed rendered short"
    rendered_path.write_bytes(rendered_bytes)
    candidate_id = "candidate_short_reedit"
    timestamp = "2026-07-27T00:00:00+00:00"
    (output_dir / "subtitle_review.json").write_text(
        json.dumps(
            {
                "version": 1,
                "jobId": job_id,
                "state": "completed",
                "renderRevision": 1,
                "reopenedAt": None,
                "sourceVideoUrl": "/api/jobs/job_reedit_upload/source-video",
                "clips": [
                    {
                        "id": candidate_id,
                        "type": "short",
                        "title": "完成したショート",
                        "originalTitle": "完成したショート",
                        "titleEdited": False,
                        "hookText": "",
                        "hookDurationSeconds": 3,
                        "start": 0,
                        "end": 10,
                        "duration": 10,
                        "previewVideoUrl": None,
                        "segmentIds": ["segment_00000"],
                        "confirmed": True,
                        "editedSegmentCount": 0,
                    }
                ],
                "segments": [
                    {
                        "id": "segment_00000",
                        "index": 0,
                        "start": 0,
                        "end": 2,
                        "originalText": "字幕",
                        "text": "字幕",
                        "confidence": 0.9,
                        "edited": False,
                        "affectedClipIds": [candidate_id],
                    }
                ],
                "confirmedClipCount": 1,
                "totalClipCount": 1,
                "editedSegmentCount": 0,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "selected_clips.json").write_text("{}\n", encoding="utf-8")
    (output_dir / "transcript_segments.json").write_text("[]\n", encoding="utf-8")

    with next(app.dependency_overrides[get_db]()) as db:
        video = Video(
            id="vid_reedit_upload",
            original_filename="source.mp4",
            stored_path=str(source_path),
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="completed",
            progress=100,
            current_step="Completed",
            settings_json={},
        )
        export = ExportItem(
            id="exp_reedit_upload",
            job_id=job.id,
            video_id=video.id,
            candidate_id=candidate_id,
            type="short",
            title="完成したショート",
            duration=10,
            score=0.8,
            video_path=str(rendered_path),
        )
        db.add_all([video, job, export])
        db.commit()
    return job_id, candidate_id, rendered_bytes


def test_completed_mp4_upload_reopens_matching_job_without_saving_copy(
    client: TestClient,
) -> None:
    job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    upload_files_before = set(storage.uploads.iterdir())

    response = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("renamed-finished.mp4", rendered_bytes, "video/mp4")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "jobId": job_id,
        "exportId": "exp_reedit_upload",
        "matchedClipId": candidate_id,
        "clipType": "short",
        "title": "完成したショート",
        "reviewState": "awaiting_review",
    }
    assert set(storage.uploads.iterdir()) == upload_files_before
    review = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    assert review["state"] == "awaiting_review"
    assert review["renderRevision"] == 2
    assert review["confirmedClipCount"] == 0
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "awaiting_subtitle_review"

    repeated = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished-again.mp4", rendered_bytes, "video/mp4")},
    )
    assert repeated.status_code == 200
    assert client.get(f"/api/jobs/{job_id}/subtitle-review").json()["renderRevision"] == 2

    queued_hook_updates: list[
        tuple[str, str, float | None, float | None]
    ] = []
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = (
        lambda: lambda queued_job_id, clip_id, start, end: queued_hook_updates.append(
            (queued_job_id, clip_id, start, end)
        )
    )
    hook_response = client.patch(
        (
            f"/api/jobs/{job_id}/subtitle-review/clips/"
            f"{candidate_id}/hook-scene"
        ),
        json={"start": 2, "end": 4},
    )

    assert hook_response.status_code == 202
    assert hook_response.json()["status"] == "preparing_subtitle_review"
    assert queued_hook_updates == [(job_id, candidate_id, 2.0, 4.0)]


def test_completed_mp4_upload_rejects_unknown_or_invalid_file(client: TestClient) -> None:
    _seed_reeditable_export()

    unknown = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("unknown.mp4", b"different output", "video/mp4")},
    )
    invalid = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("metadata.json", b"{}", "application/json")},
    )

    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "reedit_source_not_found"
    assert invalid.status_code == 415
    assert invalid.json()["detail"]["code"] == "reedit_mp4_required"


def test_subtitle_review_clip_styles_are_saved_and_omission_preserves_them(
    client: TestClient,
) -> None:
    job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    title_style = {
        "fontPreset": "heavy",
        "fontSize": 96,
        "primaryColor": "#FFF200",
        "outlineColor": "#000000",
        "outlineWidth": 6,
        "xPercent": 50,
        "yPercent": 12,
    }
    subtitle_style = {
        "fontPreset": "mono",
        "fontSize": 72,
        "primaryColor": "#FFFFFF",
        "outlineColor": "#000000",
        "outlineWidth": 4,
        "xPercent": 50,
        "yPercent": 84,
    }

    updated = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={
            "title": "スタイル変更",
            "hookText": "冒頭フック",
            "hookDurationSeconds": 3,
            "titleStyle": title_style,
            "hookStyle": None,
            "subtitleStyle": subtitle_style,
        },
    )

    assert updated.status_code == 200
    clip = updated.json()["clips"][0]
    assert clip["titleStyle"] == title_style
    assert clip["hookStyle"] is None
    assert clip["subtitleStyle"] == subtitle_style

    legacy_update = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={
            "title": "旧クライアント互換",
            "hookText": "冒頭フック",
            "hookDurationSeconds": 3,
        },
    )

    assert legacy_update.status_code == 200
    legacy_clip = legacy_update.json()["clips"][0]
    assert legacy_clip["titleStyle"] == title_style
    assert legacy_clip["subtitleStyle"] == subtitle_style


def test_subtitle_style_presets_are_persisted_in_database(client: TestClient) -> None:
    initial_response = client.get("/api/preferences/subtitle-style-presets")

    assert initial_response.status_code == 200
    assert initial_response.json() == {
        "version": 1,
        "slots": [None, None, None],
    }

    payload = {
        "version": 1,
        "slots": [
            {
                "name": "ホロライブ用",
                "savedAt": "2026-07-26T01:02:03Z",
                "style": {
                    "shortSubtitleFontName": "Source Han Sans JP Heavy",
                    "shortSubtitleFontSize": 76,
                    "shortSubtitleXPercent": 50,
                    "shortSubtitleYPercent": 68.75,
                    "shortSubtitlePrimaryColor": "#FFF200",
                    "normalSubtitleFontSize": 65,
                    "normalSubtitleXPercent": 50,
                    "normalSubtitleYPercent": 84,
                    "normalSubtitleOutlineColor": "#000000",
                },
            },
            None,
            None,
        ],
    }

    save_response = client.put(
        "/api/preferences/subtitle-style-presets",
        json=payload,
    )

    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["slots"][0]["name"] == "ホロライブ用"
    assert saved["slots"][0]["style"]["shortSubtitleFontSize"] == 76
    assert saved["slots"][0]["style"]["shortSubtitleYPercent"] == 68.75

    get_response = client.get("/api/preferences/subtitle-style-presets")

    assert get_response.status_code == 200
    assert get_response.json() == saved
    with next(app.dependency_overrides[get_db]()) as db:
        preference = db.get(AppPreference, "subtitle_style_presets")
        assert preference is not None
        assert preference.value_json["slots"][0]["name"] == "ホロライブ用"


def test_subtitle_style_presets_reject_invalid_slot_payload(client: TestClient) -> None:
    too_many_slots = client.put(
        "/api/preferences/subtitle-style-presets",
        json={"version": 1, "slots": [None, None, None, None]},
    )
    invalid_color = client.put(
        "/api/preferences/subtitle-style-presets",
        json={
            "version": 1,
            "slots": [
                {
                    "name": "invalid",
                    "savedAt": "2026-07-26T01:02:03Z",
                    "style": {"shortSubtitlePrimaryColor": "yellow"},
                },
                None,
                None,
            ],
        },
    )

    assert too_many_slots.status_code == 422
    assert invalid_color.status_code == 422


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
        assert job.settings_json["maxCandidates"] == 1200
        assert job.settings_json["maxRawCandidatesPerType"] == 250000
        assert job.settings_json["maxKeptCandidatesPerType"] == 1200
        assert job.settings_json["maxCandidatesPerTimeBucket"] == 100
        assert job.settings_json["candidateTimeBucketSeconds"] == 300.0
        assert job.settings_json["maxCandidateGenerationMemoryMb"] == 12000
        assert job.settings_json["candidateChunkSeconds"] == 600.0
        assert job.settings_json["candidateChunkOverlapSeconds"] == 75.0
        assert job.settings_json["maxCharsPerLineShort"] == 16
        assert job.settings_json["maxCharsPerLineNormal"] == 28
        assert job.settings_json["maxLines"] == 2
        assert job.settings_json["minSubtitleDuration"] == 1.1
        assert job.settings_json["maxSubtitleDuration"] == 4.2
        assert job.settings_json["minGapBetweenSubtitles"] == 0.08
        assert job.settings_json["selectionPolicy"] == "fill_requested"
        assert job.settings_json["crossTypeOverlapDedupe"] is False
        assert job.settings_json["heatmapIntervalMode"] is False
        assert job.settings_json["openaiCandidateLimit"] == 40
        assert job.settings_json["openaiModel"] == "gpt-5.5"
        assert job.settings_json["openaiFallbackToRuleScore"] is True
        assert job.settings_json["ensureSelectedOpenAIScored"] is True
        assert job.settings_json["openaiFinalistScoringLimit"] == 20
        assert job.settings_json["transcriptionLanguage"] == "ja"


def test_job_status_exposes_subtitle_correction_progress_artifact(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(created["jobId"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "subtitle_correction_progress.json").write_text(
        json.dumps(
            {
                "stage": "correcting_subtitles",
                "stageProgress": 47,
                "correctionBatchesCompleted": 8,
                "correctionBatchesTotal": 17,
                "correctionRetryCount": 1,
                "fallbackUsed": False,
                "finished": False,
            }
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        job.status = "correcting_subtitles"
        job.progress = 34
        job.current_step = "Correcting subtitles (8/17 batches)"
        db.commit()

    response = client.get(f"/api/jobs/{created['jobId']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "correcting_subtitles"
    assert payload["progress"] == 34
    assert payload["details"]["stageProgress"] == 47
    assert payload["details"]["correctionBatchesCompleted"] == 8
    assert payload["details"]["correctionBatchesTotal"] == 17
    assert payload["details"]["correctionRetryCount"] == 1


def test_create_job_accepts_normal_only_and_short_only_requests(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    normal_only = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"normalClipCount": 2, "shortCount": 0},
        },
    )
    short_only = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"normalClipCount": 0, "shortCount": 3},
        },
    )

    assert normal_only.status_code == 201
    assert short_only.status_code == 201


def test_create_job_rejects_request_without_any_output_type(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"normalClipCount": 0, "shortCount": 0},
        },
    )

    assert response.status_code == 422


def test_create_job_persists_type_specific_subtitle_styles(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "shortSubtitleFontName": "Source Han Sans JP Heavy",
                "shortSubtitlePrimaryColor": "#FFF200",
                "shortSubtitleOutlineColor": "#000000",
                "normalSubtitleFontName": "Noto Serif CJK JP",
                "normalSubtitlePrimaryColor": "#FFFFFF",
                "normalSubtitleOutlineColor": "#102030",
            },
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["shortSubtitleFontName"] == "Source Han Sans JP Heavy"
        assert job.settings_json["shortSubtitlePrimaryColor"] == "#FFF200"
        assert job.settings_json["shortSubtitleOutlineColor"] == "#000000"
        assert job.settings_json["normalSubtitleFontName"] == "Noto Serif CJK JP"
        assert job.settings_json["normalSubtitlePrimaryColor"] == "#FFFFFF"
        assert job.settings_json["normalSubtitleOutlineColor"] == "#102030"


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
                "normalClipSelectionPreset": "important",
                "shortClipSelectionPreset": "funny",
                "normalClipGuidance": "復帰理由と今後の予定",
                "shortClipGuidance": "笑えるリアクション",
                "excludeIntroOutro": True,
                "excludePromotionalContent": True,
                "maxCandidates": 300,
                "maxRawCandidatesPerType": 5000,
                "maxKeptCandidatesPerType": 300,
                "maxCandidatesPerTimeBucket": 25,
                "candidateTimeBucketSeconds": 120,
                "maxCandidateGenerationMemoryMb": 2048,
                "candidateChunkSeconds": 300,
                "candidateChunkOverlapSeconds": 60,
                "maxCharsPerLineShort": 14,
                "maxCharsPerLineNormal": 26,
                "maxLines": 2,
                "minSubtitleDuration": 1.25,
                "maxSubtitleDuration": 3.75,
                "minGapBetweenSubtitles": 0.12,
                "subtitleFontName": "Source Han Sans JP Heavy",
                "subtitleTitleFontName": "Source Han Sans JP Heavy",
                "shortSubtitleFontSize": 86,
                "shortSubtitleOutline": 4,
                "shortSubtitleLowerMargin": 680,
                "shortSubtitleAlignment": 5,
                "shortSubtitleXPercent": 40,
                "shortSubtitleYPercent": 57.3,
                "normalSubtitleFontSize": 60,
                "normalSubtitleOutline": 4,
                "normalSubtitleLowerMargin": 110,
                "normalSubtitleXPercent": 50,
                "normalSubtitleYPercent": 84,
                "selectionPolicy": "strict_quality",
                "crossTypeOverlapDedupe": True,
                "useOpenAIScoring": True,
                "openaiCandidateLimit": 7,
                "openaiModel": "gpt-test",
                "openaiFallbackToRuleScore": False,
                "ensureSelectedOpenAIScored": True,
                "openaiFinalistScoringLimit": 5,
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
        assert job.settings_json["normalClipSelectionPreset"] == "important"
        assert job.settings_json["shortClipSelectionPreset"] == "funny"
        assert job.settings_json["normalClipGuidance"] == "復帰理由と今後の予定"
        assert job.settings_json["shortClipGuidance"] == "笑えるリアクション"
        assert job.settings_json["excludeIntroOutro"] is True
        assert job.settings_json["excludePromotionalContent"] is True
        assert job.settings_json["maxCandidates"] == 300
        assert job.settings_json["maxRawCandidatesPerType"] == 5000
        assert job.settings_json["maxKeptCandidatesPerType"] == 300
        assert job.settings_json["maxCandidatesPerTimeBucket"] == 25
        assert job.settings_json["candidateTimeBucketSeconds"] == 120.0
        assert job.settings_json["maxCandidateGenerationMemoryMb"] == 2048
        assert job.settings_json["candidateChunkSeconds"] == 300.0
        assert job.settings_json["candidateChunkOverlapSeconds"] == 60.0
        assert job.settings_json["maxCharsPerLineShort"] == 14
        assert job.settings_json["maxCharsPerLineNormal"] == 26
        assert job.settings_json["maxLines"] == 2
        assert job.settings_json["minSubtitleDuration"] == 1.25
        assert job.settings_json["maxSubtitleDuration"] == 3.75
        assert job.settings_json["minGapBetweenSubtitles"] == 0.12
        assert job.settings_json["subtitleFontName"] == "Source Han Sans JP Heavy"
        assert job.settings_json["subtitleTitleFontName"] == "Source Han Sans JP Heavy"
        assert job.settings_json["shortSubtitleFontSize"] == 86
        assert job.settings_json["shortSubtitleOutline"] == 4
        assert job.settings_json["shortSubtitleLowerMargin"] == 680
        assert job.settings_json["shortSubtitleAlignment"] == 5
        assert job.settings_json["shortSubtitleXPercent"] == 40.0
        assert job.settings_json["shortSubtitleYPercent"] == 57.3
        assert job.settings_json["normalSubtitleFontSize"] == 60
        assert job.settings_json["normalSubtitleOutline"] == 4
        assert job.settings_json["normalSubtitleLowerMargin"] == 110
        assert job.settings_json["normalSubtitleXPercent"] == 50.0
        assert job.settings_json["normalSubtitleYPercent"] == 84.0
        assert job.settings_json["selectionPolicy"] == "strict_quality"
        assert job.settings_json["crossTypeOverlapDedupe"] is True
        assert job.settings_json["useOpenAIScoring"] is True
        assert job.settings_json["openaiCandidateLimit"] == 7
        assert job.settings_json["openaiModel"] == "gpt-test"
        assert job.settings_json["openaiFallbackToRuleScore"] is False
        assert job.settings_json["ensureSelectedOpenAIScored"] is True
        assert job.settings_json["openaiFinalistScoringLimit"] == 5
        assert job.settings_json["minFinalScore"] == 0


def test_low_cost_defaults_do_not_require_selected_openai_scoring(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {"mode": "low_cost"}},
    )

    assert response.status_code == 201
    created = response.json()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.settings_json["mode"] == "low_cost"
        assert job.settings_json["ensureSelectedOpenAIScored"] is False


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


def test_create_job_persists_manual_clip_ranges_and_disables_unused_openai(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 0,
                "shortCount": 2,
                "shortClipSelectionPreset": "funny",
                "shortClipGuidance": "大きなリアクション",
                "shortClipTimeRanges": [
                    {"startSeconds": 65, "endSeconds": 82},
                    {"startSeconds": 120.5, "endSeconds": 145},
                ],
                "useOpenAIScoring": True,
            },
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["shortClipTimeRanges"] == [
            {"startSeconds": 65.0, "endSeconds": 82.0},
            {"startSeconds": 120.5, "endSeconds": 145.0},
        ]
        assert job.settings_json["useOpenAIScoring"] is False


def test_create_job_rejects_partially_entered_manual_clip_ranges(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 0,
                "shortCount": 2,
                "shortClipTimeRanges": [
                    {"startSeconds": 65, "endSeconds": 82},
                    {"startSeconds": 120.5, "endSeconds": None},
                ],
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
    assert properties["normalClipSelectionPreset"]["default"] == "auto"
    assert properties["shortClipSelectionPreset"]["default"] == "auto"
    assert properties["normalClipGuidance"]["default"] == ""
    assert properties["shortClipGuidance"]["default"] == ""
    assert properties["normalClipTimeRanges"]["type"] == "array"
    assert properties["normalClipTimeRanges"]["maxItems"] == 12
    assert properties["shortClipTimeRanges"]["type"] == "array"
    assert properties["shortClipTimeRanges"]["maxItems"] == 24
    assert properties["excludeIntroOutro"]["default"] is True
    assert properties["excludePromotionalContent"]["default"] is False
    assert properties["maxCandidates"]["default"] == 1200
    assert properties["maxRawCandidatesPerType"]["default"] == 250000
    assert properties["maxKeptCandidatesPerType"]["default"] == 1200
    assert properties["maxCandidatesPerTimeBucket"]["default"] == 100
    assert properties["candidateTimeBucketSeconds"]["default"] == 300.0
    assert properties["maxCandidatesPerStartBucket"]["default"] == 5
    assert properties["candidateStartBucketSeconds"]["default"] == 15.0
    assert properties["maxCandidateGenerationMemoryMb"]["default"] == 12000
    assert properties["candidateChunkSeconds"]["default"] == 600.0
    assert properties["candidateChunkOverlapSeconds"]["default"] == 75.0
    assert properties["selectionPolicy"]["default"] == "fill_requested"
    assert properties["crossTypeOverlapDedupe"]["default"] is False
    assert properties["heatmapIntervalMode"]["default"] is False
    assert properties["openaiCandidateLimit"]["default"] == 40
    assert properties["openaiModel"]["default"] == "gpt-5.5"
    assert properties["openaiFallbackToRuleScore"]["default"] is True
    assert properties["whisperModelSize"]["default"] == "base"
    assert properties["transcriptionLanguage"]["default"] == "ja"
    assert properties["transcriptionLanguage"]["const"] == "ja"
    assert properties["transcriptionDevice"]["default"] == "cpu"
    assert properties["transcriptionComputeType"]["default"] == "auto"
    assert properties["subtitleCorrectionMode"]["default"] == "off"
    assert properties["subtitleCorrectionScope"]["default"] == "all"
    assert properties["transcriptCorrectionGlossary"]["type"] == "array"
    assert properties["subtitleCorrectionSuspicionThreshold"]["default"] == 0.4
    assert properties["subtitleCorrectionModel"]["default"] == "gpt-5.5"
    assert properties["subtitleCorrectionReasoningEffort"]["default"] == "default"
    assert properties["subtitleCorrectionMinConfidence"]["default"] == 0.9
    assert properties["subtitleCorrectionBatchSize"]["default"] == 40
    assert properties["subtitleCorrectionContextSegments"]["default"] == 2
    assert properties["subtitleCorrectionFallbackEnabled"]["default"] is True
    assert "ensureSelectedOpenAIScored" in properties
    assert "openaiFinalistScoringLimit" in properties
    assert "subtitleFontName" in properties
    assert "subtitleOutline" in properties
    assert "shortSubtitleFontSize" in properties
    assert "shortSubtitleLowerMargin" in properties
    assert "shortSubtitleXPercent" in properties
    assert "shortSubtitleYPercent" in properties
    assert "normalSubtitleFontSize" in properties
    assert "normalSubtitleLowerMargin" in properties
    assert "normalSubtitleXPercent" in properties
    assert "normalSubtitleYPercent" in properties


def test_job_creation_rejects_unsupported_transcription_profile(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"whisperModelSize": "tiny"},
        },
    )

    assert response.status_code == 422


def test_job_creation_normalizes_legacy_auto_language_to_japanese(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"transcriptionLanguage": "auto"},
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["transcriptionLanguage"] == "ja"


def test_job_creation_rejects_non_japanese_transcription_language(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"transcriptionLanguage": "en"},
        },
    )

    assert response.status_code == 422


def test_stale_running_job_is_marked_failed_on_status_poll(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"workerHeartbeatTimeoutSeconds": 60},
        },
    ).json()

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        job.status = "generating_candidates"
        job.progress = 50
        job.current_step = "Generating clip candidates"
        job.updated_at = utc_now() - timedelta(seconds=120)
        db.commit()

    response = client.get(f"/api/jobs/{created['jobId']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "worker_terminated_unexpectedly"
    assert "Previous status: generating_candidates" in payload["error"]["message"]


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
    normal_metadata_path = job_output_dir / "normal.json"
    normal_subtitle_path = job_output_dir / "normal.ass"
    zip_path = job_output_dir / "download.zip"
    normal_path.write_bytes(b"normal mp4")
    short_path.write_bytes(b"short mp4")
    normal_subtitle_path.write_text("[Script Info]\n", encoding="utf-8")
    normal_metadata_path.write_text(
        json.dumps(
            {
                "title_source": "transcript_fallback",
                "start": 12.5,
                "end": 133.0,
                "original_start": 13.0,
                "original_end": 132.0,
                "refined_start": 12.5,
                "refined_end": 133.0,
                "boundary_refined": True,
                "score": 84.0,
                "subtitle_path": str(normal_subtitle_path),
            }
        ),
        encoding="utf-8",
    )
    zip_path.write_bytes(b"zip bytes")
    (job_output_dir / "audit").mkdir()
    (job_output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [
                    {
                        "id": "cand_normal",
                        "type": "normal",
                        "rule_score": 70.0,
                        "ai_score": 84.0,
                        "final_score": 84.0,
                        "selection_reason": "above_quality_threshold",
                        "below_quality_threshold": False,
                        "quality_warning": None,
                        "openai_score_source": "finalist_on_demand",
                        "boundary_refined": True,
                    }
                ],
                "shorts": [],
            }
        ),
        encoding="utf-8",
    )
    (job_output_dir / "audit" / "output_audit_report.json").write_text(
        json.dumps(
            {
                "aggregate_summary": {
                    "generated_normal_count": 1,
                    "generated_short_count": 1,
                    "clips_requiring_human_visual_inspection_count": 1,
                    "warnings_by_type": {"normal": {"likely_abrupt_start": 1}},
                },
                "clips": [
                    {
                        "id": "cand_normal",
                        "type": "normal",
                        "resolution": {"width": 1280, "height": 720},
                        "warnings": ["likely_abrupt_start"],
                        "final_score": 84.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with next(app.dependency_overrides[get_db]()) as db:
        video = db.get(Video, upload["videoId"])
        assert video is not None
        db.add_all(
            [
                ExportItem(
                    id="exp_normal",
                    job_id=created["jobId"],
                    video_id=video.id,
                    candidate_id="cand_normal",
                    type="normal",
                    title="Normal Clip",
                    duration=120.5,
                    score=84.0,
                    video_path=str(normal_path),
                    subtitle_path=str(normal_subtitle_path),
                    metadata_path=str(normal_metadata_path),
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
    assert results["auditSummary"]["warningCounts"]["likely_abrupt_start"] == 1
    assert results["normalClips"][0]["downloadUrl"] == "/api/exports/exp_normal/download"
    assert results["normalClips"][0]["candidateId"] == "cand_normal"
    assert results["normalClips"][0]["titleSource"] == "transcript_fallback"
    assert results["normalClips"][0]["finalScore"] == 84.0
    assert results["normalClips"][0]["ruleScore"] == 70.0
    assert results["normalClips"][0]["aiScore"] == 84.0
    assert results["normalClips"][0]["selectionReason"] == "above_quality_threshold"
    assert results["normalClips"][0]["openaiScoreSource"] == "finalist_on_demand"
    assert results["normalClips"][0]["boundaryRefined"] is True
    assert results["normalClips"][0]["resolution"] == {"width": 1280, "height": 720}
    assert results["normalClips"][0]["auditWarnings"] == ["likely_abrupt_start"]
    assert results["normalClips"][0]["subtitleUrl"] == "/api/exports/exp_normal/subtitle"
    assert results["normalClips"][0]["metadataUrl"] == "/api/exports/exp_normal/metadata"
    assert results["shorts"][0]["videoUrl"] == "/api/exports/exp_short/download"

    zip_response = client.get(f"/api/jobs/{created['jobId']}/download.zip")
    assert zip_response.status_code == 200
    assert zip_response.content == b"zip bytes"

    normal_download = client.get("/api/exports/exp_normal/download")
    assert normal_download.status_code == 200
    assert normal_download.content == b"normal mp4"

    metadata_download = client.get("/api/exports/exp_normal/metadata")
    assert metadata_download.status_code == 200
    assert metadata_download.json()["boundary_refined"] is True

    subtitle_download = client.get("/api/exports/exp_normal/subtitle")
    assert subtitle_download.status_code == 200
    assert b"Script Info" in subtitle_download.content

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
