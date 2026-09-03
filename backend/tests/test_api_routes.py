from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.api.jobs as jobs_api
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.jobs.queue import (
    get_enqueue_job,
    get_enqueue_render_job,
    get_enqueue_retry_job,
    get_enqueue_subtitle_review_hook_scene_update,
    get_enqueue_subtitle_review_preview,
)
from app.jobs.publication_state import (
    mark_rerender_publication_unresolved,
    rerender_publication_is_unresolved,
)
from app.jobs.clip_plan import (
    build_clip_plan,
    clip_plan_output_path,
    mark_clip_plan_awaiting_review,
    write_clip_plan,
)
from app.jobs.runner import (
    AutoClipperPipelineDependencies,
    run_dummy_autoclipper_job,
    run_subtitle_review_render,
)
from app.jobs.status import SUCCESS_STATUSES
from app.jobs.subtitle_review import subtitle_review_preview_path
from app.main import app
from app.models import AppPreference, ExportItem, Job, Video, utc_now
from app.jobs.subtitle_review_preview import write_subtitle_review_preview_error
from app.render.render_short import (
    DEFAULT_SHORT_BOTTOM_BANNER_PATH,
    DEFAULT_SHORT_TOP_BANNER_PATH,
)
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

    def override_get_enqueue_retry_job() -> None:
        return lambda job_id, terminal_retry_allowed: None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = override_get_storage_paths
    app.dependency_overrides[get_enqueue_job] = override_get_enqueue_job
    app.dependency_overrides[get_enqueue_retry_job] = override_get_enqueue_retry_job
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: lambda job_id, clip_id, spec_hash: None

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
            "heatmap": ([{"start_time": 10.0, "end_time": 15.0, "value": 0.8}] if available else []),
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
        stored_sidecar = app.dependency_overrides[get_storage_paths]().video_heatmap(video.id)
    payload = json.loads(stored_sidecar.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["media"]["filename"] == "sample.mp4"
    assert payload["heatmap"][0]["value"] == 0.8


def test_clip_plan_converts_only_selected_short_to_normal(client: TestClient) -> None:
    job_id = "job_clip_type_update"
    video_id = "vid_clip_type_update"
    first_short = Candidate(
        id="candidate_short_1",
        type="short",
        start=10,
        end=40,
        duration=30,
        transcript_text="一つ目のショート",
        title="一つ目",
        hook_text="一つ目のフック",
        hook_duration_seconds=2,
        hook_scene_start=12,
        hook_scene_end=14,
        boundary_refined=False,
    )
    converted_short = Candidate(
        id="candidate_short_2",
        type="short",
        start=50,
        end=80,
        duration=30,
        transcript_text="通常へ変更するショート",
        title="変更対象",
        hook_text="解除されるフック",
        hook_duration_seconds=2,
        hook_scene_start=52,
        hook_scene_end=54,
        boundary_refined=False,
    )
    selection = CandidateSelection(
        normalClips=[],
        shorts=[first_short, converted_short],
        requestedNormalCount=0,
        requestedShortCount=2,
        unfilledRequestedCounts={"normal": 0, "short": 0},
    )
    settings = {
        "normalClipCount": 0,
        "shortCount": 2,
        "requireClipPlanReview": True,
        "requireSubtitleReview": True,
    }
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    source_path = storage.uploads / f"{video_id}.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"source video")
    document = mark_clip_plan_awaiting_review(
        build_clip_plan(
            job_id,
            selection,
            settings,
            source_duration=120,
        ),
        preview_clip_ids=[],
    )
    write_clip_plan(document, clip_plan_output_path(output_dir))
    write_selected_clips(selection, output_dir / "selected_clips.json")
    (output_dir / "transcript_segments.json").write_text(
        json.dumps(
            [
                {"start": 10, "end": 40, "text": "一つ目のショート", "confidence": 0.9},
                {"start": 50, "end": 80, "text": "通常へ変更するショート", "confidence": 0.9},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        video = Video(
            id=video_id,
            original_filename="source.mp4",
            stored_path=str(source_path),
            duration=120,
            width=1920,
            height=1080,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video_id,
            status="awaiting_clip_review",
            progress=65,
            current_step="切り抜き予定を確認してください",
            settings_json=settings,
        )
        db.add_all([video, job])
        db.commit()

    endpoint = f"/api/jobs/{job_id}/clip-plan/clips/{converted_short.id}/type"
    response = client.patch(endpoint, json={"type": "normal"})
    assert response.status_code == 200
    response_plan = response.json()
    response_item = next(clip for clip in response_plan["clips"] if clip["id"] == converted_short.id)
    assert response_item["type"] == "normal"
    assert (response_item["start"], response_item["end"], response_item["title"]) == (
        50.0,
        80.0,
        "変更対象",
    )
    assert response_item["hookSceneStart"] is None
    assert response_item["hookSceneEnd"] is None
    assert response_plan["settings"]["normalClipCount"] == 1
    assert response_plan["settings"]["shortCount"] == 1

    stored_selection = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert [clip["id"] for clip in stored_selection["normalClips"]] == [converted_short.id]
    assert [clip["id"] for clip in stored_selection["shorts"]] == [first_short.id]
    stored_candidate = stored_selection["normalClips"][0]
    assert stored_candidate["type"] == "normal"
    assert stored_candidate["hook_text"] is None
    assert stored_candidate["hook_duration_seconds"] is None
    assert stored_candidate["hook_scene_start"] is None
    assert stored_candidate["hook_scene_end"] is None
    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, job_id)
        assert stored_job is not None
        assert stored_job.settings_json["normalClipCount"] == 1
        assert stored_job.settings_json["shortCount"] == 1

    repeated_response = client.patch(endpoint, json={"type": "normal"})
    assert repeated_response.status_code == 200
    repeated_selection = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert [clip["id"] for clip in repeated_selection["normalClips"]] == [converted_short.id]
    assert [clip["id"] for clip in repeated_selection["shorts"]] == [first_short.id]

    approve_response = client.post(f"/api/jobs/{job_id}/clip-plan/approve")
    assert approve_response.status_code == 200
    review = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    review_types = {clip["id"]: clip["type"] for clip in review["clips"]}
    assert review_types == {
        converted_short.id: "normal",
        first_short.id: "short",
    }
    converted_review = next(clip for clip in review["clips"] if clip["id"] == converted_short.id)
    assert converted_review["hookSceneStart"] is None
    assert converted_review["hookSceneEnd"] is None

    invalid_state_response = client.patch(endpoint, json={"type": "normal"})
    assert invalid_state_response.status_code == 409


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
        sidecar_path = app.dependency_overrides[get_storage_paths]().video_heatmap(video.id)
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
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
            "message": "人気度JSONを参考にするには有効なJSONが必要です。",
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


def test_create_job_keeps_legacy_initial_selection_for_older_clients(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"legacy selection video", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["initialSelectionProvider"] == "legacy"


def test_create_manual_job_forces_legacy_initial_selection(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"manual selection video", "video/mp4")},
    ).json()

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "workflowMode": "manual",
                "normalClipCount": 0,
                "shortCount": 0,
                "initialSelectionProvider": "codex",
            },
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["initialSelectionProvider"] == "legacy"


def test_create_job_persists_codex_initial_selection_and_exposes_summary(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"codex selection video", "video/mp4")},
    ).json()
    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "initialSelectionProvider": "codex",
                "useOpenAIScoring": True,
            },
        },
    )

    assert response.status_code == 201
    job_id = response.json()["jobId"]
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["initialSelectionProvider"] == "codex"
        assert job.settings_json["useOpenAIScoring"] is False
        assert job.settings_json["ensureSelectedOpenAIScored"] is False

    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "codex_initial_selection_summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "fallback_used": False,
                "requested_normal_count": 2,
                "requested_short_count": 3,
                "selected_normal_count": 2,
                "selected_short_count": 3,
                "promptVersion": "codex_initial_selection_v4",
                "requestId": "1" * 32,
                "attemptCount": 1,
                "hostErrorCode": None,
            }
        ),
        encoding="utf-8",
    )

    status_response = client.get(f"/api/jobs/{job_id}")

    assert status_response.status_code == 200
    details = status_response.json()["details"]
    assert details["initialSelectionProvider"] == "codex"
    assert details["codexInitialSelectionStatus"] == "completed"
    assert details["codexInitialSelectionFallbackUsed"] is False
    assert details["codexInitialSelectionRequestedNormalCount"] == 2
    assert details["codexInitialSelectionRequestedShortCount"] == 3
    assert details["codexInitialSelectionSelectedNormalCount"] == 2
    assert details["codexInitialSelectionSelectedShortCount"] == 3
    assert details["codexInitialSelectionPhase"] == "initial"
    assert details["codexInitialSelectionPromptVersion"] == (
        "codex_initial_selection_v4"
    )
    assert details["codexInitialSelectionRequestId"] == "1" * 32
    assert details["codexInitialSelectionAttemptCount"] == 1
    assert details["codexInitialSelectionHostErrorCode"] is None

    (output_dir / "codex_reselection_summary.json").write_text(
        json.dumps(
            {
                "phase": "reselection",
                "status": "fallback",
                "fallbackUsed": True,
                "requestedNormalCount": 2,
                "requestedShortCount": 3,
                "selectedNormalCount": 0,
                "selectedShortCount": 0,
                "promptVersion": "codex_initial_selection_v4",
                "requestId": "2" * 32,
                "attemptCount": 2,
                "hostErrorCode": "response_schema_contract_mismatch",
                "error": {
                    "code": "codex_initial_selection_host_failed",
                    "message": "Codex再選定を実行できませんでした。",
                },
            }
        ),
        encoding="utf-8",
    )

    latest_details = client.get(f"/api/jobs/{job_id}").json()["details"]
    assert latest_details["codexInitialSelectionPhase"] == "reselection"
    assert latest_details["codexInitialSelectionStatus"] == "fallback"
    assert latest_details["codexInitialSelectionFallbackUsed"] is True
    assert latest_details["codexInitialSelectionRequestId"] == "2" * 32
    assert latest_details["codexInitialSelectionAttemptCount"] == 2
    assert latest_details["codexInitialSelectionHostErrorCode"] == (
        "response_schema_contract_mismatch"
    )
    assert latest_details["codexInitialSelectionErrorCode"] == (
        "codex_initial_selection_host_failed"
    )
    assert latest_details["codexInitialSelectionErrorMessage"] == (
        "Codex再選定を実行できませんでした。"
    )


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


