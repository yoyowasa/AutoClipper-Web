from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.jobs.runner as runner_module
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import Base
from app.jobs.quality_gate import (
    QualityGateCheck,
    QualityGateDecision,
    load_quality_gate_decision,
    quality_gate_decision_path,
    write_quality_gate_decision,
)
from app.jobs.publication_state import (
    mark_rerender_publication_unresolved,
    rerender_publication_is_unresolved,
    rerender_publication_marker_path,
)
from app.jobs.runner import run_subtitle_review_render
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths


def _passing_post_render_decision(
    job_id: str,
    *,
    input_marker: str = "staging",
) -> QualityGateDecision:
    return QualityGateDecision(
        jobId=job_id,
        mode="guarded",
        enforced=True,
        stage="post_render",
        inputHash=hashlib.sha256(
            f"{job_id}:post_render:{input_marker}".encode()
        ).hexdigest(),
        outcome="pass",
        route="continue",
        checks=[
            QualityGateCheck(
                code="post_render.export_count",
                outcome="pass",
                evidence={"expected": 1, "actual": 1},
            )
        ],
        createdAt=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("failure_point", "preexisting_unresolved"),
    [
        ("record", False),
        ("promotion", False),
        ("rollback", False),
        ("promotion", True),
    ],
)
def test_guarded_rerender_failure_leaves_post_render_gate_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    preexisting_unresolved: bool,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    input_path = storage.uploads / "source.mp4"
    input_path.write_bytes(b"source")
    job_id = "job_guarded_rerender"

    with session_factory() as db:
        video = Video(
            id="video_guarded_rerender",
            original_filename="source.mp4",
            stored_path=str(input_path),
            duration=60,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        db.add(video)
        db.add(
            Job(
                id=job_id,
                video_id=video.id,
                status="rendering_normal_clips",
                settings_json={
                    "automationMode": "guarded",
                    "burnSubtitles": True,
                    "requireClipPlanReview": True,
                    "requireSubtitleReview": True,
                },
            )
        )
        db.commit()

    candidate = Candidate(
        id="candidate_normal_1",
        type="normal",
        start=0,
        end=60,
        duration=60,
        transcript_text="promotion failure test",
        title="promotion failure test",
        title_source="existing",
    )
    selection = CandidateSelection(
        normalClips=[candidate],
        requestedNormalCount=1,
    )
    job_dir = storage.job_outputs(job_id)
    preexisting_marker: bytes | None = None
    if preexisting_unresolved:
        marker_path = mark_rerender_publication_unresolved(
            job_dir,
            job_id=job_id,
            render_revision=1,
        )
        preexisting_marker = marker_path.read_bytes()
    write_selected_clips(selection, job_dir / "selected_clips.json")
    decision_path = quality_gate_decision_path(job_dir, "post_render")
    previous_decision = _passing_post_render_decision(
        job_id,
        input_marker="previous",
    )
    write_quality_gate_decision(
        previous_decision,
        decision_path,
    )

    review = SimpleNamespace(render_revision=2, state="render_queued")
    monkeypatch.setattr(runner_module, "load_subtitle_review", lambda _path: review)
    monkeypatch.setattr(runner_module, "mark_review_rendering", lambda document: document)
    monkeypatch.setattr(runner_module, "write_subtitle_review", lambda *_args: None)
    monkeypatch.setattr(runner_module, "write_subtitle_review_summary", lambda *_args: None)
    monkeypatch.setattr(runner_module, "_read_transcript_segments", lambda _path: [])
    monkeypatch.setattr(runner_module, "apply_reviewed_text", lambda segments, _review: segments)
    monkeypatch.setattr(runner_module, "write_transcript_segments", lambda *_args: None)
    monkeypatch.setattr(runner_module, "apply_reviewed_clip_content", lambda current, _review: current)
    monkeypatch.setattr(runner_module, "_active_quality_gate_mode", lambda *_args: "guarded")
    monkeypatch.setattr(
        runner_module,
        "evaluate_post_render_quality_gate",
        lambda **_kwargs: _passing_post_render_decision(
            job_id,
            input_marker="projected",
        ),
    )

    def fake_render_selected_outputs(**kwargs: Any) -> tuple[Any, Any, list[object], Path]:
        staging_dir = kwargs["storage_paths"].job_outputs(job_id)
        video_path = staging_dir / "normal" / "normal_01.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"staged")
        failures_path = staging_dir / "render_failures.json"
        failures_path.write_text("{}\n", encoding="utf-8")
        return (
            SimpleNamespace(exports=[], failures=[]),
            SimpleNamespace(exports=[], failures=[]),
            [
                SimpleNamespace(
                    id="export_staged",
                    candidate_id="candidate_normal_1",
                    type="normal",
                    video_path=str(video_path),
                )
            ],
            failures_path,
        )

    monkeypatch.setattr(
        runner_module,
        "_render_selected_outputs",
        fake_render_selected_outputs,
    )
    promotion_called = False

    def fail_promotion(**_kwargs: Any) -> tuple[list[object], Path]:
        nonlocal promotion_called
        promotion_called = True
        if failure_point == "rollback":
            raise runner_module._SubtitleRerenderRollbackError(
                "intentional rollback failure"
            )
        raise RuntimeError("intentional promotion failure")

    monkeypatch.setattr(
        runner_module,
        "_promote_subtitle_rerender",
        fail_promotion,
    )
    monkeypatch.setattr(
        runner_module,
        "_restore_subtitle_rerender_for_retry",
        lambda **_kwargs: None,
    )

    if failure_point == "record":
        actual_writer = runner_module._try_write_quality_gate_decision
        write_calls = 0

        def fail_first_gate_write(
            document: QualityGateDecision,
            output_path: Path,
        ) -> Path | None:
            nonlocal write_calls
            write_calls += 1
            if write_calls == 1:
                return None
            return actual_writer(document, output_path)

        monkeypatch.setattr(
            runner_module,
            "_try_write_quality_gate_decision",
            fail_first_gate_write,
        )
        run_subtitle_review_render(
            job_id,
            session_factory=session_factory,
            paths=storage,
        )
        assert promotion_called is False
    else:
        expected_message = (
            "intentional rollback failure"
            if failure_point == "rollback"
            else "intentional promotion failure"
        )
        with pytest.raises(RuntimeError, match=expected_message):
            run_subtitle_review_render(
                job_id,
                session_factory=session_factory,
                paths=storage,
            )
        assert promotion_called is True

    assert not decision_path.exists()
    staging_roots = list(
        (storage.temp / "rr").glob(f"{job_id[-12:]}_r2_*")
    )
    assert bool(staging_roots) is (failure_point == "rollback")
    assert rerender_publication_is_unresolved(job_dir) is (
        failure_point == "rollback" or preexisting_unresolved
    )
    if preexisting_marker is not None:
        assert rerender_publication_marker_path(job_dir).read_bytes() == (
            preexisting_marker
        )

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_guarded_rerender_hashes_projected_canonical_exports_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    input_path = storage.uploads / "source.mp4"
    input_path.write_bytes(b"source")
    job_id = "job_guarded_rerender"

    with session_factory() as db:
        video = Video(
            id="video_guarded_rerender",
            original_filename="source.mp4",
            stored_path=str(input_path),
            duration=60,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        db.add(video)
        db.add(
            Job(
                id=job_id,
                video_id=video.id,
                status="rendering_normal_clips",
                settings_json={
                    "automationMode": "guarded",
                    "burnSubtitles": True,
                    "requireClipPlanReview": True,
                    "requireSubtitleReview": True,
                },
            )
        )
        db.commit()

    candidate = Candidate(
        id="candidate_normal_1",
        type="normal",
        start=0,
        end=60,
        duration=60,
        transcript_text="promotion success test",
        title="promotion success test",
        title_source="existing",
    )
    selection = CandidateSelection(
        normalClips=[candidate],
        requestedNormalCount=1,
    )
    job_dir = storage.job_outputs(job_id)
    write_selected_clips(selection, job_dir / "selected_clips.json")
    decision_path = quality_gate_decision_path(job_dir, "post_render")
    previous_decision = _passing_post_render_decision(
        job_id,
        input_marker="stale",
    )
    write_quality_gate_decision(
        previous_decision,
        decision_path,
    )

    review = SimpleNamespace(render_revision=2, state="render_queued")
    monkeypatch.setattr(runner_module, "load_subtitle_review", lambda _path: review)
    monkeypatch.setattr(runner_module, "mark_review_rendering", lambda document: document)
    monkeypatch.setattr(runner_module, "write_subtitle_review", lambda *_args: None)
    monkeypatch.setattr(runner_module, "write_subtitle_review_summary", lambda *_args: None)
    monkeypatch.setattr(runner_module, "_read_transcript_segments", lambda _path: [])
    monkeypatch.setattr(runner_module, "apply_reviewed_text", lambda segments, _review: segments)
    monkeypatch.setattr(runner_module, "write_transcript_segments", lambda *_args: None)
    monkeypatch.setattr(runner_module, "apply_reviewed_clip_content", lambda current, _review: current)
    monkeypatch.setattr(runner_module, "_active_quality_gate_mode", lambda *_args: "guarded")

    def fake_render_selected_outputs(**kwargs: Any) -> tuple[Any, Any, list[object], Path]:
        staging_dir = kwargs["storage_paths"].job_outputs(job_id)
        video_path = staging_dir / "normal" / "normal_01.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"staged")
        failures_path = staging_dir / "render_failures.json"
        failures_path.write_text("{}\n", encoding="utf-8")
        return (
            SimpleNamespace(exports=[], failures=[]),
            SimpleNamespace(exports=[], failures=[]),
            [
                SimpleNamespace(
                    id="export_staged",
                    candidate_id="candidate_normal_1",
                    type="normal",
                    video_path=str(video_path),
                )
            ],
            failures_path,
        )

    monkeypatch.setattr(
        runner_module,
        "_render_selected_outputs",
        fake_render_selected_outputs,
    )
    evaluated_paths: list[str] = []

    def evaluate_gate(**kwargs: Any) -> QualityGateDecision:
        video_path = str(kwargs["exports"][0]["videoPath"])
        evaluated_paths.append(video_path)
        return _passing_post_render_decision(job_id, input_marker=video_path)

    monkeypatch.setattr(
        runner_module,
        "evaluate_post_render_quality_gate",
        evaluate_gate,
    )

    class StopAfterProjection(RuntimeError):
        pass

    published_hashes: list[str] = []

    def promote(**_kwargs: Any) -> tuple[list[object], Path]:
        published_hashes.append(
            load_quality_gate_decision(decision_path).input_hash
        )
        raise StopAfterProjection("stop after projected gate was published")

    monkeypatch.setattr(runner_module, "_promote_subtitle_rerender", promote)
    monkeypatch.setattr(
        runner_module,
        "_restore_subtitle_rerender_for_retry",
        lambda **_kwargs: None,
    )

    with pytest.raises(
        StopAfterProjection,
        match="stop after projected gate was published",
    ):
        run_subtitle_review_render(
            job_id,
            session_factory=session_factory,
            paths=storage,
        )

    expected_path = str(storage.job_outputs(job_id) / "normal" / "normal_01.mp4")
    assert evaluated_paths == [expected_path]
    canonical_decision = _passing_post_render_decision(
        job_id,
        input_marker=expected_path,
    )
    assert published_hashes == [canonical_decision.input_hash]
    assert not decision_path.exists()

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_partial_rerender_promotion_restores_old_files_and_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    job_id = "job_partial_promotion"
    canonical_dir = storage.job_outputs(job_id)
    staging_paths = runner_module._prepare_subtitle_rerender_staging(
        storage,
        job_id,
        2,
    )
    staging_dir = staging_paths.job_outputs(job_id)

    canonical_video = canonical_dir / "normal" / "normal_01.mp4"
    canonical_subtitle = canonical_dir / "subtitles" / "normal" / "normal_01.ass"
    canonical_metadata = canonical_dir / "normal" / "normal_01.json"
    canonical_failures = canonical_dir / "render_failures.json"
    staged_video = staging_dir / "normal" / "normal_01.mp4"
    staged_subtitle = staging_dir / "subtitles" / "normal" / "normal_01.ass"
    staged_metadata = staging_dir / "normal" / "normal_01.json"
    staged_failures = staging_dir / "render_failures.json"
    for path in (
        canonical_video,
        canonical_metadata,
        canonical_failures,
        staged_video,
        staged_subtitle,
        staged_metadata,
        staged_failures,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    canonical_video.write_bytes(b"old-video")
    canonical_metadata.write_text('{"version":"old"}\n', encoding="utf-8")
    canonical_failures.write_bytes(b"old-failures")
    staged_video.write_bytes(b"new-video")
    staged_subtitle.write_bytes(b"new-subtitle")
    staged_metadata.write_text('{"version":"new"}\n', encoding="utf-8")
    staged_failures.write_bytes(b"new-failures")

    with session_factory() as db:
        video = Video(
            id="video_partial_promotion",
            original_filename="source.mp4",
            stored_path=str(storage.uploads / "source.mp4"),
            duration=60,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="rendering_normal_clips",
            settings_json={},
        )
        previous = ExportItem(
            id="export_previous",
            job_id=job_id,
            video_id=video.id,
            candidate_id="candidate_1",
            type="normal",
            title="old",
            duration=60,
            score=1,
            video_path=str(canonical_video),
            subtitle_path=None,
            metadata_path=str(canonical_metadata),
        )
        staged = ExportItem(
            id="export_staged",
            job_id=job_id,
            video_id=video.id,
            candidate_id="candidate_1",
            type="normal",
            title="new",
            duration=60,
            score=1,
            video_path=str(staged_video),
            subtitle_path=str(staged_subtitle),
            metadata_path=str(staged_metadata),
        )
        db.add_all([video, job, previous, staged])
        db.commit()

        original_replace = Path.replace
        failed_source = staged_metadata.resolve()

        def fail_metadata_promotion(self: Path, target: Path) -> Path:
            if self.resolve(strict=False) == failed_source:
                raise OSError("intentional partial promotion failure")
            return original_replace(self, target)

        monkeypatch.setattr(Path, "replace", fail_metadata_promotion)
        with pytest.raises(OSError, match="intentional partial promotion failure"):
            runner_module._promote_subtitle_rerender(
                db=db,
                job=job,
                previous_exports=[previous],
                staged_exports=[staged],
                staged_render_failures_path=staged_failures,
                staging_paths=staging_paths,
                storage_paths=storage,
            )

        assert canonical_video.read_bytes() == b"old-video"
        assert not canonical_subtitle.exists()
        assert canonical_metadata.read_text(encoding="utf-8") == '{"version":"old"}\n'
        assert canonical_failures.read_bytes() == b"old-failures"
        rows = list(
            db.scalars(
                runner_module.select(ExportItem).where(ExportItem.job_id == job_id)
            ).all()
        )
        assert {row.id for row in rows} == {"export_previous", "export_staged"}
        assert next(row for row in rows if row.id == "export_previous").video_path == str(
            canonical_video
        )
        assert next(row for row in rows if row.id == "export_staged").video_path == str(
            staged_video
        )

        runner_module._discard_subtitle_rerender_staging(
            db=db,
            job_id=job_id,
            previous_export_ids={previous.id},
            staging_paths=staging_paths,
        )
        remaining = list(
            db.scalars(
                runner_module.select(ExportItem).where(ExportItem.job_id == job_id)
            ).all()
        )
        assert [row.id for row in remaining] == ["export_previous"]

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_rerender_promotion_rolls_back_zip_with_media(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    staging_dir = tmp_path / "staging"
    canonical_video = canonical_dir / "normal" / "normal_01.mp4"
    staged_video = staging_dir / "normal" / "normal_01.mp4"
    canonical_zip = canonical_dir / "download.zip"
    pending_zip = canonical_dir / ".download.tmp.zip"
    for path in (canonical_video, staged_video, canonical_zip, pending_zip):
        path.parent.mkdir(parents=True, exist_ok=True)
    canonical_video.write_bytes(b"old-video")
    staged_video.write_bytes(b"new-video")
    canonical_zip.write_bytes(b"old-zip")
    pending_zip.write_bytes(b"new-zip")
    promotion = runner_module._SubtitleRerenderPromotion(
        staging_root=staging_dir,
        canonical_job_dir=canonical_dir,
        changes=[],
    )

    promotion.publish(staged_video, canonical_video)
    promotion.publish(pending_zip, canonical_zip)
    assert canonical_video.read_bytes() == b"new-video"
    assert canonical_zip.read_bytes() == b"new-zip"

    promotion.rollback()

    assert canonical_video.read_bytes() == b"old-video"
    assert canonical_zip.read_bytes() == b"old-zip"
    assert promotion.backup_root.exists()
