from collections.abc import Generator
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.db import Base, get_db
from app.jobs.queue import get_enqueue_job
from app.main import app
from app.models import ExportItem, Job
from app.render.crop_strategy import (
    build_blur_background_filter,
    build_center_crop_filter,
    build_face_tracking_crop_filter,
    strategy_order,
)
from app.render.render_short import (
    ShortRenderResult,
    render_selected_short_candidates,
    render_short_clip,
)
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.face_detect import FaceDetection, best_face_center
from app.video.probe import VideoMetadata


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


def make_short(
    candidate_id: str,
    start: float,
    end: float,
    title: str,
    final_score: float,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type="short",
        start=start,
        end=end,
        duration=end - start,
        transcript_text=f"{title} transcript",
        title=title,
        overlay_title=f"{title} overlay",
        final_score=final_score,
    )


def test_crop_strategy_filters_target_1080x1920() -> None:
    assert build_center_crop_filter("subtitles.ass") == (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "ass='subtitles.ass'"
    )
    assert build_face_tracking_crop_filter(
        source_width=1920,
        source_height=1080,
        face_center=(0.25, 0.5),
    ) == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:313:0"

    blur_filter = build_blur_background_filter("subtitles.ass")
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in blur_filter
    assert "crop=1080:1920" in blur_filter
    assert "gblur=sigma=24" in blur_filter
    assert "ass='subtitles.ass'" in blur_filter


def test_face_center_and_strategy_order() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.2, center_y=0.5, width=0.1, height=0.1),
        FaceDetection(start=1, end=1, center_x=0.8, center_y=0.5, width=0.3, height=0.3),
    ]

    center = best_face_center(detections)

    assert center is not None
    assert center[0] > 0.7
    assert strategy_order("auto", detections=detections, source_width=1920, source_height=1080) == [
        "face_tracking_crop",
        "center_crop",
        "blur_background",
    ]
    assert strategy_order("auto", detections=[], source_width=1920, source_height=1080) == [
        "center_crop",
        "blur_background",
    ]


def test_render_short_clip_auto_falls_back_to_center_crop(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return [FaceDetection(start=0, end=0, center_x=0.25, center_y=0.5, width=0.2, height=0.2)]

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        video_filter = command[command.index("-vf") + 1]
        if "crop=1080:1920:313:0" in video_filter:
            raise RuntimeError("face crop failed")
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        subtitle_path="subtitles.ass",
        layout="auto",
        face_detector=fake_face_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "center_crop"
    assert output_path.read_bytes() == b"short mp4"
    assert len(commands) == 2
    assert "crop=1080:1920:313:0" in commands[0][commands[0].index("-vf") + 1]
    assert commands[1][commands[1].index("-vf") + 1].startswith(
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    )


def test_render_selected_short_candidates_creates_exports_visible_in_results(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    renderer_calls: list[dict[str, Any]] = []

    def fake_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> ShortRenderResult:
        renderer_calls.append({"input_path": input_path, "output_path": output_path, **kwargs})
        if Path(output_path).name == "short_02.mp4":
            raise RuntimeError("short render failed")
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return ShortRenderResult(path=Path(output_path), strategy="center_crop")

    candidates = [
        make_short("cand_short_1", 0.0, 45.0, "First short", 93.0),
        make_short("cand_short_fail", 50.0, 95.0, "Broken short", 90.0),
        make_short("cand_short_2", 100.0, 145.0, "Second short", 84.0),
        Candidate(
            id="cand_normal_ignored",
            type="normal",
            start=0.0,
            end=120.0,
            duration=120.0,
            transcript_text="ignored normal",
            final_score=99.0,
        ),
    ]
    transcript_segments = [
        TranscriptSegment(start=0.0, end=10.0, text="first subtitle"),
        TranscriptSegment(start=100.0, end=110.0, text="second subtitle"),
    ]

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None

        result = render_selected_short_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=candidates,
            transcript_segments=transcript_segments,
            burn_subtitles=True,
            normalize_audio=True,
            layout="auto",
            paths=storage,
            renderer=fake_renderer,
            source_width=1920,
            source_height=1080,
        )

        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert [export.candidate_id for export in result.exports] == ["cand_short_1", "cand_short_2"]
    assert [failure.candidate_id for failure in result.failures] == ["cand_short_fail"]
    assert [export.candidate_id for export in exports] == ["cand_short_1", "cand_short_2"]
    assert len(renderer_calls) == 3
    assert all(call["subtitle_path"] is not None for call in renderer_calls)
    assert all(call["layout"] == "auto" for call in renderer_calls)
    assert all(call["source_width"] == 1920 for call in renderer_calls)

    shorts_dir = storage.outputs / created["jobId"] / "shorts"
    subtitle_dir = storage.outputs / created["jobId"] / "subtitles" / "shorts"
    assert (shorts_dir / "short_01.mp4").is_file()
    assert not (shorts_dir / "short_01.ass").exists()
    assert (subtitle_dir / "short_01.ass").is_file()
    assert not (shorts_dir / "short_02.mp4").is_file()
    assert (shorts_dir / "short_03.mp4").is_file()
    short_metadata = json.loads((shorts_dir / "short_01.json").read_text(encoding="utf-8"))
    assert short_metadata["title"] == "First short"
    assert short_metadata["overlay_title"] == "First short overlay"
    assert short_metadata["title_source"] == "existing"
    assert "original_start" in short_metadata
    assert "refined_start" in short_metadata
    assert "boundary_refined" in short_metadata
    assert short_metadata["subtitle_path"].replace("\\", "/").endswith("/subtitles/shorts/short_01.ass")

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    shorts = results_response.json()["shorts"]
    assert len(shorts) == 2
    assert {short["title"] for short in shorts} == {"First short", "Second short"}

    download_response = client.get(shorts[0]["downloadUrl"])
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"rendered short_")


def test_render_selected_short_candidates_writes_fallback_title_metadata(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> ShortRenderResult:
        Path(output_path).write_bytes(b"rendered short")
        return ShortRenderResult(path=Path(output_path), strategy="center_crop")

    candidate = Candidate(
        id="cand_short_title_fallback",
        type="short",
        start=0.0,
        end=45.0,
        duration=45.0,
        transcript_text="まあ インフレの見方が変わる重要な場面です。",
        final_score=82.0,
    )

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        result = render_selected_short_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=[candidate],
            burn_subtitles=True,
            paths=storage,
            renderer=fake_renderer,
        )
        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert result.exports[0].title == "インフレの見方が変わる重要な場面です"
    assert exports[0].title == "インフレの見方が変わる重要な場面です"
    shorts_dir = storage.outputs / created["jobId"] / "shorts"
    short_metadata = json.loads((shorts_dir / "short_01.json").read_text(encoding="utf-8"))
    assert short_metadata["title"] == "インフレの見方が変わる重要な場面です"
    assert short_metadata["overlay_title"] == "インフレの見方が変わる重要な場面です"
    assert short_metadata["title_source"] == "transcript_fallback"
    subtitle_dir = storage.outputs / created["jobId"] / "subtitles" / "shorts"
    assert not (shorts_dir / "short_01.ass").exists()
    ass_text = (subtitle_dir / "short_01.ass").read_text(encoding="utf-8")
    assert ",Title,," not in ass_text
