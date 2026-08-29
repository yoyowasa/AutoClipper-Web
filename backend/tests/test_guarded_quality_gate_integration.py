from __future__ import annotations

import hashlib
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.jobs.runner as runner_module
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import build_audio_features
from app.db import Base, get_db
from app.jobs.automation import (
    automation_manifest_path,
    build_automation_manifest,
    write_automation_manifest,
)
from app.jobs.clip_plan import clip_plan_output_path
from app.jobs.quality_gate import (
    QualityGateCheck,
    QualityGateDecision,
    load_quality_gate_decision,
    quality_gate_decision_path,
    write_quality_gate_decision,
)
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
    subtitle_review_output_path,
    write_subtitle_review,
)
from app.main import app
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.probe import VideoMetadata
from app.video.scene_detect import SceneSegment


@pytest.fixture()
def guarded_client(
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
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    app.dependency_overrides[get_enqueue_job] = lambda: lambda _job_id: None
    try:
        yield TestClient(app), storage, testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _decision(
    job_id: str,
    *,
    stage: str,
    outcome: str,
    mode: str = "guarded",
) -> QualityGateDecision:
    route_by_stage_and_outcome = {
        ("selection", "pass"): "continue",
        ("selection", "fail"): "clip_review",
        ("selection", "unknown"): "clip_review",
        ("content", "pass"): "continue",
        ("content", "fail"): "subtitle_review",
        ("content", "unknown"): "subtitle_review",
        ("post_render", "pass"): "continue",
        ("post_render", "fail"): "failed",
        ("post_render", "unknown"): "failed",
    }
    return QualityGateDecision(
        jobId=job_id,
        mode=mode,
        enforced=mode == "guarded",
        stage=stage,
        inputHash=hashlib.sha256(f"{job_id}:{stage}:{outcome}".encode()).hexdigest(),
        outcome=outcome,
        route=(
            "observe"
            if mode == "shadow"
            else route_by_stage_and_outcome[(stage, outcome)]
        ),
        checks=[
            QualityGateCheck(
                code=f"{stage}.integration",
                outcome=outcome,
                reasonCode=None if outcome == "pass" else f"integration_{outcome}",
                evidence={"source": "integration_test"},
            )
        ],
        createdAt=datetime.now(UTC),
    )


def _create_review_job(
    client: TestClient,
    *,
    automation_mode: str = "guarded",
) -> str:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    )
    assert upload.status_code == 201
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload.json()["videoId"],
            "settings": {
                "automationMode": automation_mode,
                "initialSelectionProvider": "legacy",
                "normalClipCount": 1,
                "shortCount": 0,
                "normalMinDuration": 60,
                "normalMaxDuration": 120,
                "normalClipTimeRanges": [
                    {"startSeconds": 5, "endSeconds": 95},
                ],
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    )
    assert created.status_code == 201
    return str(created.json()["jobId"])


def _transcript() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start=0,
            end=40,
            text="最初に問題の背景を説明し、具体的な事例へ進みます。",
            confidence=0.95,
        ),
        TranscriptSegment(
            start=40,
            end=80,
            text="確認手順を順番に実行すると、原因を安全に切り分けられます。",
            confidence=0.95,
        ),
        TranscriptSegment(
            start=80,
            end=120,
            text="最後に結果を整理し、次に行う対応を明確にして話題を終えます。",
            confidence=0.95,
        ),
    ]


def _dependencies(tmp_path: Path) -> AutoClipperPipelineDependencies:
    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake wav")
        return path

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preview")
        return path

    del tmp_path
    return AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: _transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0, end=120)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
        subtitle_review_preview_renderer=fake_render,
    )


def _queue_guarded_subtitle_render(
    job_id: str,
    *,
    storage: StoragePaths,
    session_factory: sessionmaker[Session],
) -> int:
    review_path = subtitle_review_output_path(storage.job_outputs(job_id))
    review = load_subtitle_review(review_path)
    for clip in review.clips:
        review = confirm_review_clip(review, clip.id)
    review = queue_review_render(review)
    write_subtitle_review(review, review_path)
    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.status = "rendering_normal_clips"
        db.commit()
    return review.render_revision


def test_guarded_selection_pass_skips_clip_review_and_stops_at_content_unknown(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(str(kwargs["job_id"]), stage="selection", outcome="pass"),
    )

    statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )

    output_dir = storage.job_outputs(job_id)
    assert statuses[-1] == "awaiting_subtitle_review"
    assert not clip_plan_output_path(output_dir).exists()
    assert load_quality_gate_decision(
        quality_gate_decision_path(output_dir, "selection")
    ).outcome == "pass"
    content = load_quality_gate_decision(
        quality_gate_decision_path(output_dir, "content")
    )
    assert content.outcome == "unknown"
    assert content.route == "subtitle_review"
    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["status"] == "awaiting_subtitle_review"
    assert payload["details"]["automationGateStage"] == "content"
    assert payload["details"]["automationGateOutcome"] == "unknown"


