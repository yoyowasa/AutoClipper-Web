import json
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.jobs.runner as runner_module
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import build_audio_features
from app.candidates.select_candidates import CandidateSelection
from app.db import Base, get_db
from app.jobs.clip_plan import load_clip_plan
from app.jobs.queue import get_enqueue_job
from app.jobs.runner import (
    AutoClipperPipelineDependencies,
    run_autoclipper_job,
    run_subtitle_review_render,
)
from app.jobs.subtitle_review import (
    confirm_review_clip,
    load_subtitle_review,
    queue_review_render,
    write_subtitle_review,
)
from app.main import app
from app.models import Job, Video
from app.render.subtitles_ass import subtitle_events_for_candidate
from app.schemas import JobSettings
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.probe import VideoMetadata


@pytest.fixture()
def manual_environment(
    tmp_path: Path,
) -> Generator[tuple[sessionmaker[Session], StoragePaths], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'manual.db'}",
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


def _seed_job(
    session_factory: sessionmaker[Session],
    storage: StoragePaths,
    *,
    settings: dict[str, Any],
    job_id: str = "job_manual",
) -> None:
    source_path = storage.uploads / f"{job_id}.mp4"
    source_path.write_bytes(b"video")
    with session_factory() as db:
        db.add(
            Video(
                id=f"vid_{job_id}",
                original_filename="manual.mp4",
                stored_path=str(source_path),
            )
        )
        db.add(
            Job(
                id=job_id,
                video_id=f"vid_{job_id}",
                status="queued",
                progress=5,
                current_step="Queued",
                settings_json=settings,
            )
        )
        db.commit()


def _probe(*, has_audio: bool = True) -> VideoMetadata:
    return VideoMetadata(
        duration=30.0,
        width=1920,
        height=1080,
        fps=30.0,
        has_audio=has_audio,
        video_stream_duration=30.0,
        audio_stream_duration=30.0 if has_audio else None,
        container_duration=30.0,
    )


def _fake_manual_source_proxy(
    _input: str | Path,
    output: str | Path,
    **_kwargs: Any,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"proxy")
    return path


def test_manual_job_stops_after_probe_with_empty_editable_plan(
    manual_environment: tuple[sessionmaker[Session], StoragePaths],
) -> None:
    session_factory, storage = manual_environment
    settings = JobSettings(
        workflowMode="manual",
        normalClipCount=0,
        shortCount=0,
    ).model_dump(by_alias=True, mode="json")
    _seed_job(session_factory, storage, settings=settings)

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("manual draft must stop after probe")

    visited = run_autoclipper_job(
        "job_manual",
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: _probe(has_audio=False),
            manual_source_proxy_renderer=_fake_manual_source_proxy,
            extract_audio=must_not_run,  # type: ignore[arg-type]
            transcribe_audio=must_not_run,  # type: ignore[arg-type]
            detect_scenes=must_not_run,  # type: ignore[arg-type]
            detect_black_screen=must_not_run,  # type: ignore[arg-type]
        ),
    )

    assert visited == ["probing", "awaiting_manual_edit"]
    with session_factory() as db:
        job = db.get(Job, "job_manual")
        video = db.get(Video, "vid_job_manual")
        assert job is not None and job.status == "awaiting_manual_edit"
        assert video is not None and video.duration == 30.0
    plan = load_clip_plan(storage.job_outputs("job_manual") / "clip_plan.json")
    assert plan.state == "manual_editing"
    assert plan.source_duration == 30.0
    assert plan.clips == []


