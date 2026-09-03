from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.db import Base, get_db
from app.jobs.runner import _create_zip
from app.jobs.queue import get_enqueue_thumbnail_regeneration
from app.jobs.thumbnail_regeneration import run_export_thumbnail_regeneration
from app.jobs.thumbnails import generate_export_thumbnails
from app.main import app
from app.models import ExportItem, Job, Video
from app.render.render_thumbnail import ThumbnailRenderResult
from app.storage.paths import StoragePaths, get_storage_paths


def _candidate(
    *,
    candidate_id: str,
    candidate_type: str,
    start: float,
    duration: float,
    **values: object,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,
        start=start,
        end=start + duration,
        duration=duration,
        transcript_text="サムネイル候補の字幕",
        title="サムネイル候補",
        **values,
    )


def _export(
    output_dir: Path,
    *,
    export_id: str,
    candidate_id: str,
    export_type: str,
    duration: float,
) -> ExportItem:
    type_dir = "shorts" if export_type == "short" else "normal"
    stem = "short_01" if export_type == "short" else "normal_01"
    media_dir = output_dir / type_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    video_path = media_dir / f"{stem}.mp4"
    metadata_path = media_dir / f"{stem}.json"
    video_path.write_bytes(b"completed mp4")
    metadata_path.write_text(
        json.dumps({"candidate_id": candidate_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    return ExportItem(
        id=export_id,
        job_id="job_thumbnail",
        video_id="vid_thumbnail",
        candidate_id=candidate_id,
        type=export_type,
        title="完成動画",
        duration=duration,
        score=90,
        video_path=str(video_path),
        metadata_path=str(metadata_path),
    )


def test_normal_thumbnail_uses_source_absolute_time_from_clip_relative_setting(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    source_path = tmp_path / "uploads" / "source.mp4"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source mp4")
    candidate = _candidate(
        candidate_id="cand_normal",
        candidate_type="normal",
        start=3600.5,
        duration=30,
        thumbnail_frame_seconds=4.25,
        thumbnail_kicker="見どころ",
        thumbnail_line1="一行目",
        thumbnail_line2="二行目",
    )
    export = _export(
        output_dir,
        export_id="exp_normal",
        candidate_id=candidate.id,
        export_type="normal",
        duration=candidate.duration,
    )
    received: dict[str, object] = {}

    def fake_normal_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: object,
    ) -> ThumbnailRenderResult:
        received.update(input_path=Path(input_path), **kwargs)
        rendered = Path(output_path)
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"jpeg")
        return ThumbnailRenderResult(
            path=rendered,
            kind="normal",
            source_timestamp=float(kwargs["frame_time"]),
            width=1280,
            height=720,
        )

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(normalClips=[candidate]),
        input_path=source_path,
        job_output_dir=output_dir,
        normal_renderer=fake_normal_renderer,
    )

    assert result.failures == []
    assert received["input_path"] == source_path
    assert received["frame_time"] == pytest.approx(3604.75)
    metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
    assert metadata["thumbnail_status"] == "ready"
    assert metadata["thumbnail_source_time"] == pytest.approx(3604.75)
    assert metadata["thumbnail_source_time_basis"] == "source_video_absolute"
    assert Path(metadata["thumbnail_path"]).is_file()


def test_normal_thumbnail_empty_fields_match_preview_and_auto_frame(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    source_path = tmp_path / "uploads" / "source.mp4"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source mp4")
    candidate = _candidate(
        candidate_id="cand_normal_empty",
        candidate_type="normal",
        start=100,
        duration=20,
    )
    export = _export(
        output_dir,
        export_id="exp_normal_empty",
        candidate_id=candidate.id,
        export_type="normal",
        duration=candidate.duration,
    )
    received: dict[str, object] = {}

    def fake_normal_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: object,
    ) -> ThumbnailRenderResult:
        received.update(input_path=Path(input_path), **kwargs)
        rendered = Path(output_path)
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"jpeg")
        return ThumbnailRenderResult(
            path=rendered,
            kind="normal",
            source_timestamp=float(kwargs["frame_time"]),
            width=1280,
            height=720,
        )

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(normalClips=[candidate]),
        input_path=source_path,
        job_output_dir=output_dir,
        normal_renderer=fake_normal_renderer,
    )

    assert result.failures == []
    assert received["frame_time"] == pytest.approx(107.6)
    assert received["eyebrow"] == ""
    assert received["title_first_line"] == ""
    assert received["title_second_line"] == ""