@pytest.mark.parametrize("outcome", ["fail", "unknown"])
def test_guarded_selection_non_pass_routes_to_clip_review(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="selection",
            outcome=outcome,
        ),
    )

    statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )

    output_dir = storage.job_outputs(job_id)
    assert statuses[-1] == "awaiting_clip_review"
    assert clip_plan_output_path(output_dir).is_file()
    assert not quality_gate_decision_path(output_dir, "content").exists()
    selection = load_quality_gate_decision(
        quality_gate_decision_path(output_dir, "selection")
    )
    assert selection.outcome == outcome
    assert selection.route == "clip_review"
    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["status"] == "awaiting_clip_review"
    assert payload["details"]["automationGateStage"] == "selection"
    assert payload["details"]["automationGateOutcome"] == outcome


@pytest.mark.parametrize(
    ("status", "expected_stage", "expected_outcome"),
    [
        ("awaiting_clip_review", "selection", "fail"),
        ("awaiting_subtitle_review", "content", "unknown"),
        ("completed", "post_render", "pass"),
    ],
)
def test_job_details_uses_gate_for_current_status_not_stale_later_stage(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    status: str,
    expected_stage: str,
    expected_outcome: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    decisions = {
        "selection": _decision(job_id, stage="selection", outcome="fail"),
        "content": _decision(job_id, stage="content", outcome="unknown"),
        "post_render": _decision(job_id, stage="post_render", outcome="pass"),
    }
    for stage, decision in decisions.items():
        write_quality_gate_decision(
            decision,
            quality_gate_decision_path(output_dir, stage),
        )

    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        video = db.get(Video, job.video_id)
        assert video is not None
        write_automation_manifest(
            build_automation_manifest(
                job_id=job.id,
                video_id=video.id,
                stored_path=video.stored_path,
                settings=dict(job.settings_json or {}),
            ),
            automation_manifest_path(output_dir),
        )
        job.status = status
        db.commit()

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["status"] == status
    assert payload["details"]["automationGateStage"] == expected_stage
    assert payload["details"]["automationGateOutcome"] == expected_outcome


@pytest.mark.parametrize("mismatch", ["job", "stage", "mode"])
def test_job_details_falls_back_for_mismatched_gate_identity(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    mismatch: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        video = db.get(Video, job.video_id)
        assert video is not None
        write_automation_manifest(
            build_automation_manifest(
                job_id=job.id,
                video_id=video.id,
                stored_path=video.stored_path,
                settings=dict(job.settings_json or {}),
            ),
            automation_manifest_path(output_dir),
        )
        job.status = "awaiting_clip_review"
        db.commit()

    decision = _decision(
        "job_other" if mismatch == "job" else job_id,
        stage="content" if mismatch == "stage" else "selection",
        outcome="unknown",
        mode="shadow" if mismatch == "mode" else "guarded",
    )
    write_quality_gate_decision(
        decision,
        quality_gate_decision_path(output_dir, "selection"),
    )

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["details"]["automationGateState"] == "fallback_manual"
    assert payload["details"]["automationGateInvalid"] is True
    assert "automationGateStage" not in payload["details"]


def test_job_details_falls_back_when_guarded_stable_stage_has_no_decision(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        video = db.get(Video, job.video_id)
        assert video is not None
        write_automation_manifest(
            build_automation_manifest(
                job_id=job.id,
                video_id=video.id,
                stored_path=video.stored_path,
                settings=dict(job.settings_json or {}),
            ),
            automation_manifest_path(output_dir),
        )
        job.status = "awaiting_clip_review"
        db.commit()

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["details"]["automationGateState"] == "fallback_manual"
    assert payload["details"]["automationGateMissing"] is True


def test_guarded_content_pass_can_continue_to_completed(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="selection",
            outcome="pass",
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome="pass",
        ),
    )

    statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )

    output_dir = storage.job_outputs(job_id)
    assert statuses[-1] == "completed"
    assert load_quality_gate_decision(
        quality_gate_decision_path(output_dir, "post_render")
    ).outcome == "pass"
    review_payload = client.get(f"/api/jobs/{job_id}/subtitle-review").json()
    assert review_payload["state"] == "completed"


@pytest.mark.parametrize("outcome", ["fail", "unknown"])
def test_guarded_review_render_content_non_pass_returns_before_render(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="selection",
            outcome="pass",
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome="unknown",
        ),
    )
    initial_statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )
    assert initial_statuses[-1] == "awaiting_subtitle_review"
    render_revision = _queue_guarded_subtitle_render(
        job_id,
        storage=storage,
        session_factory=session_factory,
    )

    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome=outcome,
        ),
    )
    render_calls: list[str] = []

    def must_not_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        render_calls.append(str(output_path))
        raise AssertionError("guarded content non-pass must stop before rendering")

    statuses = run_subtitle_review_render(
        job_id,
        render_revision=render_revision,
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            normal_renderer=must_not_render,
            short_renderer=must_not_render,
        ),
    )

    output_dir = storage.job_outputs(job_id)
    assert statuses[-1] == "awaiting_subtitle_review"
    assert render_calls == []
    assert load_subtitle_review(
        subtitle_review_output_path(output_dir)
    ).state == "awaiting_review"
    decision = load_quality_gate_decision(
        quality_gate_decision_path(output_dir, "content")
    )
    assert decision.outcome == outcome
    assert decision.route == "subtitle_review"
    assert not quality_gate_decision_path(output_dir, "post_render").exists()
    assert not (output_dir / "normal" / "normal_01.mp4").exists()
    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.status == "awaiting_subtitle_review"
        assert list(
            db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)).all()
        ) == []