def test_manual_clip_crud_and_approve_preserve_user_values(
    manual_environment: tuple[sessionmaker[Session], StoragePaths],
) -> None:
    session_factory, storage = manual_environment
    settings = JobSettings(
        workflowMode="manual",
        manualSubtitleMode="none",
        normalClipCount=0,
        shortCount=0,
        requireClipPlanReview=True,
        requireSubtitleReview=True,
    ).model_dump(by_alias=True, mode="json")
    _seed_job(session_factory, storage, settings=settings)
    with session_factory() as db:
        job = db.get(Job, "job_manual")
        assert job is not None
        legacy_settings = dict(job.settings_json or {})
        legacy_settings.pop("shortTopBannerEnabled", None)
        legacy_settings.pop("shortBottomBannerEnabled", None)
        legacy_settings.pop("shortSubtitleYPercent", None)
        job.settings_json = legacy_settings
        db.commit()
    run_autoclipper_job(
        "job_manual",
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: _probe(),
            manual_source_proxy_renderer=_fake_manual_source_proxy,
        ),
    )

    queued: list[str] = []

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    app.dependency_overrides[get_enqueue_job] = lambda: queued.append
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/jobs/job_manual/clip-plan/clips",
                json={
                    "type": "normal",
                    "title": "仮タイトル",
                    "start": 2.0,
                    "end": 8.0,
                },
            )
            assert created.status_code == 201
            clip_id = created.json()["clips"][0]["id"]

            updated = client.patch(
                f"/api/jobs/job_manual/clip-plan/clips/{clip_id}",
                json={
                    "type": "short",
                    "title": "手動タイトル",
                    "start": 3.0,
                    "end": 9.5,
                },
            )
            assert updated.status_code == 200
            updated_clip = updated.json()["clips"][0]
            assert updated_clip["type"] == "short"
            assert updated_clip["title"] == "手動タイトル"
            assert updated_clip["start"] == 3.0
            assert updated_clip["end"] == 9.5
            assert updated_clip["duration"] == 6.5

            hook = client.patch(
                f"/api/jobs/job_manual/clip-plan/clips/{clip_id}/hook-scene",
                json={"start": 4.0, "end": 6.0},
            )
            assert hook.status_code == 202

            disposable = client.post(
                "/api/jobs/job_manual/clip-plan/clips",
                json={"type": "normal", "start": 10.0, "end": 12.0},
            )
            disposable_id = disposable.json()["clips"][1]["id"]
            deleted = client.delete(
                f"/api/jobs/job_manual/clip-plan/clips/{disposable_id}"
            )
            assert deleted.status_code == 200
            assert [clip["id"] for clip in deleted.json()["clips"]] == [clip_id]

            approved = client.post("/api/jobs/job_manual/clip-plan/approve")
            assert approved.status_code == 200
            assert approved.json()["status"] == "queued"
    finally:
        app.dependency_overrides.clear()

    assert queued == ["job_manual"]
    with session_factory() as db:
        job = db.get(Job, "job_manual")
        assert job is not None
        assert job.settings_json["manualEditFinalized"] is True
        assert job.settings_json["manualSubtitleMode"] == "none"
        assert job.settings_json["burnSubtitles"] is False
        assert job.settings_json["requireSubtitleReview"] is True
        assert job.settings_json["requireClipPlanReview"] is False
        assert job.settings_json["normalClipCount"] == 0
        assert job.settings_json["shortCount"] == 1
        assert job.settings_json["shortTopBannerEnabled"] is False
        assert job.settings_json["shortBottomBannerEnabled"] is False
        assert job.settings_json["shortSubtitleYPercent"] is None
        assert job.settings_json["shortClipTimeRanges"] == [
            {"startSeconds": 3.0, "endSeconds": 9.5}
        ]
        assert job.settings_json["manualClipMetadata"] == [
            {
                "id": clip_id,
                "type": "short",
                "title": "手動タイトル",
                "startSeconds": 3.0,
                "endSeconds": 9.5,
                "hookSceneStart": 4.0,
                "hookSceneEnd": 6.0,
            }
        ]