def test_short_thumbnail_uses_completed_mp4_and_hook_interval(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    candidate = _candidate(
        candidate_id="cand_short",
        candidate_type="short",
        start=120,
        duration=20,
        hook_text="冒頭フック",
        hook_duration_seconds=3,
        hook_scene_start=126,
        hook_scene_end=128.5,
    )
    export = _export(
        output_dir,
        export_id="exp_short",
        candidate_id=candidate.id,
        export_type="short",
        duration=22.5,
    )
    received: dict[str, object] = {}

    def fake_short_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: object,
    ) -> ThumbnailRenderResult:
        received.update(input_path=Path(input_path), **kwargs)
        rendered = Path(output_path)
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"jpeg")
        midpoint = (float(kwargs["hook_start"]) + float(kwargs["hook_end"])) / 2
        return ThumbnailRenderResult(
            path=rendered,
            kind="short",
            source_timestamp=midpoint,
            width=1080,
            height=1920,
        )

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(shorts=[candidate]),
        input_path=tmp_path / "unused-source.mp4",
        job_output_dir=output_dir,
        short_renderer=fake_short_renderer,
    )

    assert result.failures == []
    assert received["input_path"] == Path(export.video_path)
    assert received["hook_start"] == pytest.approx(0)
    assert received["hook_end"] == pytest.approx(2.5)
    metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
    assert metadata["thumbnail_source_time"] == pytest.approx(1.25)
    assert metadata["thumbnail_source_time_basis"] == "rendered_video_relative"


def test_short_thumbnail_stays_within_hook_text_when_hook_scene_is_longer(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    candidate = _candidate(
        candidate_id="cand_short_mismatch",
        candidate_type="short",
        start=120,
        duration=20,
        hook_text="1秒だけ表示するフック",
        hook_duration_seconds=1,
        hook_scene_start=126,
        hook_scene_end=129,
    )
    export = _export(
        output_dir,
        export_id="exp_short_mismatch",
        candidate_id=candidate.id,
        export_type="short",
        duration=23,
    )
    received: dict[str, object] = {}

    def fake_short_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: object,
    ) -> ThumbnailRenderResult:
        received.update(kwargs)
        rendered = Path(output_path)
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"jpeg")
        midpoint = (float(kwargs["hook_start"]) + float(kwargs["hook_end"])) / 2
        return ThumbnailRenderResult(
            path=rendered,
            kind="short",
            source_timestamp=midpoint,
            width=1080,
            height=1920,
        )

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(shorts=[candidate]),
        input_path=tmp_path / "unused-source.mp4",
        job_output_dir=output_dir,
        short_renderer=fake_short_renderer,
    )

    assert result.failures == []
    assert received["hook_start"] == pytest.approx(0)
    assert received["hook_end"] == pytest.approx(1)
    metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
    assert metadata["thumbnail_source_time"] == pytest.approx(0.5)