def test_guarded_review_render_content_pass_continues_to_renderer(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="selection",
            outcome="pass",
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome="unknown",
        ),
    )
    initial_statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )
    assert initial_statuses[-1] == "awaiting_subtitle_review"
    render_revision = _queue_guarded_subtitle_render(
        job_id,
        storage=storage,
        session_factory=session_factory,
    )

    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome="pass",
        ),
    )
    render_calls: list[Path] = []

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"rendered")
        render_calls.append(path)
        return path

    statuses = run_subtitle_review_render(
        job_id,
        render_revision=render_revision,
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            normal_renderer=fake_render,
            short_renderer=fake_render,
        ),
    )

    assert statuses[-1] == "completed"
    assert [path.name for path in render_calls] == ["normal_01.mp4"]
    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.status == "completed"
        assert len(
            list(
                db.scalars(
                    select(ExportItem).where(ExportItem.job_id == job_id)
                ).all()
            )
        ) == 1


@pytest.mark.parametrize(
    ("failure_kind", "expected_error"),
    [
        ("gate", "quality_gate_render_failed"),
        ("record", "quality_gate_record_failed"),
    ],
)
def test_guarded_rejected_initial_outputs_are_not_exposed(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_kind: str,
    expected_error: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client)
    monkeypatch.setattr(
        runner_module,
        "evaluate_selection_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="selection",
            outcome="pass",
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate_content_quality_gate",
        lambda **kwargs: _decision(
            str(kwargs["job_id"]),
            stage="content",
            outcome="pass",
        ),
    )
    if failure_kind == "gate":
        monkeypatch.setattr(
            runner_module,
            "evaluate_post_render_quality_gate",
            lambda **kwargs: _decision(
                str(kwargs["job_id"]),
                stage="post_render",
                outcome="fail",
            ),
        )
    else:
        actual_writer = runner_module._try_write_quality_gate_decision

        def reject_post_render_record(
            document: QualityGateDecision,
            output_path: Path,
        ) -> Path | None:
            if document.stage == "post_render":
                return None
            return actual_writer(document, output_path)

        monkeypatch.setattr(
            runner_module,
            "_try_write_quality_gate_decision",
            reject_post_render_record,
        )

    run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == expected_error
    results = client.get(f"/api/jobs/{job_id}/results").json()
    assert results["normalClips"] == []
    assert results["shorts"] == []
    with session_factory() as db:
        assert list(
            db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)).all()
        ) == []
    assert not (storage.job_outputs(job_id) / "normal" / "normal_01.mp4").exists()


@pytest.mark.parametrize("automation_mode", ["shadow", "guarded"])
def test_quality_gate_record_failure_keeps_existing_review_fallback(
    guarded_client: tuple[TestClient, StoragePaths, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    automation_mode: str,
) -> None:
    client, storage, session_factory = guarded_client
    job_id = _create_review_job(client, automation_mode=automation_mode)
    monkeypatch.setattr(
        runner_module,
        "_try_write_quality_gate_decision",
        lambda *_args, **_kwargs: None,
    )

    statuses = run_autoclipper_job(
        job_id,
        session_factory=session_factory,
        paths=storage,
        dependencies=_dependencies(tmp_path),
    )

    assert statuses[-1] == "awaiting_clip_review"
    assert not quality_gate_decision_path(
        storage.job_outputs(job_id),
        "selection",
    ).exists()