def test_finalized_manual_job_skips_scene_scoring_and_preserves_identity(
    manual_environment: tuple[sessionmaker[Session], StoragePaths],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, storage = manual_environment
    clip_id = "clip_user_fixed"
    settings = JobSettings(
        workflowMode="manual",
        manualEditFinalized=True,
        normalClipCount=1,
        shortCount=0,
        normalClipTimeRanges=[{"startSeconds": 3.0, "endSeconds": 9.5}],
        requireClipPlanReview=False,
        requireSubtitleReview=False,
        burnSubtitles=True,
        manualClipMetadata=[
            {
                "id": clip_id,
                "type": "normal",
                "title": "固定タイトル",
                "startSeconds": 3.0,
                "endSeconds": 9.5,
                "hookSceneStart": None,
                "hookSceneEnd": None,
            }
        ],
    ).model_dump(by_alias=True, mode="json")
    _seed_job(session_factory, storage, settings=settings)

    def fake_extract(_input: str | Path, output: str | Path) -> Path:
        Path(output).write_bytes(b"wav")
        return Path(output)

    def fake_render(
        _input: str | Path,
        output: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"rendered")
        return Path(output)

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("manual workflow must skip automatic analysis")

    monkeypatch.setattr(runner_module, "load_heatmap_for_video", must_not_run)
    monkeypatch.setattr(
        runner_module,
        "generate_normal_candidates_with_summary",
        must_not_run,
    )
    monkeypatch.setattr(
        runner_module,
        "generate_short_candidates_with_summary",
        must_not_run,
    )
    monkeypatch.setattr(runner_module, "_score_candidate_list", must_not_run)
    monkeypatch.setattr(runner_module, "select_candidates", must_not_run)

    visited = run_autoclipper_job(
        "job_manual",
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: _probe(),
            extract_audio=fake_extract,
            transcribe_audio=lambda _path: [
                TranscriptSegment(
                    start=float(index),
                    end=float(index + 1),
                    text=f"これは十分な長さを持つ手動字幕セグメント{index}",
                )
                for index in range(30)
            ],
            detect_silence=lambda _path, _duration: [],
            compute_audio_features=lambda _path, duration, segments: build_audio_features(
                duration=duration,
                silence_segments=segments,
                volume_peak=0.5,
            ),
            detect_scenes=must_not_run,  # type: ignore[arg-type]
            detect_black_screen=must_not_run,  # type: ignore[arg-type]
            normal_renderer=fake_render,
            short_renderer=fake_render,
            openai_scorer=must_not_run,  # type: ignore[arg-type]
        ),
    )

    assert "detecting_scenes" not in visited
    assert "scoring_candidates" not in visited
    assert "selecting_clips" not in visited
    selected = json.loads(
        (storage.job_outputs("job_manual") / "selected_clips.json").read_text(
            encoding="utf-8"
        )
    )
    assert selected["normalClips"][0]["id"] == clip_id
    assert selected["normalClips"][0]["title"] == "固定タイトル"
    assert selected["normalClips"][0]["start"] == 3.0
    assert selected["normalClips"][0]["end"] == 9.5
    finalized_plan = load_clip_plan(
        storage.job_outputs("job_manual") / "clip_plan.json"
    )
    assert finalized_plan.state == "approved"


