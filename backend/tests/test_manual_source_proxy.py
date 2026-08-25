from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.select_candidates import CandidateSelection
from app.db import Base, get_db
from app.jobs.clip_plan import build_clip_plan, load_clip_plan
from app.jobs.runner import AutoClipperPipelineDependencies, run_autoclipper_job
from app.main import app
from app.models import Job, Video
from app.render.render_manual_source_proxy import (
    render_manual_source_proxy,
)
from app.render.render_review_preview import build_review_preview_command
from app.schemas import JobSettings
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.probe import VideoMetadata


@pytest.fixture()
def proxy_environment(
    tmp_path: Path,
) -> Generator[tuple[sessionmaker[Session], StoragePaths], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'manual-source-proxy.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    try:
        yield session_factory, storage
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_manual_job(
    session_factory: sessionmaker[Session],
    storage: StoragePaths,
    *,
    filename: str,
) -> Path:
    source_path = storage.uploads / filename
    source_path.write_bytes(b"original source")
    settings = JobSettings(
        workflowMode="manual",
        normalClipCount=0,
        shortCount=0,
    ).model_dump(by_alias=True, mode="json")
    with session_factory() as db:
        db.add(
            Video(
                id="vid_manual_proxy",
                original_filename=filename,
                stored_path=str(source_path),
            )
        )
        db.add(
            Job(
                id="job_manual_proxy",
                video_id="vid_manual_proxy",
                status="queued",
                progress=5,
                current_step="Queued",
                settings_json=settings,
            )
        )
        db.commit()
    return source_path


def _metadata(*, has_audio: bool) -> VideoMetadata:
    return VideoMetadata(
        duration=45.0,
        width=1920,
        height=1080,
        fps=30.0,
        has_audio=has_audio,
        video_stream_duration=45.0,
        audio_stream_duration=45.0 if has_audio else None,
        container_duration=45.0,
    )


def test_manual_source_proxy_reuses_preview_renderer_without_audio(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    output_path = tmp_path / "manual_source_preview.mp4"

    def fake_preview_renderer(
        input_path: str | Path,
        target_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        calls.append(
            {
                "input": Path(input_path),
                "output": Path(target_path),
                **kwargs,
            }
        )
        Path(target_path).write_bytes(b"proxy")
        return Path(target_path)

    result = render_manual_source_proxy(
        tmp_path / "source.mkv",
        output_path,
        duration=45.0,
        has_audio=False,
        preview_renderer=fake_preview_renderer,
    )

    assert result == output_path
    assert calls == [
        {
            "input": tmp_path / "source.mkv",
            "output": output_path,
            "start": 0.0,
            "duration": 45.0,
            "include_audio": False,
        }
    ]


def test_review_preview_command_disables_audio_for_silent_manual_source() -> None:
    command = build_review_preview_command(
        "source.mkv",
        "manual_source_preview.mp4",
        start=0.0,
        duration=45.0,
        include_audio=False,
    )

    assert "-an" in command
    assert "-c:a" not in command
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "force_divisible_by=2" in command[command.index("-vf") + 1]


def test_clip_plan_editor_url_is_additive_and_keeps_source_url() -> None:
    automatic = build_clip_plan("job_automatic", CandidateSelection(), {})
    manual = build_clip_plan(
        "job_manual",
        CandidateSelection(),
        {},
        editor_video_url="/api/jobs/job_manual/editor-video",
    )

    assert automatic.source_video_url == "/api/jobs/job_automatic/source-video"
    assert automatic.editor_video_url is None
    assert manual.source_video_url == "/api/jobs/job_manual/source-video"
    assert manual.editor_video_url == "/api/jobs/job_manual/editor-video"


def test_manual_mkv_job_generates_proxy_and_serves_editor_video(
    proxy_environment: tuple[sessionmaker[Session], StoragePaths],
) -> None:
    session_factory, storage = proxy_environment
    source_path = _seed_manual_job(
        session_factory,
        storage,
        filename="manual-source.mkv",
    )
    proxy_calls: list[dict[str, Any]] = []
    proxy_start_steps: list[str] = []

    def fake_proxy_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        with session_factory() as db:
            job = db.get(Job, "job_manual_proxy")
            assert job is not None
            proxy_start_steps.append(job.current_step)
        proxy_calls.append(
            {
                "input": Path(input_path),
                "output": Path(output_path),
                **kwargs,
            }
        )
        Path(output_path).write_bytes(b"browser-ready proxy")
        return Path(output_path)

    visited = run_autoclipper_job(
        "job_manual_proxy",
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: _metadata(has_audio=False),
            manual_source_proxy_renderer=fake_proxy_renderer,
        ),
    )

    assert visited == ["probing", "awaiting_manual_edit"]
    plan = load_clip_plan(
        storage.job_outputs("job_manual_proxy") / "clip_plan.json"
    )
    assert plan.source_video_url == "/api/jobs/job_manual_proxy/source-video"
    assert plan.editor_video_url == "/api/jobs/job_manual_proxy/editor-video"
    assert proxy_start_steps == ["手動編集用の動画を準備中"]
    assert proxy_calls == [
        {
            "input": source_path,
            "output": storage.job_outputs("job_manual_proxy")
            / "manual_source_preview.mp4",
            "duration": 45.0,
            "has_audio": False,
        }
    ]

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(plan.editor_video_url)
        client.close()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"browser-ready proxy"