def _write_reeditable_preview_inputs(job_id: str, candidate_id: str) -> None:
    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    (output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [],
                "shorts": [
                    {
                        "id": candidate_id,
                        "type": "short",
                        "start": 0,
                        "end": 10,
                        "duration": 10,
                        "transcript_text": "字幕",
                        "title": "完成したショート",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "transcript_segments.json").write_text(
        json.dumps(
            [{"start": 0, "end": 2, "text": "字幕", "confidence": 0.9}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _seed_reeditable_normal_export(
    *,
    duration: float = 10,
    start: float = 0,
    segments: list[tuple[float, float, str]] | None = None,
) -> tuple[str, str, bytes]:
    job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    review = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    segment_values = segments or [(0, min(2, duration), "字幕")]
    review_segments = [
        {
            "id": f"segment_{index:05d}",
            "index": index,
            "start": start + segment_start,
            "end": start + segment_end,
            "originalText": text,
            "text": text,
            "confidence": 0.9,
            "edited": False,
            "affectedClipIds": [candidate_id],
        }
        for index, (segment_start, segment_end, text) in enumerate(segment_values)
    ]
    review_clip = review["clips"][0]
    review_clip.update(
        {
            "type": "normal",
            "title": "完成した通常動画",
            "originalTitle": "完成した通常動画",
            "start": start,
            "end": start + duration,
            "duration": duration,
            "segmentIds": [segment["id"] for segment in review_segments],
        }
    )
    review["segments"] = review_segments
    (output_dir / "subtitle_review.json").write_text(
        json.dumps(review, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [
                    {
                        "id": candidate_id,
                        "type": "normal",
                        "start": start,
                        "end": start + duration,
                        "duration": duration,
                        "transcript_text": " ".join(item[2] for item in segment_values),
                        "title": "完成した通常動画",
                    }
                ],
                "shorts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "transcript_segments.json").write_text(
        json.dumps(
            [
                {
                    "start": start + segment_start,
                    "end": start + segment_end,
                    "text": text,
                    "confidence": 0.9,
                }
                for segment_start, segment_end, text in segment_values
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        export = db.get(ExportItem, "exp_reedit_upload")
        assert export is not None
        export.type = "normal"
        export.title = "完成した通常動画"
        export.duration = duration
        db.commit()
    return job_id, candidate_id, rendered_bytes


def test_apply_subtitle_review_clip_saves_drafts_confirms_and_queues_once(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append((queued_job_id, clip_id, spec_hash))
    )
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    segment_id = reopened.json()["clips"][0]["segmentIds"][0]
    queued.clear()

    applied = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/apply",
        json={
            "title": "即時確認後のタイトル",
            "hookText": "即時確認後のフック",
            "hookDurationSeconds": 4,
            "titleStyle": None,
            "hookStyle": None,
            "subtitleStyle": None,
            "segments": [
                {
                    "segmentId": segment_id,
                    "text": "OKでまとめて保存した字幕",
                }
            ],
        },
    )

    assert applied.status_code == 200
    payload = applied.json()
    clip = payload["clips"][0]
    assert clip["title"] == "即時確認後のタイトル"
    assert clip["hookText"] == "即時確認後のフック"
    assert clip["hookDurationSeconds"] == 4
    assert clip["confirmed"] is True
    assert clip["previewState"] == "queued"
    assert payload["confirmedClipCount"] == 1
    assert payload["segments"][0]["text"] == "OKでまとめて保存した字幕"
    assert len(queued) == 1
    assert queued[0][0:2] == (job_id, candidate_id)

    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    persisted = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    assert persisted["clips"][0]["confirmed"] is True
    assert persisted["segments"][0]["text"] == "OKでまとめて保存した字幕"


def test_apply_subtitle_review_clip_accepts_empty_overlay_title(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200

    applied = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/apply",
        json={
            "title": "",
            "publicationTitle": "公開用タイトル",
            "hookText": "",
            "hookDurationSeconds": 3,
            "segments": [],
        },
    )

    assert applied.status_code == 200
    clip = applied.json()["clips"][0]
    assert clip["title"] == ""
    assert clip["publicationTitle"].startswith("公開用タイトル")
    assert clip["overlayTitleExpected"] is False
    assert clip["confirmed"] is True


@pytest.mark.parametrize("action", ["apply", "confirm"])
def test_auto_clip_acceptance_queues_render_without_confirming_auto_passed_sibling(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    review_path = output_dir / "subtitle_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    sibling = dict(review["clips"][0])
    sibling.update(
        {
            "id": "auto_passed_sibling",
            "title": "自動判定済み",
            "originalTitle": "自動判定済み",
            "segmentIds": [],
            "confirmed": False,
        }
    )
    review["clips"].append(sibling)
    review["totalClipCount"] = 2
    review["confirmedClipCount"] = 0
    for index, clip in enumerate(review["clips"], start=1):
        clip["previewState"] = "ready"
        clip["previewSpecHash"] = f"{index:064x}"
        clip["previewVideoUrl"] = f"/preview-{clip['id']}.mp4"
    review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {"automationMode": "auto"}
        db.commit()

    monkeypatch.setattr(
        jobs_api,
        "_refresh_subtitle_review_previews_unlocked",
        lambda **kwargs: (kwargs["document"], []),
    )
    monkeypatch.setattr(
        jobs_api,
        "_evaluate_and_write_content_quality_gate",
        lambda **_kwargs: type("PassingDecision", (), {"route": "continue"})(),
    )
    queued: list[tuple[str, int]] = []
    app.dependency_overrides[get_enqueue_render_job] = lambda: (
        lambda queued_job_id, revision: queued.append((queued_job_id, revision))
    )

    if action == "apply":
        response = client.post(
            f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/apply",
            json={
                "title": review["clips"][0]["title"],
                "hookText": "",
                "hookDurationSeconds": 3,
                "segments": [],
            },
        )
    else:
        response = client.post(
            f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/confirm"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "render_queued"
    assert payload["confirmedClipCount"] == 1
    assert payload["totalClipCount"] == 2
    assert next(
        clip for clip in payload["clips"] if clip["id"] == "auto_passed_sibling"
    )["confirmed"] is False
    assert queued == [(job_id, payload["renderRevision"])]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == (
        "rendering_normal_clips"
    )


def test_patch_subtitle_review_clip_framing_persists_and_requeues_preview(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append(
            (queued_job_id, clip_id, spec_hash)
        )
    )
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    baseline_hash = reopened.json()["clips"][0]["previewSpecHash"]
    queued.clear()

    response = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/framing",
        json={
            "framingOffsetX": 25.126,
            "framingOffsetY": -30.874,
            "framingZoom": 1.23456,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    clip = payload["clips"][0]
    assert clip["framingOffsetX"] == 25.13
    assert clip["framingOffsetY"] == -30.87
    assert clip["framingZoom"] == 1.235
    assert clip["confirmed"] is False
    assert clip["previewState"] == "queued"
    assert clip["previewSpecHash"] != baseline_hash
    assert queued == [(job_id, candidate_id, clip["previewSpecHash"])]

    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    persisted = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    assert persisted["clips"][0]["framingOffsetX"] == 25.13
    assert persisted["clips"][0]["framingOffsetY"] == -30.87
    assert persisted["clips"][0]["framingZoom"] == 1.235


def test_apply_subtitle_review_clip_rejects_segment_from_another_clip(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200

    rejected = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/apply",
        json={
            "title": "変更しないタイトル",
            "segments": [{"segmentId": "segment_from_other_clip", "text": "不可"}],
        },
    )

    assert rejected.status_code == 422
    assert rejected.json()["detail"] == ("subtitle segment does not belong to the selected clip")


def test_get_subtitle_review_hydrates_banner_settings_from_job(
    client: TestClient,
) -> None:
    job_id, _candidate_id, _rendered_bytes = _seed_reeditable_export()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": True,
        }
        db.commit()

    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    response = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert response.status_code == 200
    assert response.json()["shortOverlayTitleMode"] == "auto"
    assert response.json()["shortTopBannerEnabled"] is False
    assert response.json()["shortBottomBannerEnabled"] is True
    assert response.json()["clips"][0]["overlayTitleExpected"] is True
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    artifact = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "subtitle_review_summary.json").read_text(encoding="utf-8"))
    assert artifact["shortOverlayTitleMode"] == "auto"
    assert artifact["shortTopBannerEnabled"] is False
    assert artifact["shortBottomBannerEnabled"] is True
    assert artifact["clips"][0]["overlayTitleExpected"] is True
    assert summary["short_overlay_title_mode"] == "auto"
    assert summary["short_top_banner_enabled"] is False
    assert summary["short_bottom_banner_enabled"] is True
    assert summary["overlay_title_expected_by_clip"] == {"candidate_short_reedit": True}


def test_get_subtitle_review_preserves_explicit_never_mode(
    client: TestClient,
) -> None:
    job_id, _candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    artifact_path = storage.job_outputs(job_id) / "subtitle_review.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["shortOverlayTitleMode"] = "auto"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "shortOverlayTitleMode": "never",
        }
        db.commit()

    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    response = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert response.status_code == 200
    assert response.json()["shortOverlayTitleMode"] == "never"
    assert response.json()["clips"][0]["overlayTitleExpected"] is False
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["shortOverlayTitleMode"] == "never"
    assert persisted["clips"][0]["overlayTitleExpected"] is False


def test_get_subtitle_review_persists_missing_false_title_expectation(
    client: TestClient,
) -> None:
    job_id, _candidate_id, _rendered_bytes = _seed_reeditable_export()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            "mode": "low_cost",
            "shortOverlayTitleMode": "auto",
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        }
        db.commit()

    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    response = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert response.status_code == 200
    assert response.json()["clips"][0]["overlayTitleExpected"] is False
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    artifact = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "subtitle_review_summary.json").read_text(encoding="utf-8"))
    assert artifact["clips"][0]["overlayTitleExpected"] is False
    assert summary["overlay_title_expected_by_clip"] == {"candidate_short_reedit": False}


def test_get_subtitle_review_does_not_requeue_failed_current_spec(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    (output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [],
                "shorts": [
                    {
                        "id": candidate_id,
                        "type": "short",
                        "start": 0,
                        "end": 10,
                        "duration": 10,
                        "transcript_text": "字幕",
                        "title": "完成したショート",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "transcript_segments.json").write_text(
        json.dumps(
            [
                {
                    "start": 0,
                    "end": 2,
                    "text": "字幕",
                    "confidence": 0.9,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append((queued_job_id, clip_id, spec_hash))
    )
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200

    first = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert first.status_code == 200
    first_clip = first.json()["clips"][0]
    assert first_clip["previewState"] == "queued"
    spec_hash = first_clip["previewSpecHash"]
    assert queued == [(job_id, candidate_id, spec_hash)]
    write_subtitle_review_preview_error(
        output_dir,
        candidate_id,
        spec_hash,
        "preview failed",
    )

    second = client.get(f"/api/jobs/{job_id}/subtitle-review")
    third = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert second.status_code == 200
    assert second.json()["clips"][0]["previewState"] == "failed"
    assert second.json()["clips"][0]["previewError"] == "preview failed"
    assert third.status_code == 200
    assert third.json()["clips"][0]["previewState"] == "failed"
    assert queued == [(job_id, candidate_id, spec_hash)]


def test_failed_subtitle_review_preview_can_be_retried_once(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(job_id, candidate_id)
    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append((queued_job_id, clip_id, spec_hash))
    )
    first = client.get(f"/api/jobs/{job_id}/subtitle-review")
    assert first.status_code == 200
    spec_hash = first.json()["clips"][0]["previewSpecHash"]
    output_dir = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    error_path = write_subtitle_review_preview_error(
        output_dir,
        candidate_id,
        spec_hash,
        "preview failed",
    )
    failed = client.get(f"/api/jobs/{job_id}/subtitle-review")
    assert failed.json()["clips"][0]["previewState"] == "failed"
    queued.clear()

    retried = client.post((f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/preview/retry"))
    duplicate = client.post((f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/preview/retry"))

    assert retried.status_code == 200
    assert retried.json()["clips"][0]["previewState"] == "queued"
    assert retried.json()["clips"][0]["previewError"] is None
    assert duplicate.status_code == 200
    assert duplicate.json()["clips"][0]["previewState"] == "queued"
    assert queued == [(job_id, candidate_id, spec_hash)]
    assert not error_path.exists()


def test_completed_subtitle_review_get_preserves_confirmation_without_preview_queue(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    artifact_path = storage.job_outputs(job_id) / "subtitle_review.json"
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append((queued_job_id, clip_id, spec_hash))
    )

    response = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "completed"
    assert payload["confirmedClipCount"] == 1
    assert payload["clips"][0]["id"] == candidate_id
    assert payload["clips"][0]["confirmed"] is True
    assert payload["clips"][0]["previewSpecHash"] is None
    assert queued == []
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "completed"
    assert persisted["confirmedClipCount"] == 1
    assert persisted["clips"][0]["confirmed"] is True
    assert persisted["clips"][0].get("previewSpecHash") is None


def test_completed_legacy_preview_is_transiently_playable_until_reopen(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    artifact_path = output_dir / "subtitle_review.json"
    legacy_preview = subtitle_review_preview_path(output_dir, candidate_id)
    legacy_preview.parent.mkdir(parents=True, exist_ok=True)
    legacy_preview.write_bytes(b"legacy preview")
    stored_before = artifact_path.read_bytes()
    queued: list[tuple[str, str, str]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: (
        lambda queued_job_id, clip_id, spec_hash: queued.append((queued_job_id, clip_id, spec_hash))
    )

    completed = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert completed.status_code == 200
    completed_clip = completed.json()["clips"][0]
    assert completed_clip["confirmed"] is True
    assert completed_clip["previewState"] == "ready"
    assert completed_clip["previewSpecHash"] is None
    assert completed_clip["previewVideoUrl"]
    legacy_response = client.get(completed_clip["previewVideoUrl"])
    assert legacy_response.status_code == 200
    assert legacy_response.content == b"legacy preview"
    assert artifact_path.read_bytes() == stored_before
    assert queued == []

    _write_reeditable_preview_inputs(job_id, candidate_id)
    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    active = client.get(f"/api/jobs/{job_id}/subtitle-review")
    active_clip = active.json()["clips"][0]
    assert active_clip["previewState"] == "queued"
    assert active_clip["previewSpecHash"] is not None
    assert active_clip["previewVideoUrl"] is None
    assert queued == [(job_id, candidate_id, active_clip["previewSpecHash"])]


def test_subtitle_review_get_poll_cannot_overwrite_concurrent_content_patch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    refresh_entered = Event()
    release_refresh = Event()
    original_refresh = jobs_api.refresh_subtitle_review_preview_states
    first_refresh = True

    def blocking_refresh(*args: object, **kwargs: object) -> object:
        nonlocal first_refresh
        should_block = first_refresh
        first_refresh = False
        if should_block:
            refresh_entered.set()
            assert release_refresh.wait(timeout=3)
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(
        jobs_api,
        "refresh_subtitle_review_preview_states",
        blocking_refresh,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        poll_future = executor.submit(
            client.get,
            f"/api/jobs/{job_id}/subtitle-review",
        )
        assert refresh_entered.wait(timeout=3)
        patch_future = executor.submit(
            client.patch,
            f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
            json={
                "title": "並行更新後のタイトル",
                "hookText": "",
                "hookDurationSeconds": 3,
            },
        )
        assert not patch_future.done()
        release_refresh.set()
        assert poll_future.result(timeout=3).status_code == 200
        patch_response = patch_future.result(timeout=3)

    assert patch_response.status_code == 200
    persisted = json.loads(
        (app.dependency_overrides[get_storage_paths]().job_outputs(job_id) / "subtitle_review.json").read_text(encoding="utf-8")
    )
    clip = next(item for item in persisted["clips"] if item["id"] == candidate_id)
    assert clip["title"] == "並行更新後のタイトル"


def test_hook_scene_status_transition_blocks_concurrent_settings_patch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: lambda job_id, clip_id, start, end: None
    validation_entered = Event()
    release_validation = Event()
    original_update = jobs_api.update_review_hook_scene

    def blocking_update(*args: object, **kwargs: object) -> object:
        validation_entered.set()
        assert release_validation.wait(timeout=3)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(jobs_api, "update_review_hook_scene", blocking_update)

    with ThreadPoolExecutor(max_workers=2) as executor:
        hook_future = executor.submit(
            client.patch,
            (f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/hook-scene"),
            json={"start": 1, "end": 3},
        )
        assert validation_entered.wait(timeout=3)
        settings_future = executor.submit(
            client.patch,
            f"/api/jobs/{job_id}/subtitle-review/settings",
            json={
                "shortTopBannerEnabled": True,
                "shortBottomBannerEnabled": True,
            },
        )
        assert not settings_future.done()
        release_validation.set()
        hook_response = hook_future.result(timeout=3)
        settings_response = settings_future.result(timeout=3)

    assert hook_response.status_code == 202
    assert settings_response.status_code == 409
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.status == "preparing_subtitle_review"
        assert job.settings_json.get("shortTopBannerEnabled") is not True


@pytest.mark.parametrize("poll_target", ["review", "preview-video"])
def test_subtitle_review_poll_refreshes_job_status_after_waiting_for_hook_lock(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    poll_target: str,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: lambda job_id, clip_id, start, end: None
    poll_waiting = Event()
    release_poll = Event()
    original_lock = jobs_api.subtitle_review_document_lock
    delay_first_lock = True

    @contextmanager
    def delayed_first_lock(*args: object, **kwargs: object) -> Generator[None, None, None]:
        nonlocal delay_first_lock
        should_delay = delay_first_lock
        delay_first_lock = False
        if should_delay:
            poll_waiting.set()
            assert release_poll.wait(timeout=3)
        with original_lock(*args, **kwargs):
            yield

    monkeypatch.setattr(jobs_api, "subtitle_review_document_lock", delayed_first_lock)
    poll_path = (
        f"/api/jobs/{job_id}/subtitle-review"
        if poll_target == "review"
        else (f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/preview-video")
    )
    artifact_path = app.dependency_overrides[get_storage_paths]().job_outputs(job_id) / "subtitle_review.json"

    with ThreadPoolExecutor(max_workers=1) as executor:
        poll_future = executor.submit(client.get, poll_path)
        assert poll_waiting.wait(timeout=3)
        try:
            hook_response = client.patch(
                (f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/hook-scene"),
                json={"start": 1, "end": 3},
            )
            stored_after_hook_snapshot = artifact_path.read_bytes()
        finally:
            release_poll.set()
        poll_response = poll_future.result(timeout=3)

    assert hook_response.status_code == 202
    assert poll_response.status_code == (200 if poll_target == "review" else 409)
    assert artifact_path.read_bytes() == stored_after_hook_snapshot


@pytest.mark.parametrize(
    ("position", "asset_path"),
    [
        ("top", DEFAULT_SHORT_TOP_BANNER_PATH),
        ("bottom", DEFAULT_SHORT_BOTTOM_BANNER_PATH),
    ],
)
def test_subtitle_review_banner_asset_matches_renderer_asset(
    client: TestClient,
    position: str,
    asset_path: Path,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()

    response = client.get(f"/api/jobs/{created['jobId']}/subtitle-review/banner-assets/{position}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "content-disposition" not in response.headers
    assert response.content == asset_path.read_bytes()


def test_subtitle_review_banner_asset_rejects_invalid_or_missing_asset(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    base_url = f"/api/jobs/{created['jobId']}/subtitle-review/banner-assets"

    invalid = client.get(f"{base_url}/center")
    missing_job = client.get("/api/jobs/job_missing/subtitle-review/banner-assets/top")
    monkeypatch.setattr(
        "app.api.jobs.DEFAULT_SHORT_TOP_BANNER_PATH",
        tmp_path / "missing.png",
    )
    missing_asset = client.get(f"{base_url}/top")

    assert invalid.status_code == 422
    assert missing_job.status_code == 404
    assert missing_asset.status_code == 404
    assert missing_asset.json()["detail"] == "short top banner asset not found"


def test_completed_mp4_upload_reopens_matching_job_without_saving_copy(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    upload_files_before = set(storage.uploads.iterdir())

    response = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("renamed-finished.mp4", rendered_bytes, "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    job_id = payload["jobId"]
    assert job_id != source_job_id
    assert payload == {
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
    assert review["reeditSourceJobId"] == source_job_id
    assert review["reeditSourceClipId"] == candidate_id
    assert len(review["clips"]) == 1
    assert review["confirmedClipCount"] == 0
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "awaiting_subtitle_review"

    assert client.get(f"/api/jobs/{source_job_id}").json()["status"] == "completed"

    repeated = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished-again.mp4", rendered_bytes, "video/mp4")},
    )
    assert repeated.status_code == 200
    assert repeated.json()["jobId"] not in {job_id, source_job_id}

    queued_hook_updates: list[tuple[str, str, float | None, float | None]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: (
        lambda queued_job_id, clip_id, start, end: queued_hook_updates.append((queued_job_id, clip_id, start, end))
    )
    hook_response = client.patch(
        (f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/hook-scene"),
        json={"start": 2, "end": 4},
    )

    assert hook_response.status_code == 202
    assert hook_response.json()["status"] == "preparing_subtitle_review"
    assert queued_hook_updates == [(job_id, candidate_id, 2.0, 4.0)]


def test_completed_mp4_upload_creates_one_clip_child_from_legacy_open_review(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    _write_reeditable_preview_inputs(source_job_id, candidate_id)

    reopened = client.post(f"/api/jobs/{source_job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "awaiting_review"

    storage = app.dependency_overrides[get_storage_paths]()
    source_review_path = storage.job_outputs(source_job_id) / "subtitle_review.json"
    source_review_before = source_review_path.read_bytes()
    with next(app.dependency_overrides[get_db]()) as db:
        source_before = db.get(Job, source_job_id)
        assert source_before is not None
        source_settings_before = dict(source_before.settings_json)

    response = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("legacy-finished.mp4", rendered_bytes, "video/mp4")},
    )

    assert response.status_code == 200
    child_job_id = response.json()["jobId"]
    assert child_job_id != source_job_id
    child_review = client.get(f"/api/jobs/{child_job_id}/subtitle-review").json()
    assert child_review["state"] == "awaiting_review"
    assert [clip["id"] for clip in child_review["clips"]] == [candidate_id]
    assert child_review["reeditSourceJobId"] == source_job_id
    assert child_review["reeditSourceClipId"] == candidate_id

    assert client.get(f"/api/jobs/{source_job_id}").json()["status"] == (
        "awaiting_subtitle_review"
    )
    assert source_review_path.read_bytes() == source_review_before
    with next(app.dependency_overrides[get_db]()) as db:
        source_after = db.get(Job, source_job_id)
        assert source_after is not None
        assert source_after.settings_json == source_settings_before


def test_completed_mp4_upload_rejects_initial_review_without_reopen_marker(
    client: TestClient,
) -> None:
    source_job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    source_review_path = storage.job_outputs(source_job_id) / "subtitle_review.json"
    source_review = json.loads(source_review_path.read_text(encoding="utf-8"))
    source_review.update(
        {
            "state": "awaiting_review",
            "renderRevision": 1,
            "reopenedAt": None,
        }
    )
    source_review_path.write_text(
        json.dumps(source_review, ensure_ascii=False),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        source = db.get(Job, source_job_id)
        assert source is not None
        source.status = "awaiting_subtitle_review"
        db.commit()

    response = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("initial-review.mp4", rendered_bytes, "video/mp4")},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reedit_source_unavailable"


def test_completed_mp4_upload_rejects_match_with_missing_source_artifact(
    client: TestClient,
) -> None:
    source_job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    (storage.job_outputs(source_job_id) / "subtitle_review.json").unlink()

    response = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("missing-source.mp4", rendered_bytes, "video/mp4")},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "reedit_source_unavailable"
    assert "保存データが不足" in detail["message"]


def test_clip_reedit_creates_one_clip_child_and_keeps_source_job_completed(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export()
    storage = app.dependency_overrides[get_storage_paths]()
    source_output_dir = storage.job_outputs(source_job_id)
    selected = json.loads((source_output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected["shorts"].append(
        {
            "id": "other_short",
            "type": "short",
            "start": 0,
            "end": 5,
            "duration": 5,
            "transcript_text": "別clip",
            "title": "別ショート",
        }
    )
    (source_output_dir / "selected_clips.json").write_text(
        json.dumps(selected, ensure_ascii=False),
        encoding="utf-8",
    )
    source_review = json.loads(
        (source_output_dir / "subtitle_review.json").read_text(encoding="utf-8")
    )
    other_clip = dict(source_review["clips"][0])
    other_clip.update(
        {
            "id": "other_short",
            "type": "short",
            "title": "別ショート",
            "originalTitle": "別ショート",
            "end": 5,
            "duration": 5,
        }
    )
    source_review["clips"].append(other_clip)
    source_review["totalClipCount"] = 2
    source_review["confirmedClipCount"] = 2
    source_review["segments"][0]["affectedClipIds"].append("other_short")
    (source_output_dir / "subtitle_review.json").write_text(
        json.dumps(source_review, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.post(
        f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit"
    )

    assert response.status_code == 201
    child_review = response.json()
    assert child_review["jobId"] != source_job_id
    assert child_review["renderRevision"] == 2
    assert [clip["id"] for clip in child_review["clips"]] == [candidate_id]
    assert child_review["reeditSourceJobId"] == source_job_id
    assert client.get(f"/api/jobs/{source_job_id}").json()["status"] == "completed"
    assert client.get(f"/api/jobs/{child_review['jobId']}").json()["status"] == (
        "awaiting_subtitle_review"
    )
    child_results = client.get(f"/api/jobs/{child_review['jobId']}/results")
    assert child_results.status_code == 200
    assert child_results.json()["reeditSourceJobId"] == source_job_id


def test_isolated_normal_reedit_can_convert_to_one_short(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export()
    reedit = client.post(
        f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit"
    )
    assert reedit.status_code == 201
    child_job_id = reedit.json()["jobId"]

    converted = client.post(
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
        json={},
    )

    assert converted.status_code == 200
    assert converted.json()["clips"][0]["type"] == "short"
    storage = app.dependency_overrides[get_storage_paths]()
    selection = json.loads(
        (storage.job_outputs(child_job_id) / "selected_clips.json").read_text(
            encoding="utf-8"
        )
    )
    assert selection["normalClips"] == []
    assert [clip["id"] for clip in selection["shorts"]] == [candidate_id]
    summary = json.loads(
        (storage.job_outputs(child_job_id) / "candidate_generation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["normal_candidate_count"] == 0
    assert summary["short_candidate_count"] == 1
    assert summary["candidates_kept_by_type"] == {"normal": 0, "short": 1}
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        source = db.get(Job, source_job_id)
        assert child is not None
        assert source is not None
        assert child.settings_json["normalClipCount"] == 0
        assert child.settings_json["shortCount"] == 1
        assert child.settings_json["automationMode"] == "manual"
        assert child.settings_json["initialSelectionProvider"] == "legacy"
        assert source.status == "completed"


def test_isolated_normal_reedit_rejects_short_conversion_over_limit(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export(
        duration=80
    )
    reedit = client.post(
        f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit"
    )
    child_job_id = reedit.json()["jobId"]

    converted = client.post(
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
        json={},
    )

    assert converted.status_code == 422
    assert "75 seconds" in converted.json()["detail"]
    review = client.get(f"/api/jobs/{child_job_id}/subtitle-review").json()
    assert review["clips"][0]["type"] == "normal"


def test_isolated_normal_reedit_converts_relative_range_and_preserves_saved_content(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export(
        duration=100,
        start=120,
        segments=[
            (5, 7, "範囲外の前字幕"),
            (30, 33, "修正前字幕"),
            (90, 92, "範囲外の後字幕"),
        ],
    )
    storage = app.dependency_overrides[get_storage_paths]()
    source_output_dir = storage.job_outputs(source_job_id)
    source_review = json.loads(
        (source_output_dir / "subtitle_review.json").read_text(encoding="utf-8")
    )
    source_clip = source_review["clips"][0]
    title_style = {
        "fontPreset": "heavy",
        "fontSize": 96,
        "primaryColor": "#FFF200",
        "outlineColor": "#000000",
        "outlineWidth": 5,
        "xPercent": 95,
        "yPercent": 5,
        "positionMode": "explicit",
    }
    hook_style = {
        **title_style,
        "fontPreset": "chikara",
        "fontSize": 88,
        "yPercent": 20,
    }
    subtitle_style = {
        **title_style,
        "fontPreset": "noto_black",
        "fontSize": 72,
        "yPercent": 80,
    }
    source_clip.update(
        {
            "title": "保存済みタイトル",
            "publicationTitle": "保存済み公開タイトル",
            "titleEdited": True,
            "hookText": "保存済みフック",
            "hookSceneStart": 125,
            "hookSceneEnd": 127,
            "titleStyle": title_style,
            "hookStyle": hook_style,
            "subtitleStyle": subtitle_style,
        }
    )
    source_review["segments"][1].update(
        {"text": "保存済み修正字幕", "edited": True}
    )
    (source_output_dir / "subtitle_review.json").write_text(
        json.dumps(source_review, ensure_ascii=False),
        encoding="utf-8",
    )

    reedit = client.post(f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit")
    assert reedit.status_code == 201
    child_job_id = reedit.json()["jobId"]
    assert reedit.json()["renderRevision"] == 2
    assert reedit.json()["segments"][1]["text"] == "保存済み修正字幕"

    converted = client.post(
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
        json={"startSeconds": 20, "endSeconds": 70},
    )

    assert converted.status_code == 200
    payload = converted.json()
    clip = payload["clips"][0]
    assert (clip["start"], clip["end"], clip["duration"]) == (140.0, 190.0, 50.0)
    assert clip["segmentIds"] == ["segment_00001"]
    assert [segment["text"] for segment in payload["segments"]] == ["保存済み修正字幕"]
    assert clip["title"] == "保存済みタイトル"
    assert clip["publicationTitle"] == "保存済み公開タイトル"
    assert clip["hookText"] == "保存済みフック"
    assert clip["hookSceneStart"] is None
    assert clip["hookSceneEnd"] is None
    assert {key: clip["titleStyle"][key] for key in title_style} == title_style
    assert {key: clip["hookStyle"][key] for key in hook_style} == hook_style
    assert {key: clip["subtitleStyle"][key] for key in subtitle_style} == subtitle_style
    assert (clip["previewWidth"], clip["previewHeight"]) == (1080, 1920)
    assert clip["resolvedTitleStyle"]["xPercent"] == 95.0
    assert clip["resolvedTitleStyle"]["yPercent"] == 5.0

    child_output_dir = storage.job_outputs(child_job_id)
    selection = json.loads(
        (child_output_dir / "selected_clips.json").read_text(encoding="utf-8")
    )
    short = selection["shorts"][0]
    assert (short["start"], short["end"], short["duration"]) == (140.0, 190.0, 50.0)
    assert (short["segment_start_index"], short["segment_end_index"]) == (1, 1)
    assert short["transcript_text"] == "保存済み修正字幕"
    assert {key: short["title_style"][key] for key in title_style} == title_style
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        assert child is not None
        assert child.settings_json["shortClipTimeRanges"] == [
            {"startSeconds": 140.0, "endSeconds": 190.0}
        ]

    unchanged_source = json.loads(
        (source_output_dir / "subtitle_review.json").read_text(encoding="utf-8")
    )
    assert unchanged_source["clips"][0]["type"] == "normal"
    assert (unchanged_source["clips"][0]["start"], unchanged_source["clips"][0]["end"]) == (
        120,
        220,
    )


def test_isolated_normal_reedit_rejects_partial_short_range(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export(
        duration=100
    )
    reedit = client.post(f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit")
    child_job_id = reedit.json()["jobId"]

    converted = client.post(
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
        json={"startSeconds": 10},
    )

    assert converted.status_code == 422
    review = client.get(f"/api/jobs/{child_job_id}/subtitle-review").json()
    assert review["clips"][0]["type"] == "normal"


def test_isolated_normal_reedit_counts_retained_hook_against_short_limit(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export(
        duration=74
    )
    storage = app.dependency_overrides[get_storage_paths]()
    source_review_path = storage.job_outputs(source_job_id) / "subtitle_review.json"
    source_review = json.loads(source_review_path.read_text(encoding="utf-8"))
    source_review["clips"][0].update(
        {"hookSceneStart": 1, "hookSceneEnd": 3}
    )
    source_review_path.write_text(
        json.dumps(source_review, ensure_ascii=False),
        encoding="utf-8",
    )
    reedit = client.post(f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit")
    child_job_id = reedit.json()["jobId"]
    endpoint = (
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short"
    )

    omitted = client.post(endpoint, json={})
    assert omitted.status_code == 422
    assert "startSeconds and endSeconds are required" in omitted.json()["detail"]

    converted = client.post(
        endpoint,
        json={"startSeconds": 0, "endSeconds": 72},
    )
    assert converted.status_code == 200
    assert converted.json()["clips"][0]["hookSceneStart"] == 1.0
    assert converted.json()["clips"][0]["hookSceneEnd"] == 3.0


def test_isolated_normal_reedit_conversion_rolls_back_artifacts_and_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export()
    reedit = client.post(f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit")
    child_job_id = reedit.json()["jobId"]
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(child_job_id)
    artifact_paths = [
        output_dir / filename
        for filename in jobs_api._SHORT_CONVERSION_ARTIFACT_FILENAMES
    ]
    before_artifacts = {
        path: path.read_bytes() if path.is_file() else None for path in artifact_paths
    }
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        assert child is not None
        before_settings = dict(child.settings_json or {})

    def fail_review_write(_document: object, _paths: object) -> None:
        raise RuntimeError("intentional conversion write failure")

    monkeypatch.setattr(jobs_api, "_write_subtitle_review_unlocked", fail_review_write)
    with pytest.raises(RuntimeError, match="intentional conversion write failure"):
        client.post(
            f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
            json={},
        )

    after_artifacts = {
        path: path.read_bytes() if path.is_file() else None for path in artifact_paths
    }
    assert after_artifacts == before_artifacts
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        source = db.get(Job, source_job_id)
        assert child is not None
        assert source is not None
        assert child.settings_json == before_settings
        assert child.status == "awaiting_subtitle_review"
        assert source.status == "completed"


def test_converted_child_render_failure_returns_to_subtitle_review_without_exports(
    client: TestClient,
) -> None:
    source_job_id, candidate_id, _rendered_bytes = _seed_reeditable_normal_export()
    reedit = client.post(f"/api/jobs/{source_job_id}/clips/{candidate_id}/reedit")
    child_job_id = reedit.json()["jobId"]
    converted = client.post(
        f"/api/jobs/{child_job_id}/subtitle-review/clips/{candidate_id}/convert-to-short",
        json={},
    )
    assert converted.status_code == 200
    assert converted.json()["renderRevision"] == 2

    storage = app.dependency_overrides[get_storage_paths]()
    review_path = storage.job_outputs(child_job_id) / "subtitle_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["state"] = "render_queued"
    review["clips"][0]["confirmed"] = True
    review["confirmedClipCount"] = 1
    review_path.write_text(
        json.dumps(review, ensure_ascii=False),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        assert child is not None
        child.status = "rendering_normal_clips"
        db.commit()
        assert db.scalars(select(ExportItem).where(ExportItem.job_id == child_job_id)).all() == []

    def failing_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: object,
    ) -> Path:
        raise RuntimeError("intentional child render failure")

    statuses = run_subtitle_review_render(
        child_job_id,
        render_revision=2,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            normal_renderer=failing_render,
            short_renderer=failing_render,
        ),
    )

    assert statuses == ["rendering_normal_clips", "rendering_shorts"]
    restored = client.get(f"/api/jobs/{child_job_id}/subtitle-review").json()
    assert restored["state"] == "awaiting_review"
    assert restored["renderRevision"] == 2
    with next(app.dependency_overrides[get_db]()) as db:
        child = db.get(Job, child_job_id)
        source = db.get(Job, source_job_id)
        assert child is not None
        assert source is not None
        assert child.status == "awaiting_subtitle_review"
        assert child.error_code == "no_usable_output"
        assert source.status == "completed"
        assert db.scalars(select(ExportItem).where(ExportItem.job_id == child_job_id)).all() == []


def test_subtitle_review_banner_settings_are_strict_and_persisted(
    client: TestClient,
) -> None:
    job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    job_id = reopened.json()["jobId"]
    review = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    assert review["shortLayout"] == "auto"
    assert review["shortTopBannerEnabled"] is False
    assert review["shortBottomBannerEnabled"] is False
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": "auto",
        }
        db.commit()

    extra_field = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": False,
            "mode": "low_cost",
        },
    )
    string_bool = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": "true",
            "shortBottomBannerEnabled": False,
        },
    )
    invalid_layout = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortLayout": "person_zoom",
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        },
    )
    assert extra_field.status_code == 422
    assert string_bool.status_code == 422
    assert invalid_layout.status_code == 422

    bottom_only = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortLayout": "face_tracking_crop",
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": True,
        },
    )
    assert bottom_only.status_code == 200
    assert bottom_only.json()["shortLayout"] == "face_tracking_crop"
    assert bottom_only.json()["shortOverlayTitleMode"] == "auto"
    assert bottom_only.json()["clips"][0]["overlayTitleExpected"] is False
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortLayout"] == "face_tracking_crop"
        assert job.settings_json["shortOverlayTitleMode"] == "auto"

    response = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["shortOverlayTitleMode"] == "auto"
    assert response.json()["shortTopBannerEnabled"] is True
    assert response.json()["shortBottomBannerEnabled"] is False
    assert response.json()["clips"][0]["overlayTitleExpected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortTopBannerEnabled"] is True
        assert job.settings_json["shortBottomBannerEnabled"] is False
        assert job.settings_json["shortOverlayTitleMode"] == "auto"

    disabled = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": True,
        },
    )
    assert disabled.status_code == 200
    assert disabled.json()["shortOverlayTitleMode"] == "always"
    assert disabled.json()["clips"][0]["overlayTitleExpected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortOverlayTitleMode"] == "always"
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    artifact = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "subtitle_review_summary.json").read_text(encoding="utf-8"))
    assert artifact["shortOverlayTitleMode"] == "always"
    assert artifact["shortLayout"] == "face_tracking_crop"
    assert artifact["shortTopBannerEnabled"] is False
    assert artifact["shortBottomBannerEnabled"] is True
    assert artifact["clips"][0]["overlayTitleExpected"] is True
    assert summary["short_overlay_title_mode"] == "always"
    assert summary["short_layout"] == "face_tracking_crop"
    assert summary["short_top_banner_enabled"] is False
    assert summary["short_bottom_banner_enabled"] is True
    assert summary["overlay_title_expected_by_clip"] == {"candidate_short_reedit": True}


def test_subtitle_review_top_off_preserves_title_and_bottom_only_preserves_never(
    client: TestClient,
) -> None:
    job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    job_id = reopened.json()["jobId"]
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": "never",
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        }
        db.commit()

    bottom_only = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": True,
        },
    )
    assert bottom_only.status_code == 200
    assert bottom_only.json()["shortOverlayTitleMode"] == "never"
    assert bottom_only.json()["clips"][0]["overlayTitleExpected"] is False

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": "never",
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": True,
        }
        db.commit()

    legacy_top_off = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": True,
        },
    )
    assert legacy_top_off.status_code == 200
    assert legacy_top_off.json()["shortOverlayTitleMode"] == "always"
    assert legacy_top_off.json()["shortTopBannerEnabled"] is False
    assert legacy_top_off.json()["clips"][0]["overlayTitleExpected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortOverlayTitleMode"] == "always"


@pytest.mark.parametrize(
    "title_mode",
    ["auto", "high_quality_only", "always"],
)
def test_subtitle_review_top_off_forces_title_mode_always(
    client: TestClient,
    title_mode: str,
) -> None:
    job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    job_id = reopened.json()["jobId"]
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": title_mode,
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": False,
        }
        db.commit()

    response = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["shortOverlayTitleMode"] == "always"
    assert response.json()["clips"][0]["overlayTitleExpected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortOverlayTitleMode"] == "always"


@pytest.mark.parametrize(
    "title_mode",
    ["auto", "high_quality_only", "never", "always"],
)
def test_subtitle_review_top_on_preserves_existing_title_mode(
    client: TestClient,
    title_mode: str,
) -> None:
    job_id, _candidate_id, rendered_bytes = _seed_reeditable_export()
    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    job_id = reopened.json()["jobId"]
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": title_mode,
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        }
        db.commit()

    response = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["shortOverlayTitleMode"] == title_mode
    assert response.json()["shortTopBannerEnabled"] is True
    assert response.json()["clips"][0]["overlayTitleExpected"] is True
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.settings_json["shortOverlayTitleMode"] == title_mode


def test_subtitle_review_title_edit_recomputes_auto_title_expectation(
    client: TestClient,
) -> None:
    job_id, candidate_id, rendered_bytes = _seed_reeditable_export()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": "auto",
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
        }
        db.commit()

    reopened = client.post(
        "/api/jobs/reedit-upload",
        files={"file": ("finished.mp4", rendered_bytes, "video/mp4")},
    )
    assert reopened.status_code == 200
    job_id = reopened.json()["jobId"]
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    reopened_artifact = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    assert reopened_artifact["clips"][0]["overlayTitleExpected"] is False

    edited = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={"title": "手動で変更したタイトル"},
    )

    assert edited.status_code == 200
    assert edited.json()["clips"][0]["titleEdited"] is True
    assert edited.json()["clips"][0]["overlayTitleExpected"] is True
    artifact = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "subtitle_review_summary.json").read_text(encoding="utf-8"))
    assert artifact["clips"][0]["overlayTitleExpected"] is True
    assert summary["overlay_title_expected_by_clip"] == {candidate_id: True}

    restored = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={"title": "完成したショート"},
    )
    assert restored.status_code == 200
    assert restored.json()["clips"][0]["titleEdited"] is False
    assert restored.json()["clips"][0]["overlayTitleExpected"] is False


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
    job_id = reopened.json()["jobId"]
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
    assert {key: clip["titleStyle"][key] for key in title_style} == title_style
    assert clip["titleStyle"]["fontName"] is None
    assert clip["titleStyle"]["bold"] is None
    assert clip["titleStyle"]["positionMode"] == "explicit"
    assert clip["hookStyle"] is None
    assert {key: clip["subtitleStyle"][key] for key in subtitle_style} == subtitle_style

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
    assert {key: legacy_clip["titleStyle"][key] for key in title_style} == title_style
    assert {key: legacy_clip["subtitleStyle"][key] for key in subtitle_style} == subtitle_style


def test_subtitle_review_hydrates_resolved_style_contract_and_preserves_custom_font(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    artifact_path = storage.job_outputs(job_id) / "subtitle_review.json"
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        video = db.get(Video, "vid_reedit_upload")
        assert job is not None
        assert video is not None
        video.width = 640
        video.height = 360
        job.settings_json = {
            **job.settings_json,
            "mode": "low_cost",
            "shortOverlayTitleMode": "auto",
            "shortSubtitleFontName": "利用者の任意フォント",
            "titleFontName": "利用者の任意タイトルフォント",
            "shortSubtitleFontSize": 81,
            "shortSubtitleXPercent": 42.5,
            "shortSubtitleYPercent": 70,
            "maxCharsPerLineShort": 13,
            "maxLines": 2,
        }
        db.commit()

    completed = client.get(f"/api/jobs/{job_id}/subtitle-review")

    assert completed.status_code == 200
    completed_payload = completed.json()
    completed_clip = completed_payload["clips"][0]
    assert completed_payload["renderMode"] == "low_cost"
    assert completed_clip["subtitleMaxCharsPerLine"] == 13
    assert completed_clip["subtitleMaxLines"] == 2
    assert completed_clip["previewWidth"] == 1080
    assert completed_clip["previewHeight"] == 1920
    assert completed_clip["resolvedSubtitleStyle"]["fontPreset"] is None
    assert completed_clip["resolvedSubtitleStyle"]["fontName"] == "利用者の任意フォント"
    assert completed_clip["resolvedSubtitleStyle"]["xPercent"] == 42.5
    assert completed_clip["resolvedSubtitleStyle"]["positionMode"] == "layout"
    assert completed_clip["resolvedSubtitleStyle"]["positionOverride"] is True
    assert completed_clip["resolvedTitleStyle"]["fontName"] == ("利用者の任意タイトルフォント")
    assert completed_clip["resolvedHookStyle"]["fontName"] == ("利用者の任意タイトルフォント")
    assert "resolvedSubtitleStyle" not in json.loads(artifact_path.read_text(encoding="utf-8"))["clips"][0]

    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["renderMode"] == "low_cost"
    assert persisted["clips"][0]["resolvedSubtitleStyle"]["fontName"] == ("利用者の任意フォント")

    updated = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={
            "title": "手動編集タイトル",
            "subtitleStyle": {
                "fontPreset": None,
                "fontName": "利用者の任意フォント",
                "bold": True,
                "fontSize": 81,
                "primaryColor": "#12AB34",
                "outlineColor": "#000000",
                "outlineWidth": 5,
                "xPercent": 42.5,
                "yPercent": 70,
                "positionMode": "layout",
            },
        },
    )

    assert updated.status_code == 200
    updated_payload = updated.json()
    updated_clip = updated_payload["clips"][0]
    assert updated_clip["overlayTitleExpected"] is True
    assert updated_clip["subtitleStyle"]["fontPreset"] is None
    assert updated_clip["subtitleStyle"]["fontName"] == "利用者の任意フォント"
    assert updated_clip["resolvedSubtitleStyle"]["fontName"] == "利用者の任意フォント"
    assert updated_clip["resolvedSubtitleStyle"]["primaryColor"] == "#12AB34"
    assert updated_clip["resolvedSubtitleStyle"]["positionMode"] == "layout"
    assert updated_clip["resolvedSubtitleStyle"]["xPercent"] == 42.5


def test_normal_resolved_twelve_pixel_style_round_trips_through_content_patch(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    artifact_path = output_dir / "subtitle_review.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["clips"][0]["type"] = "normal"
    artifact["clips"][0]["hookText"] = ""
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [
                    {
                        "id": candidate_id,
                        "type": "normal",
                        "start": 0,
                        "end": 10,
                        "duration": 10,
                        "transcript_text": "字幕",
                        "title": "完成した通常切り抜き",
                    }
                ],
                "shorts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        video = db.get(Video, "vid_reedit_upload")
        assert job is not None
        assert video is not None
        video.width = 640
        video.height = 360
        job.settings_json = {
            **job.settings_json,
            "normalSubtitleFontName": "12px任意フォント",
            "normalSubtitleFontSize": 12,
            "minSubtitleDuration": 0.6,
            "maxSubtitleDuration": 2.5,
            "minGapBetweenSubtitles": 0.2,
        }
        db.commit()

    reopened = client.post(f"/api/jobs/{job_id}/subtitle-review/reopen")
    assert reopened.status_code == 200
    clip = reopened.json()["clips"][0]
    resolved = clip["resolvedSubtitleStyle"]
    assert resolved["fontName"] == "12px任意フォント"
    assert resolved["fontSize"] == 12
    assert clip["resolvedDefaultSubtitleStyle"] == resolved
    assert clip["resolvedDefaultTitleStyle"] is not None
    assert clip["resolvedDefaultHookStyle"] is not None
    assert clip["subtitleMinDurationSeconds"] == 0.6
    assert clip["subtitleMaxDurationSeconds"] == 2.5
    assert clip["subtitleMinGapSeconds"] == 0.2

    updated = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/content",
        json={
            "title": clip["title"],
            "subtitleStyle": {
                "fontPreset": resolved["fontPreset"],
                "fontName": resolved["fontName"],
                "bold": resolved["bold"],
                "fontSize": resolved["fontSize"],
                "primaryColor": "#12AB34",
                "outlineColor": resolved["outlineColor"],
                "outlineWidth": resolved["outlineWidth"],
                "xPercent": resolved["xPercent"],
                "yPercent": resolved["yPercent"],
                "positionMode": resolved["positionMode"],
            },
        },
    )

    assert updated.status_code == 200
    updated_clip = updated.json()["clips"][0]
    assert updated_clip["subtitleStyle"]["fontSize"] == 12
    assert updated_clip["resolvedSubtitleStyle"]["fontSize"] == 12
    assert updated_clip["resolvedSubtitleStyle"]["primaryColor"] == "#12AB34"
    assert updated_clip["resolvedDefaultSubtitleStyle"]["fontSize"] == 12
    assert updated_clip["resolvedDefaultSubtitleStyle"]["primaryColor"] == "#FFFFFF"


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


def test_youtube_posting_profile_is_persisted_in_database(client: TestClient) -> None:
    initial_response = client.get("/api/preferences/youtube-posting-profile")

    assert initial_response.status_code == 200
    assert initial_response.json()["profile"]["performerName"] == ""
    payload = {
        "version": 1,
        "profile": {
            "performerName": "儒烏風亭らでん",
            "affiliation": "hololive DEV_IS / ReGLOSS",
            "baseHashtags": ["#儒烏風亭らでん", "#ReGLOSS"],
            "shortHashtags": ["#shortsfunny"],
            "baseTags": ["儒烏風亭らでん", "ReGLOSS"],
        },
    }

    saved = client.put("/api/preferences/youtube-posting-profile", json=payload)

    assert saved.status_code == 200
    assert client.get("/api/preferences/youtube-posting-profile").json() == payload
    with next(app.dependency_overrides[get_db]()) as db:
        preference = db.get(AppPreference, "youtube_posting_profile")
        assert preference is not None
        assert preference.value_json["profile"]["performerName"] == "儒烏風亭らでん"


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
        "details": {
            "initialSelectionProvider": "legacy",
            "codexInitialSelectionSummaryAvailable": False,
        },
        "error": None,
    }

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.video_id == upload["videoId"]
        assert job.settings_json["mode"] == "high_quality"
        assert job.settings_json["automationMode"] == "manual"
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
        assert job.settings_json["selectionPolicy"] == "strict_quality"
        assert job.settings_json["crossTypeOverlapDedupe"] is False
        assert job.settings_json["heatmapIntervalMode"] is False
        assert job.settings_json["initialSelectionProvider"] == "legacy"
        assert job.settings_json["shortOverlayTitleMode"] == "auto"
        assert job.settings_json["shortTopBannerEnabled"] is True
        assert job.settings_json["shortBottomBannerEnabled"] is True
        assert job.settings_json["shortSubtitleYPercent"] == 68.75
        assert job.settings_json["openaiCandidateLimit"] == 40
        assert job.settings_json["openaiModel"] == "gpt-5.5"
        assert job.settings_json["openaiFallbackToRuleScore"] is True
        assert job.settings_json["ensureSelectedOpenAIScored"] is True
        assert job.settings_json["openaiFinalistScoringLimit"] == 20
        assert job.settings_json["transcriptionLanguage"] == "ja"


@pytest.mark.parametrize("automation_mode", ["shadow", "guarded", "auto"])
def test_create_job_persists_review_based_automation_mode(
    client: TestClient,
    automation_mode: str,
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
                "automationMode": automation_mode,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    )

    assert response.status_code == 201
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, response.json()["jobId"])
        assert job is not None
        assert job.settings_json["automationMode"] == automation_mode
        assert job.settings_json["requireClipPlanReview"] is True
        assert job.settings_json["requireSubtitleReview"] is True


@pytest.mark.parametrize("automation_mode", ["automatic", "future"])
def test_create_job_rejects_unknown_automation_mode(
    client: TestClient,
    automation_mode: str,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        jobs_before = len(list(db.scalars(select(Job)).all()))

    response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "automationMode": automation_mode,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    )

    assert response.status_code == 422
    with next(app.dependency_overrides[get_db]()) as db:
        assert len(list(db.scalars(select(Job)).all())) == jobs_before


@pytest.mark.parametrize("automation_mode", ["shadow", "guarded", "auto"])
def test_create_job_rejects_review_based_mode_without_both_review_stops(
    client: TestClient,
    automation_mode: str,
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
                "automationMode": automation_mode,
                "burnSubtitles": True,
                "requireClipPlanReview": False,
                "requireSubtitleReview": True,
            },
        },
    )

    assert response.status_code == 422


def test_retry_no_usable_selection_reuses_source_and_settings_once(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 0,
                "shortCount": 2,
                "selectionPolicy": "strict_quality",
                "shortTopBannerEnabled": True,
            },
        },
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.progress = 100
        source_job.current_step = "Failed"
        source_job.error_code = "no_usable_selection"
        source_job.error_message = "no clips"
        legacy_settings = dict(source_job.settings_json)
        legacy_settings.pop("shortTopBannerEnabled", None)
        legacy_settings.pop("shortBottomBannerEnabled", None)
        legacy_settings.pop("shortSubtitleYPercent", None)
        legacy_settings.pop("automationMode", None)
        source_job.settings_json = legacy_settings
        expected_settings = {
            **legacy_settings,
            "shortTopBannerEnabled": False,
            "shortBottomBannerEnabled": False,
            "shortSubtitleYPercent": None,
            "automationMode": "manual",
        }
        db.commit()

    storage = app.dependency_overrides[get_storage_paths]()
    source_output = storage.job_outputs(created["jobId"]) / "old-artifact.json"
    source_output.write_text("{}", encoding="utf-8")
    failed_status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert failed_status["error"] == {
        "code": "no_usable_selection",
        "message": "分析は完了しましたが、選定基準を満たす切り抜き候補がありませんでした。",
    }
    queued_jobs: list[str] = []

    def enqueue_once(retry_id: str, _terminal_retry_allowed: object) -> None:
        if retry_id not in queued_jobs:
            queued_jobs.append(retry_id)

    app.dependency_overrides[get_enqueue_retry_job] = lambda: enqueue_once

    first = client.post(f"/api/jobs/{created['jobId']}/retry")
    repeated = client.post(f"/api/jobs/{created['jobId']}/retry")

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert first.json() == repeated.json()
    retry_id = first.json()["jobId"]
    assert retry_id != created["jobId"]
    assert first.json()["status"] == "queued"
    assert queued_jobs == [retry_id]
    assert source_output.read_text(encoding="utf-8") == "{}"
    assert not (storage.outputs / retry_id).exists()
    active_child_source_status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert active_child_source_status["error"]["code"] == "no_usable_selection"
    with next(app.dependency_overrides[get_db]()) as db:
        jobs = list(db.scalars(select(Job)).all())
        retry = db.get(Job, retry_id)
        assert len(jobs) == 2
        assert retry is not None
        assert retry.video_id == upload["videoId"]
        assert retry.settings_json == {**expected_settings, "retryOf": created["jobId"]}
        assert retry.error_code is None

        retry.status = "failed"
        retry.error_code = "no_usable_selection"
        retry.error_message = "still no clips"
        db.commit()

    failed_retry_status = client.get(f"/api/jobs/{retry_id}").json()
    assert failed_retry_status["error"] == {
        "code": "no_usable_selection_retry_exhausted",
        "message": "再処理でも選定基準を満たす切り抜き候補がありませんでした。",
    }
    exhausted_source_status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert exhausted_source_status["error"] == {
        "code": "no_usable_selection_retry_exhausted",
        "message": "このJobの再処理は終了しています。",
    }
    blocked_source_retry = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert blocked_source_retry.status_code == 409
    assert blocked_source_retry.json()["detail"]["code"] == "job_retry_not_available"
    blocked_grandchild = client.post(f"/api/jobs/{retry_id}/retry")
    assert blocked_grandchild.status_code == 409
    assert blocked_grandchild.json()["detail"]["code"] == "job_retry_not_available"


def test_retry_supports_legacy_selection_failure_artifacts(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_output"
        source_job.error_message = "legacy no clips"
        db.commit()

    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(created["jobId"])
    (output_dir / "selected_clips.json").write_text(
        json.dumps({"normalClips": [], "shorts": [], "rejectedCandidates": []}),
        encoding="utf-8",
    )
    (output_dir / "rejection_summary.json").write_text(
        json.dumps({"render_failure_count": 0, "render_failures": []}),
        encoding="utf-8",
    )

    status_payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status_payload["error"] == {
        "code": "no_usable_selection",
        "message": "分析は完了しましたが、選定基準を満たす切り抜き候補がありませんでした。",
    }

    queued_jobs: list[str] = []
    app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda retry_id, _terminal_retry_allowed: queued_jobs.append(retry_id)
    retried = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert retried.status_code == 202
    assert queued_jobs == [retried.json()["jobId"]]


def test_retry_rejects_legacy_render_failure_artifacts(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_output"
        source_job.error_message = "legacy render failure"
        db.commit()

    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(created["jobId"])
    (output_dir / "selected_clips.json").write_text(
        json.dumps({"normalClips": [], "shorts": [{"id": "short_1"}]}),
        encoding="utf-8",
    )
    (output_dir / "rejection_summary.json").write_text(
        json.dumps({"render_failure_count": 1}),
        encoding="utf-8",
    )
    (output_dir / "render_failures.json").write_text(
        json.dumps([{"type": "short", "error": "ffmpeg failed"}]),
        encoding="utf-8",
    )
    (output_dir / "subtitle_review.json").write_text("{}", encoding="utf-8")

    status_payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status_payload["error"] == {
        "code": "no_usable_output",
        "message": "切り抜き動画を生成できませんでした。レンダリング結果を確認してください。",
    }
    rejected = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "job_retry_not_available"


def test_retry_no_usable_selection_rejects_other_failures_or_missing_source(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "audio_extraction_failed"
        db.commit()

    other_failure = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert other_failure.status_code == 409
    assert other_failure.json()["detail"]["code"] == "job_retry_not_available"

    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        video = db.get(Video, upload["videoId"])
        assert source_job is not None
        assert video is not None
        source_job.error_code = "no_usable_selection"
        db.commit()
        Path(video.stored_path).unlink()

    missing_source = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert missing_source.status_code == 409
    assert missing_source.json()["detail"]["code"] == "retry_source_unavailable"


def test_retry_enqueue_failure_preserves_recoverable_pending_job(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_selection"
        db.commit()

    def fail_enqueue(_job_id: str, _terminal_retry_allowed: object) -> None:
        raise RuntimeError("queue unavailable")

    app.dependency_overrides[get_enqueue_retry_job] = lambda: fail_enqueue
    failed = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "retry_enqueue_failed"
    with next(app.dependency_overrides[get_db]()) as db:
        jobs = list(db.scalars(select(Job)).all())
        assert len(jobs) == 2
        pending = next(job for job in jobs if job.id != created["jobId"])
        assert pending.status == "queued"
        assert pending.current_step == "再処理を開始待ち"
        pending_id = pending.id

    queued_jobs: list[str] = []
    app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda retry_id, _terminal_retry_allowed: queued_jobs.append(retry_id)
    retried = client.post(f"/api/jobs/{created['jobId']}/retry")
    assert retried.status_code == 202
    assert queued_jobs == [retried.json()["jobId"]]
    assert retried.json()["jobId"] == pending_id


def test_retry_recovers_child_committed_before_enqueue(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    retry_id = "job_" + hashlib.sha256(f"retry:{created['jobId']}".encode("utf-8")).hexdigest()[:32]
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_selection"
        db.add(
            Job(
                id=retry_id,
                video_id=upload["videoId"],
                status="queued",
                progress=5,
                current_step="再処理を開始待ち",
                settings_json=dict(source_job.settings_json),
            )
        )
        db.commit()

    queued_jobs: list[str] = []
    app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda retry_id, _terminal_retry_allowed: queued_jobs.append(retry_id)
    recovered = client.post(f"/api/jobs/{created['jobId']}/retry")

    assert recovered.status_code == 202
    assert recovered.json()["jobId"] == retry_id
    assert queued_jobs == [retry_id]
    with next(app.dependency_overrides[get_db]()) as db:
        retry = db.get(Job, retry_id)
        assert retry is not None
        assert retry.current_step == "再処理を開始待ち"


def test_retry_enqueues_child_committed_by_competing_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    retry_id = "job_" + hashlib.sha256(f"retry:{created['jobId']}".encode("utf-8")).hexdigest()[:32]
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_selection"
        db.commit()

    original_commit = Session.commit
    competing_commit_injected = False

    def commit_with_competing_insert(db: Session) -> None:
        nonlocal competing_commit_injected
        pending = next(
            (item for item in db.new if isinstance(item, Job) and item.id == retry_id),
            None,
        )
        if pending is not None and not competing_commit_injected:
            competing_commit_injected = True
            with next(app.dependency_overrides[get_db]()) as competing_db:
                competing_db.add(
                    Job(
                        id=pending.id,
                        video_id=pending.video_id,
                        status=pending.status,
                        progress=pending.progress,
                        current_step=pending.current_step,
                        settings_json=dict(pending.settings_json),
                    )
                )
                original_commit(competing_db)
        original_commit(db)

    monkeypatch.setattr(Session, "commit", commit_with_competing_insert)
    queued_jobs: list[str] = []
    app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda queued_id, _terminal_retry_allowed: queued_jobs.append(queued_id)

    recovered = client.post(f"/api/jobs/{created['jobId']}/retry")

    assert recovered.status_code == 202
    assert recovered.json()["jobId"] == retry_id
    assert competing_commit_injected is True
    assert queued_jobs == [retry_id]


def test_retry_does_not_rewind_worker_progress_after_enqueue(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_selection"
        db.commit()

    def advance_worker(retry_id: str, _terminal_retry_allowed: object) -> None:
        with next(app.dependency_overrides[get_db]()) as db:
            retry = db.get(Job, retry_id)
            assert retry is not None
            retry.status = "transcribing"
            retry.current_step = "Transcribing"
            retry.progress = 28
            db.commit()

    app.dependency_overrides[get_enqueue_retry_job] = lambda: advance_worker
    retried = client.post(f"/api/jobs/{created['jobId']}/retry")

    assert retried.status_code == 202
    assert retried.json()["status"] == "transcribing"
    with next(app.dependency_overrides[get_db]()) as db:
        retry = db.get(Job, retried.json()["jobId"])
        assert retry is not None
        assert retry.status == "transcribing"
        assert retry.current_step == "Transcribing"
        assert retry.progress == 28


def test_retry_does_not_enqueue_after_worker_completes_existing_attempt(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    with next(app.dependency_overrides[get_db]()) as db:
        source_job = db.get(Job, created["jobId"])
        assert source_job is not None
        source_job.status = "failed"
        source_job.error_code = "no_usable_selection"
        db.commit()

    queued_jobs: list[str] = []

    def finish_before_terminal_retry(
        retry_id: str,
        terminal_retry_allowed: object,
    ) -> None:
        with next(app.dependency_overrides[get_db]()) as db:
            retry = db.get(Job, retry_id)
            assert retry is not None
            retry.status = "completed"
            retry.current_step = "Completed"
            retry.progress = 100
            db.commit()
        assert callable(terminal_retry_allowed)
        assert terminal_retry_allowed() is False

    app.dependency_overrides[get_enqueue_retry_job] = lambda: finish_before_terminal_retry
    retried = client.post(f"/api/jobs/{created['jobId']}/retry")

    assert retried.status_code == 202
    assert retried.json()["status"] == "completed"
    assert queued_jobs == []


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
                "shortTopBannerEnabled": True,
                "shortBottomBannerEnabled": True,
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
        assert job.settings_json["shortTopBannerEnabled"] is True
        assert job.settings_json["shortBottomBannerEnabled"] is True
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

    assert properties["automationMode"]["default"] == "manual"
    assert properties["automationMode"]["enum"] == ["manual", "shadow", "guarded", "auto"]
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
    assert properties["selectionPolicy"]["default"] == "strict_quality"
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


def test_openapi_exposes_optional_boolean_heatmap_mode_for_clip_reselection(
    client: TestClient,
) -> None:
    payload = client.get("/openapi.json").json()
    schema = payload["components"]["schemas"]["ClipPlanReselectionRequest"]

    assert schema["properties"]["heatmapIntervalMode"]["anyOf"] == [
        {"type": "boolean"},
        {"type": "null"},
    ]
    assert "heatmapIntervalMode" not in schema["required"]


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


def test_unpublished_rerender_exports_are_hidden_and_active_publication_is_blocked(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(created["jobId"])
    published_path = output_dir / "normal.mp4"
    published_path.write_bytes(b"published")
    storage.zip_path(created["jobId"]).write_bytes(b"published zip")
    staging_path = storage.temp / "rr" / "attempt" / "normal.mp4"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_bytes(b"staging")

    with next(app.dependency_overrides[get_db]()) as db:
        db.add_all(
            [
                ExportItem(
                    id="exp_published",
                    job_id=created["jobId"],
                    video_id=upload["videoId"],
                    type="normal",
                    title="Published",
                    duration=10,
                    score=1,
                    video_path=str(published_path),
                ),
                ExportItem(
                    id="exp_staging",
                    job_id=created["jobId"],
                    video_id=upload["videoId"],
                    type="normal",
                    title="Staging",
                    duration=10,
                    score=1,
                    video_path=str(staging_path),
                ),
            ]
        )
        db.commit()

    results = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results.status_code == 200
    assert [item["id"] for item in results.json()["normalClips"]] == [
        "exp_published"
    ]
    assert client.get("/api/exports/exp_staging/download").status_code == 404

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        job.status = "rendering_normal_clips"
        db.commit()

    active_results = client.get(f"/api/jobs/{created['jobId']}/results")
    assert active_results.status_code == 200
    assert active_results.json()["normalClips"] == []
    assert client.get("/api/exports/exp_published/download").status_code == 409
    assert client.get(f"/api/jobs/{created['jobId']}/download.zip").status_code == 409


def test_rollback_failed_publication_stays_blocked_during_hook_updates(
    client: TestClient,
) -> None:
    job_id, candidate_id, _rendered_bytes = _seed_reeditable_export()
    storage = app.dependency_overrides[get_storage_paths]()
    output_dir = storage.job_outputs(job_id)
    storage.zip_path(job_id).write_bytes(b"possibly mixed zip")
    assert client.post(f"/api/jobs/{job_id}/subtitle-review/reopen").status_code == 200
    mark_rerender_publication_unresolved(
        output_dir,
        job_id=job_id,
        render_revision=2,
        attempt_id="test_unresolved_publication",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.error_code = "subtitle_rerender_rollback_failed"
        db.commit()

    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = (
        lambda: lambda _job_id, _clip_id, _start, _end: None
    )
    queued = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/hook-scene",
        json={"start": 1, "end": 3},
    )
    assert queued.status_code == 202
    assert rerender_publication_is_unresolved(output_dir)
    assert client.get("/api/exports/exp_reedit_upload/download").status_code == 409
    assert client.get(f"/api/jobs/{job_id}/download.zip").status_code == 409
    assert client.get(f"/api/jobs/{job_id}/results").json()["shorts"] == []

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.status = "awaiting_subtitle_review"
        db.commit()

    def fail_enqueue(
        _job_id: str,
        _clip_id: str,
        _start: float | None,
        _end: float | None,
    ) -> None:
        raise RuntimeError("queue unavailable")

    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = (
        lambda: fail_enqueue
    )
    queue_failed = client.patch(
        f"/api/jobs/{job_id}/subtitle-review/clips/{candidate_id}/hook-scene",
        json={"start": 2, "end": 4},
    )
    assert queue_failed.status_code == 503
    assert rerender_publication_is_unresolved(output_dir)
    assert client.get("/api/exports/exp_reedit_upload/download").status_code == 409
    assert client.get(f"/api/jobs/{job_id}/download.zip").status_code == 409


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