@pytest.mark.parametrize(
    ("subtitle_mode", "burn_subtitles", "expected_segment_count"),
    [
        ("none", False, 0),
        ("manual", True, 2),
    ],
)
def test_manual_subtitle_modes_skip_audio_and_prepare_review(
    manual_environment: tuple[sessionmaker[Session], StoragePaths],
    monkeypatch: pytest.MonkeyPatch,
    subtitle_mode: str,
    burn_subtitles: bool,
    expected_segment_count: int,
) -> None:
    session_factory, storage = manual_environment
    settings = JobSettings(
        workflowMode="manual",
        manualEditFinalized=True,
        manualSubtitleMode=subtitle_mode,
        normalClipCount=1,
        shortCount=1,
        normalClipTimeRanges=[{"startSeconds": 3.0, "endSeconds": 9.0}],
        shortClipTimeRanges=[{"startSeconds": 3.0, "endSeconds": 9.0}],
        requireClipPlanReview=False,
        requireSubtitleReview=True,
        burnSubtitles=burn_subtitles,
        manualClipMetadata=[
            {
                "id": "clip_normal_manual",
                "type": "normal",
                "title": "通常タイトル",
                "startSeconds": 3.0,
                "endSeconds": 9.0,
                "hookSceneStart": None,
                "hookSceneEnd": None,
            },
            {
                "id": "clip_short_manual",
                "type": "short",
                "title": "ショートタイトル",
                "startSeconds": 3.0,
                "endSeconds": 9.0,
                "hookSceneStart": None,
                "hookSceneEnd": None,
            },
        ],
    ).model_dump(by_alias=True, mode="json")
    _seed_job(session_factory, storage, settings=settings)

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("manual subtitle mode must skip automatic audio analysis")

    monkeypatch.setattr(
        runner_module,
        "_render_exact_subtitle_review_preview_for_clip",
        lambda **_kwargs: SimpleNamespace(
            spec_hash="exact-spec",
            live_spec_hash="live-spec",
        ),
    )

    visited = run_autoclipper_job(
        "job_manual",
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: _probe(has_audio=False),
            extract_audio=must_not_run,  # type: ignore[arg-type]
            transcribe_audio=must_not_run,  # type: ignore[arg-type]
            detect_scenes=must_not_run,  # type: ignore[arg-type]
            detect_black_screen=must_not_run,  # type: ignore[arg-type]
        ),
    )

    assert "extracting_audio" not in visited
    assert "transcribing" not in visited
    assert visited[-2:] == ["preparing_subtitle_review", "awaiting_subtitle_review"]
    review = load_subtitle_review(
        storage.job_outputs("job_manual") / "subtitle_review.json"
    )
    assert [clip.id for clip in review.clips] == [
        "clip_normal_manual",
        "clip_short_manual",
    ]
    assert len(review.segments) == expected_segment_count
    if subtitle_mode == "manual":
        assert [segment.text for segment in review.segments] == ["", ""]
        assert [segment.affected_clip_ids for segment in review.segments] == [
            ["clip_normal_manual"],
            ["clip_short_manual"],
        ]
        transcript_payload = json.loads(
            (storage.job_outputs("job_manual") / "transcript_segments.json").read_text(
                encoding="utf-8"
            )
        )
        assert [segment["clip_id"] for segment in transcript_payload] == [
            "clip_normal_manual",
            "clip_short_manual",
        ]
        selection = CandidateSelection.model_validate(
            json.loads(
                (storage.job_outputs("job_manual") / "selected_clips.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        scoped_segments = [
            TranscriptSegment.model_validate(segment).model_copy(
                update={"text": f"字幕{index}"}
            )
            for index, segment in enumerate(transcript_payload, start=1)
        ]
        normal_events = subtitle_events_for_candidate(
            scoped_segments,
            selection.normal_clips[0],
        )
        short_events = subtitle_events_for_candidate(
            scoped_segments,
            selection.shorts[0],
        )
        assert [event.text for event in normal_events] == ["字幕1"]
        assert [event.text for event in short_events] == ["字幕2"]
    else:
        def override_db() -> Generator[Session, None, None]:
            with session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_storage_paths] = lambda: storage
        try:
            with TestClient(app) as client:
                hook_response = client.patch(
                    "/api/jobs/job_manual/subtitle-review/clips/"
                    "clip_short_manual/hook-scene",
                    json={"start": 4.0, "end": 6.0},
                )
                assert hook_response.status_code == 422
                assert "without audio" in hook_response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

        for clip in review.clips:
            review = confirm_review_clip(review, clip.id)
        review = queue_review_render(review)
        write_subtitle_review(
            review,
            storage.job_outputs("job_manual") / "subtitle_review.json",
        )
        with session_factory() as db:
            job = db.get(Job, "job_manual")
            assert job is not None
            job.status = "rendering_normal_clips"
            db.commit()

        burn_subtitle_values: list[bool] = []

        def fake_render(
            _input: str | Path,
            output: str | Path,
            **kwargs: Any,
        ) -> Path:
            burn_subtitle_values.append(bool(kwargs.get("burn_subtitles", False)))
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"rendered")
            return path

        resume_visited = run_subtitle_review_render(
            "job_manual",
            render_revision=1,
            session_factory=session_factory,
            paths=storage,
            dependencies=AutoClipperPipelineDependencies(
                normal_renderer=fake_render,
                short_renderer=fake_render,
            ),
        )
        assert resume_visited[-1] == "completed"
        assert burn_subtitle_values == [False, False]