def test_thumbnail_failure_is_recorded_without_raising(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    candidate = _candidate(
        candidate_id="cand_normal",
        candidate_type="normal",
        start=10,
        duration=20,
    )
    export = _export(
        output_dir,
        export_id="exp_normal",
        candidate_id=candidate.id,
        export_type="normal",
        duration=candidate.duration,
    )

    def failing_renderer(*_args: object, **_kwargs: object) -> ThumbnailRenderResult:
        raise RuntimeError("ffmpeg failed")

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(normalClips=[candidate]),
        input_path=tmp_path / "source.mp4",
        job_output_dir=output_dir,
        normal_renderer=failing_renderer,
    )

    assert result.generated_paths == []
    assert len(result.failures) == 1
    assert result.failures[0].error_code == "RuntimeError"
    assert Path(export.video_path).is_file()
    metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
    assert metadata["candidate_id"] == candidate.id
    assert metadata["thumbnail_status"] == "failed"
    assert metadata["thumbnail_path"] is None
    assert metadata["thumbnail_error_code"] == "RuntimeError"


def test_thumbnail_cleanup_error_does_not_escape_failure_recording(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    candidate = _candidate(
        candidate_id="cand_cleanup",
        candidate_type="normal",
        start=10,
        duration=20,
    )
    export = _export(
        output_dir,
        export_id="exp_cleanup",
        candidate_id=candidate.id,
        export_type="normal",
        duration=candidate.duration,
    )
    blocked_output = output_dir / "thumbnails" / "normal" / "normal_01.jpg"
    blocked_output.mkdir(parents=True)

    def failing_renderer(*_args: object, **_kwargs: object) -> ThumbnailRenderResult:
        raise RuntimeError("ffmpeg failed before cleanup")

    result = generate_export_thumbnails(
        exports=[export],
        selection=CandidateSelection(normalClips=[candidate]),
        input_path=tmp_path / "source.mp4",
        job_output_dir=output_dir,
        normal_renderer=failing_renderer,
    )

    assert len(result.failures) == 1
    assert result.failures[0].error_code == "RuntimeError"
    metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
    assert metadata["thumbnail_status"] == "failed"
    assert metadata["thumbnail_error_code"] == "RuntimeError"


def test_zip_contains_thumbnail_in_type_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    export = _export(
        output_dir,
        export_id="exp_normal",
        candidate_id="cand_normal",
        export_type="normal",
        duration=20,
    )
    thumbnail_path = output_dir / "thumbnails" / "normal" / "normal_01_thumbnail.jpg"
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"jpeg")
    metadata_path = Path(export.metadata_path)
    metadata_path.write_text(
        json.dumps(
            {
                "candidate_id": export.candidate_id,
                "thumbnail_status": "ready",
                "thumbnail_path": str(thumbnail_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    zip_path = output_dir / "download.zip"

    _create_zip(zip_path, [export])

    with ZipFile(zip_path) as archive:
        assert "thumbnails/normal/normal_01_thumbnail.jpg" in archive.namelist()
        assert archive.read("thumbnails/normal/normal_01_thumbnail.jpg") == b"jpeg"


def test_zip_rejects_thumbnail_from_sibling_job(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs" / "job_thumbnail"
    export = _export(
        output_dir,
        export_id="exp_normal",
        candidate_id="cand_normal",
        export_type="normal",
        duration=20,
    )
    sibling_thumbnail = (
        tmp_path / "outputs" / "job_sibling" / "thumbnails" / "normal" / "normal_01.jpg"
    )
    sibling_thumbnail.parent.mkdir(parents=True, exist_ok=True)
    sibling_thumbnail.write_bytes(b"sibling jpeg")
    Path(export.metadata_path).write_text(
        json.dumps(
            {
                "candidate_id": export.candidate_id,
                "thumbnail_status": "ready",
                "thumbnail_path": str(sibling_thumbnail),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    zip_path = output_dir / "download.zip"

    _create_zip(zip_path, [export])

    with ZipFile(zip_path) as archive:
        assert not any(name.startswith("thumbnails/") for name in archive.namelist())


@pytest.fixture()
def thumbnail_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'thumbnail.db'}",
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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_thumbnail_endpoint_rejects_path_outside_published_job(
    thumbnail_client: TestClient,
    tmp_path: Path,
) -> None:
    storage = app.dependency_overrides[get_storage_paths]()
    job_dir = storage.job_outputs("job_traversal")
    video_path = job_dir / "normal" / "normal_01.mp4"
    metadata_path = job_dir / "normal" / "normal_01.json"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"mp4")
    outside_thumbnail = tmp_path / "outside.jpg"
    outside_thumbnail.write_bytes(b"jpeg")
    metadata_path.write_text(
        json.dumps(
            {
                "thumbnail_status": "ready",
                "thumbnail_path": str(outside_thumbnail),
            }
        ),
        encoding="utf-8",
    )

    with next(app.dependency_overrides[get_db]()) as db:
        video = Video(
            id="vid_traversal",
            original_filename="source.mp4",
            stored_path=str(storage.uploads / "source.mp4"),
        )
        job = Job(
            id="job_traversal",
            video_id=video.id,
            status="completed",
            progress=100,
            current_step="Completed",
            settings_json={},
        )
        export = ExportItem(
            id="exp_traversal",
            job_id=job.id,
            video_id=video.id,
            candidate_id="cand_traversal",
            type="normal",
            title="通常切り抜き",
            duration=20,
            score=90,
            video_path=str(video_path),
            metadata_path=str(metadata_path),
        )
        db.add_all([video, job, export])
        db.commit()

    response = thumbnail_client.get("/api/exports/exp_traversal/thumbnail")

    assert response.status_code == 404
    assert response.json()["detail"] == "thumbnail is not published"


def test_completed_normal_thumbnail_can_be_queued_without_rerendering_video(
    thumbnail_client: TestClient,
) -> None:
    storage = app.dependency_overrides[get_storage_paths]()
    job_dir = storage.job_outputs("job_regenerate")
    video_path = job_dir / "normal" / "normal_01.mp4"
    metadata_path = job_dir / "normal" / "normal_01.json"
    thumbnail_path = job_dir / "thumbnails" / "normal" / "normal_01.jpg"
    source_path = storage.uploads / "source.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"source")
    video_path.write_bytes(b"completed video")
    thumbnail_path.write_bytes(b"old thumbnail")
    metadata_path.write_text(
        json.dumps(
            {
                "candidate_id": "cand_regenerate",
                "start": 120.0,
                "thumbnail_status": "ready",
                "thumbnail_path": str(thumbnail_path),
                "thumbnail_frame_seconds": 4.0,
                "thumbnail_render_revision": 0,
            }
        ),
        encoding="utf-8",
    )
    with next(app.dependency_overrides[get_db]()) as db:
        video = Video(
            id="vid_regenerate",
            original_filename="source.mp4",
            stored_path=str(source_path),
        )
        job = Job(
            id="job_regenerate",
            video_id=video.id,
            status="completed",
            progress=100,
            current_step="Completed",
            settings_json={},
        )
        export = ExportItem(
            id="exp_regenerate",
            job_id=job.id,
            video_id=video.id,
            candidate_id="cand_regenerate",
            type="normal",
            title="通常切り抜き",
            duration=30,
            score=90,
            video_path=str(video_path),
            metadata_path=str(metadata_path),
        )
        db.add_all([video, job, export])
        db.commit()

    queued: list[tuple[str, int]] = []
    app.dependency_overrides[get_enqueue_thumbnail_regeneration] = (
        lambda: lambda export_id, revision: queued.append((export_id, revision))
    )

    response = thumbnail_client.post(
        "/api/exports/exp_regenerate/thumbnail/regenerate",
        json={"frameSeconds": 8.5, "subjectAnchorX": 1, "advanceFrame": True},
    )

    assert response.status_code == 202
    assert response.json() == {
        "exportId": "exp_regenerate",
        "status": "generating",
        "revision": 1,
    }
    assert queued == [("exp_regenerate", 1)]
    assert video_path.read_bytes() == b"completed video"
    assert thumbnail_path.read_bytes() == b"old thumbnail"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["thumbnail_status"] == "generating"
    assert metadata["thumbnail_frame_seconds"] == pytest.approx(8.5)
    assert metadata["thumbnail_subject_anchor_x"] == pytest.approx(1)
    assert metadata["thumbnail_advance_frame"] is True
    assert metadata["thumbnail_variant_index"] == 0
    assert metadata["thumbnail_request_revision"] == 1


def test_thumbnail_regeneration_worker_promotes_only_the_requested_thumbnail(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'worker.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    job_dir = storage.job_outputs("job_worker")
    video_path = job_dir / "normal" / "normal_01.mp4"
    metadata_path = job_dir / "normal" / "normal_01.json"
    thumbnail_path = job_dir / "thumbnails" / "normal" / "normal_01.jpg"
    source_path = storage.uploads / "source.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"source video")
    video_path.write_bytes(b"completed video")
    thumbnail_path.write_bytes(b"old thumbnail")
    metadata_path.write_text(
        json.dumps(
            {
                "start": 3600.0,
                "thumbnail_kicker": "見どころ",
                "thumbnail_line1": "一行目",
                "thumbnail_line2": "二行目",
                "thumbnail_frame_seconds": 12.5,
                "thumbnail_subject_anchor_x": 1.0,
                "thumbnail_advance_frame": True,
                "thumbnail_variant_index": 3,
                "thumbnail_request_revision": 2,
                "thumbnail_render_revision": 1,
                "thumbnail_status": "generating",
                "thumbnail_path": str(thumbnail_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with testing_session() as db:
        video = Video(
            id="vid_worker",
            original_filename="source.mp4",
            stored_path=str(source_path),
        )
        job = Job(
            id="job_worker",
            video_id=video.id,
            status="completed",
            progress=100,
            current_step="Completed",
            settings_json={},
        )
        export = ExportItem(
            id="exp_worker",
            job_id=job.id,
            video_id=video.id,
            candidate_id="cand_worker",
            type="normal",
            title="通常切り抜き",
            duration=40,
            score=90,
            video_path=str(video_path),
            metadata_path=str(metadata_path),
        )
        db.add_all([video, job, export])
        db.commit()

    received: dict[str, object] = {}
    selected: dict[str, object] = {}

    def fake_frame_selector(
        input_path: str | Path,
        **kwargs: object,
    ) -> float:
        selected.update(input_path=Path(input_path), **kwargs)
        return 28.0

    def fake_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: object,
    ) -> ThumbnailRenderResult:
        received.update(input_path=Path(input_path), **kwargs)
        rendered = Path(output_path)
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"new thumbnail")
        return ThumbnailRenderResult(
            path=rendered,
            kind="normal",
            source_timestamp=float(kwargs["frame_time"]),
            width=1280,
            height=720,
        )

    run_export_thumbnail_regeneration(
        "exp_worker",
        2,
        session_factory=testing_session,
        paths=storage,
        normal_renderer=fake_renderer,
        frame_selector=fake_frame_selector,
    )

    assert video_path.read_bytes() == b"completed video"
    assert thumbnail_path.read_bytes() == b"new thumbnail"
    assert received["input_path"] == source_path
    assert received["frame_time"] == pytest.approx(3628.0)
    assert received["subject_anchor_x"] == pytest.approx(1)
    assert selected["input_path"] == source_path
    assert selected["clip_start"] == pytest.approx(3600.0)
    assert selected["clip_end"] == pytest.approx(3640.0)
    assert selected["variant_index"] == 3
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["thumbnail_status"] == "ready"
    assert metadata["thumbnail_render_revision"] == 2
    assert metadata["thumbnail_template_version"] == "raden_normal_v3"
    assert metadata["thumbnail_frame_seconds"] == pytest.approx(28.0)
    assert metadata["thumbnail_advance_frame"] is False
    engine.dispose()
