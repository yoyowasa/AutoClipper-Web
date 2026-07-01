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
from app.render.render_normal import render_selected_normal_candidates
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


def make_candidate(
    candidate_id: str,
    start: float,
    end: float,
    title: str,
    final_score: float,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type="normal",
        start=start,
        end=end,
        duration=end - start,
        transcript_text=f"{title} transcript",
        title=title,
        final_score=final_score,
    )


def test_render_selected_normal_candidates_creates_exports_visible_in_results(client: TestClient) -> None:
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
    ) -> Path:
        renderer_calls.append({"input_path": input_path, "output_path": output_path, **kwargs})
        if Path(output_path).name == "normal_02.mp4":
            raise RuntimeError("render failed for candidate")
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    candidates = [
        make_candidate("cand_normal_1", 0.0, 120.0, "First normal", 91.0),
        make_candidate("cand_normal_fail", 130.0, 250.0, "Broken normal", 90.0),
        make_candidate("cand_normal_2", 260.0, 380.0, "Second normal", 82.0),
        Candidate(
            id="cand_short_ignored",
            type="short",
            start=0.0,
            end=40.0,
            duration=40.0,
            transcript_text="ignored short",
            final_score=99.0,
        ),
    ]
    transcript_segments = [
        TranscriptSegment(start=0.0, end=10.0, text="first subtitle"),
        TranscriptSegment(start=260.0, end=270.0, text="second subtitle"),
    ]

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None

        result = render_selected_normal_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=candidates,
            transcript_segments=transcript_segments,
            burn_subtitles=True,
            normalize_audio=True,
            paths=storage,
            renderer=fake_renderer,
        )

        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert [export.candidate_id for export in result.exports] == ["cand_normal_1", "cand_normal_2"]
    assert [failure.candidate_id for failure in result.failures] == ["cand_normal_fail"]
    assert [export.candidate_id for export in exports] == ["cand_normal_1", "cand_normal_2"]
    assert len(renderer_calls) == 3
    assert all(call["subtitle_path"] is not None for call in renderer_calls)
    assert all(call["normalize_audio"] is True for call in renderer_calls)

    normal_dir = storage.outputs / created["jobId"] / "normal"
    subtitle_dir = storage.outputs / created["jobId"] / "subtitles" / "normal"
    assert (normal_dir / "normal_01.mp4").is_file()
    assert not (normal_dir / "normal_01.ass").exists()
    assert (subtitle_dir / "normal_01.ass").is_file()
    assert not (normal_dir / "normal_02.mp4").is_file()
    assert (normal_dir / "normal_03.mp4").is_file()
    normal_metadata = json.loads((normal_dir / "normal_01.json").read_text(encoding="utf-8"))
    assert normal_metadata["title"] == "First normal"
    assert normal_metadata["title_source"] == "existing"
    assert normal_metadata["subtitle_path"].replace("\\", "/").endswith("/subtitles/normal/normal_01.ass")

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    normal_clips = results_response.json()["normalClips"]
    assert len(normal_clips) == 2
    assert {clip["title"] for clip in normal_clips} == {"First normal", "Second normal"}

    download_response = client.get(normal_clips[0]["downloadUrl"])
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"rendered normal_")


def test_render_selected_normal_candidates_uses_transcript_fallback_title(client: TestClient) -> None:
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
    ) -> Path:
        Path(output_path).write_bytes(b"rendered normal")
        return Path(output_path)

    candidate = Candidate(
        id="cand_normal_title_fallback",
        type="normal",
        start=0.0,
        end=120.0,
        duration=120.0,
        transcript_text="えっと 物価上昇で投資判断が変わる場面です。",
        final_score=80.0,
    )

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        result = render_selected_normal_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=[candidate],
            burn_subtitles=False,
            paths=storage,
            renderer=fake_renderer,
        )
        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert result.exports[0].title == "物価上昇で投資判断が変わる場面です"
    assert exports[0].title == "物価上昇で投資判断が変わる場面です"
    normal_dir = storage.outputs / created["jobId"] / "normal"
    normal_metadata = json.loads((normal_dir / "normal_01.json").read_text(encoding="utf-8"))
    assert normal_metadata["title"] == "物価上昇で投資判断が変わる場面です"
    assert normal_metadata["title_source"] == "transcript_fallback"
