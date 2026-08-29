import os
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audio.transcribe_faster_whisper import (
    TranscriptSegment,
    transcript_output_path,
    write_transcript_segments,
)
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import Base
from app.jobs.runner import (
    AutoClipperPipelineDependencies,
    run_subtitle_review_hook_scene_update,
    run_subtitle_review_preview,
)
from app.jobs.subtitle_review import (
    build_subtitle_review,
    load_subtitle_review,
    subtitle_review_output_path,
    update_review_clip_content,
    write_subtitle_review,
    write_subtitle_review_summary,
    subtitle_review_summary_path,
)
from app.jobs.subtitle_review_preview import (
    cleanup_stale_subtitle_review_preview_artifacts,
    current_subtitle_review_preview_spec,
    exact_subtitle_review_preview_is_ready,
    exact_subtitle_review_preview_error_path,
    subtitle_review_document_lock,
)
from app.models import Job, Video
from app.render.render_exact_review_preview import (
    ExactPreviewResult,
    build_live_subtitle_review_preview_spec,
    build_subtitle_review_preview_spec,
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
    subtitle_review_preview_spec_hash,
)
from app.storage.paths import StoragePaths


def test_preview_ready_requires_spec_payload_to_match_full_hash(tmp_path: Path) -> None:
    spec = {"rendererVersion": "test", "clip": {"id": "candidate_spec"}}
    spec_hash = subtitle_review_preview_spec_hash(spec)
    paths = exact_subtitle_review_preview_paths(
        tmp_path,
        "candidate_spec",
        spec_hash,
    )
    paths.video_path.parent.mkdir(parents=True, exist_ok=True)
    paths.video_path.write_bytes(b"video")
    paths.subtitle_path.write_text("ass", encoding="utf-8")
    paths.spec_path.write_text("{}", encoding="utf-8")

    assert not exact_subtitle_review_preview_is_ready(paths, spec_hash)

    paths.spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert exact_subtitle_review_preview_is_ready(paths, spec_hash)


def test_preview_cleanup_retains_current_and_latest_previous_artifact_set(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "job"
    clip_id = "candidate_cleanup"
    hashes = {"current": "a" * 64, "previous": "b" * 64, "stale": "c" * 64}
    artifact_sets = {
        name: exact_subtitle_review_preview_paths(output_dir, clip_id, spec_hash)
        for name, spec_hash in hashes.items()
    }
    for name, paths in artifact_sets.items():
        paths.video_path.parent.mkdir(parents=True, exist_ok=True)
        paths.video_path.write_bytes(name.encode("ascii"))
        paths.subtitle_path.write_text(name, encoding="utf-8")
        paths.spec_path.write_text("{}", encoding="utf-8")
        error_path = exact_subtitle_review_preview_error_path(
            output_dir,
            clip_id,
            hashes[name],
        )
        error_path.write_text("{}", encoding="utf-8")
        timestamp_ns = {
            "stale": 1_000_000_000,
            "previous": 2_000_000_000,
            "current": 3_000_000_000,
        }[name]
        for artifact_path in (
            paths.video_path,
            paths.subtitle_path,
            paths.spec_path,
            error_path,
        ):
            os.utime(artifact_path, ns=(timestamp_ns, timestamp_ns))

    preview_dir = artifact_sets["current"].video_path.parent
    render_temp = preview_dir / ".render-active.tmp.mp4"
    error_temp = preview_dir / ".error-active.tmp"
    render_temp.write_bytes(b"rendering")
    error_temp.write_bytes(b"writing error")

    cleanup_stale_subtitle_review_preview_artifacts(
        output_dir,
        clip_id,
        hashes["current"],
    )

    for name in ("current", "previous"):
        paths = artifact_sets[name]
        assert paths.video_path.is_file()
        assert paths.subtitle_path.is_file()
        assert paths.spec_path.is_file()
        assert exact_subtitle_review_preview_error_path(
            output_dir,
            clip_id,
            hashes[name],
        ).is_file()
    stale_paths = artifact_sets["stale"]
    assert not stale_paths.video_path.exists()
    assert not stale_paths.subtitle_path.exists()
    assert not stale_paths.spec_path.exists()
    assert not exact_subtitle_review_preview_error_path(
        output_dir,
        clip_id,
        hashes["stale"],
    ).exists()
    assert render_temp.is_file()
    assert error_temp.is_file()


def test_preview_worker_never_overwrites_a_concurrent_api_edit(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source_path = storage.uploads / "source.mp4"
    source_path.write_bytes(b"source")
    job_id = "job_preview_race"
    clip_id = "candidate_normal_race"
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        id=clip_id,
        type="normal",
        start=0,
        end=20,
        duration=20,
        transcript_text="元の字幕",
        title="元のタイトル",
    )
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    segments = [
        TranscriptSegment(start=0, end=20, text="元の字幕", confidence=0.9)
    ]
    write_selected_clips(selection, output_dir / "selected_clips.json")
    write_transcript_segments(segments, transcript_output_path(output_dir))

    with session_factory() as db:
        video = Video(
            id="vid_preview_race",
            original_filename="source.mp4",
            stored_path=str(source_path),
            duration=20,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="awaiting_subtitle_review",
            progress=72,
            current_step="字幕確認",
            settings_json={"burnSubtitles": True},
        )
        db.add_all([video, job])
        db.commit()
        document = build_subtitle_review(job_id, selection, segments)
        old_spec, old_hash, _inputs = current_subtitle_review_preview_spec(
            job=job,
            video=video,
            document=document,
            paths=storage,
            clip_id=clip_id,
        )
        document.clips[0].preview_spec_hash = old_hash
        write_subtitle_review(document, subtitle_review_output_path(output_dir))
        write_subtitle_review_summary(
            document,
            subtitle_review_summary_path(output_dir),
        )

    concurrent_hash: str | None = None

    def fake_exact_renderer(
        _input_path: str | Path,
        renderer_output_dir: str | Path,
        **_kwargs: Any,
    ) -> ExactPreviewResult:
        nonlocal concurrent_hash
        latest = load_subtitle_review(subtitle_review_output_path(output_dir))
        latest = update_review_clip_content(
            latest,
            clip_id,
            title="APIで同時に変更したタイトル",
        )
        with session_factory() as db:
            current_job = db.get(Job, job_id)
            assert current_job is not None
            current_video = db.get(Video, current_job.video_id)
            assert current_video is not None
            _concurrent_spec, concurrent_hash, _inputs = (
                current_subtitle_review_preview_spec(
                    job=current_job,
                    video=current_video,
                    document=latest,
                    paths=storage,
                    clip_id=clip_id,
                )
            )
        latest.clips[0].preview_state = "queued"
        latest.clips[0].preview_spec_hash = concurrent_hash
        latest.clips[0].preview_video_url = None
        write_subtitle_review(latest, subtitle_review_output_path(output_dir))

        artifacts = exact_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            old_hash,
        )
        artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts.video_path.write_bytes(b"old preview")
        artifacts.subtitle_path.write_text("old ass", encoding="utf-8")
        artifacts.spec_path.write_text(
            json.dumps(old_spec, ensure_ascii=False),
            encoding="utf-8",
        )
        live_spec = build_live_subtitle_review_preview_spec(old_spec)
        live_spec_hash = subtitle_review_preview_spec_hash(live_spec)
        live_artifacts = live_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            live_spec_hash,
        )
        live_artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        live_artifacts.video_path.write_bytes(b"old live preview")
        live_artifacts.spec_path.write_text(
            json.dumps(live_spec, ensure_ascii=False),
            encoding="utf-8",
        )
        return ExactPreviewResult(
            path=artifacts.video_path,
            subtitle_path=artifacts.subtitle_path,
            spec_path=artifacts.spec_path,
            spec_hash=old_hash,
            live_path=live_artifacts.video_path,
            live_spec_path=live_artifacts.spec_path,
            live_spec_hash=live_spec_hash,
        )

    statuses = run_subtitle_review_preview(
        job_id,
        clip_id,
        old_hash,
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            subtitle_review_exact_preview_renderer=fake_exact_renderer,
        ),
    )

    assert statuses == ["ready"]
    persisted = load_subtitle_review(subtitle_review_output_path(output_dir))
    assert persisted.clips[0].title == "APIで同時に変更したタイトル"
    assert persisted.clips[0].preview_state == "queued"
    assert persisted.clips[0].preview_spec_hash == concurrent_hash
    assert persisted.clips[0].preview_spec_hash != old_hash


def test_auto_preview_worker_queues_render_after_confirmed_preview_becomes_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auto.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source_path = storage.uploads / "source.mp4"
    source_path.write_bytes(b"source")
    job_id = "job_auto_preview_resume"
    clip_id = "candidate_auto_confirmed"
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        id=clip_id,
        type="normal",
        start=0,
        end=20,
        duration=20,
        transcript_text="確認済み字幕",
        title="確認済みタイトル",
    )
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    segments = [
        TranscriptSegment(start=0, end=20, text="確認済み字幕", confidence=0.1)
    ]
    write_selected_clips(selection, output_dir / "selected_clips.json")
    write_transcript_segments(segments, transcript_output_path(output_dir))

    with session_factory() as db:
        video = Video(
            id="vid_auto_preview_resume",
            original_filename="source.mp4",
            stored_path=str(source_path),
            duration=20,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="awaiting_subtitle_review",
            progress=80,
            current_step="字幕確認",
            settings_json={"automationMode": "auto", "burnSubtitles": True},
        )
        db.add_all([video, job])
        db.commit()
        document = build_subtitle_review(job_id, selection, segments)
        spec, spec_hash, _inputs = current_subtitle_review_preview_spec(
            job=job,
            video=video,
            document=document,
            paths=storage,
            clip_id=clip_id,
        )
        document.clips[0].confirmed = True
        document.clips[0].preview_state = "queued"
        document.clips[0].preview_spec_hash = spec_hash
        document.confirmed_clip_count = 1
        write_subtitle_review(document, subtitle_review_output_path(output_dir))
        write_subtitle_review_summary(
            document,
            subtitle_review_summary_path(output_dir),
        )

    def fake_exact_renderer(
        _input_path: str | Path,
        renderer_output_dir: str | Path,
        **_kwargs: Any,
    ) -> ExactPreviewResult:
        artifacts = exact_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            spec_hash,
        )
        artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts.video_path.write_bytes(b"exact preview")
        artifacts.subtitle_path.write_text("ass", encoding="utf-8")
        artifacts.spec_path.write_text(
            json.dumps(spec, ensure_ascii=False),
            encoding="utf-8",
        )
        live_spec = build_live_subtitle_review_preview_spec(spec)
        live_hash = subtitle_review_preview_spec_hash(live_spec)
        live_artifacts = live_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            live_hash,
        )
        live_artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        live_artifacts.video_path.write_bytes(b"live preview")
        live_artifacts.spec_path.write_text(
            json.dumps(live_spec, ensure_ascii=False),
            encoding="utf-8",
        )
        return ExactPreviewResult(
            path=artifacts.video_path,
            subtitle_path=artifacts.subtitle_path,
            spec_path=artifacts.spec_path,
            spec_hash=spec_hash,
            live_path=live_artifacts.video_path,
            live_spec_path=live_artifacts.spec_path,
            live_spec_hash=live_hash,
        )

    queued: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_subtitle_review_render",
        lambda queued_job_id, revision: queued.append((queued_job_id, revision)),
    )

    statuses = run_subtitle_review_preview(
        job_id,
        clip_id,
        spec_hash,
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            subtitle_review_exact_preview_renderer=fake_exact_renderer,
        ),
    )

    assert statuses == ["ready", "render_queued"]
    persisted = load_subtitle_review(subtitle_review_output_path(output_dir))
    assert persisted.state == "render_queued"
    assert persisted.clips[0].preview_state == "ready"
    assert persisted.confirmed_clip_count == 1
    assert queued == [(job_id, persisted.render_revision)]
    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.status == "rendering_normal_clips"


def test_hook_preview_worker_rejects_changed_review_snapshot(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source_path = storage.uploads / "source.mp4"
    source_path.write_bytes(b"source")
    job_id = "job_hook_preview_race"
    clip_id = "candidate_short_race"
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        id=clip_id,
        type="short",
        start=0,
        end=10,
        duration=10,
        transcript_text="元の字幕",
        title="元のタイトル",
    )
    selection = CandidateSelection(normalClips=[], shorts=[candidate])
    segments = [
        TranscriptSegment(start=0, end=10, text="元の字幕", confidence=0.9)
    ]
    selected_path = output_dir / "selected_clips.json"
    write_selected_clips(selection, selected_path)
    write_transcript_segments(segments, transcript_output_path(output_dir))

    with session_factory() as db:
        video = Video(
            id="vid_hook_preview_race",
            original_filename="source.mp4",
            stored_path=str(source_path),
            duration=10,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="preparing_subtitle_review",
            progress=70,
            current_step="冒頭フック映像を準備中",
            settings_json={"burnSubtitles": True, "shortMaxDuration": 75},
        )
        db.add_all([video, job])
        db.commit()
    document = build_subtitle_review(job_id, selection, segments)
    write_subtitle_review(document, subtitle_review_output_path(output_dir))
    write_subtitle_review_summary(document, subtitle_review_summary_path(output_dir))

    def fake_exact_renderer(
        _input_path: str | Path,
        renderer_output_dir: str | Path,
        **kwargs: Any,
    ) -> ExactPreviewResult:
        with subtitle_review_document_lock(output_dir):
            latest = load_subtitle_review(subtitle_review_output_path(output_dir))
            latest = update_review_clip_content(
                latest,
                clip_id,
                title="描画中に保存されたタイトル",
            )
            write_subtitle_review(latest, subtitle_review_output_path(output_dir))
            write_subtitle_review_summary(
                latest,
                subtitle_review_summary_path(output_dir),
            )
        spec = build_subtitle_review_preview_spec(
            candidate=kwargs["candidate"],
            transcript_segments=kwargs["transcript_segments"],
            settings=kwargs["settings"],
            source_fingerprint=kwargs["source_fingerprint"],
            source_width=kwargs["source_width"],
            source_height=kwargs["source_height"],
            candidate_index=kwargs["candidate_index"],
            overlay_title_expected=kwargs["overlay_title_expected"],
        )
        spec_hash = subtitle_review_preview_spec_hash(spec)
        artifacts = exact_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            spec_hash,
        )
        artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts.video_path.write_bytes(b"hook preview")
        artifacts.subtitle_path.write_text("ass", encoding="utf-8")
        artifacts.spec_path.write_text(json.dumps(spec), encoding="utf-8")
        live_spec = build_live_subtitle_review_preview_spec(spec)
        live_spec_hash = subtitle_review_preview_spec_hash(live_spec)
        live_artifacts = live_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            live_spec_hash,
        )
        live_artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        live_artifacts.video_path.write_bytes(b"hook live preview")
        live_artifacts.spec_path.write_text(json.dumps(live_spec), encoding="utf-8")
        return ExactPreviewResult(
            path=artifacts.video_path,
            subtitle_path=artifacts.subtitle_path,
            spec_path=artifacts.spec_path,
            spec_hash=spec_hash,
            live_path=live_artifacts.video_path,
            live_spec_path=live_artifacts.spec_path,
            live_spec_hash=live_spec_hash,
        )

    with pytest.raises(
        RuntimeError,
        match="subtitle review changed while hook preview was rendering",
    ):
        run_subtitle_review_hook_scene_update(
            job_id,
            clip_id,
            1,
            3,
            session_factory=session_factory,
            paths=storage,
            dependencies=AutoClipperPipelineDependencies(
                subtitle_review_exact_preview_renderer=fake_exact_renderer,
            ),
        )

    persisted = load_subtitle_review(subtitle_review_output_path(output_dir))
    assert persisted.clips[0].title == "描画中に保存されたタイトル"
    stored_selection = CandidateSelection.model_validate(
        json.loads(selected_path.read_text(encoding="utf-8"))
    )
    assert stored_selection.shorts[0].hook_scene_start is None
    assert stored_selection.shorts[0].hook_scene_end is None
    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.status == "awaiting_subtitle_review"


def test_hook_preview_worker_updates_normal_selection(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source_path = storage.uploads / "source.mp4"
    source_path.write_bytes(b"source")
    job_id = "job_normal_hook_preview"
    clip_id = "candidate_normal_hook"
    output_dir = storage.job_outputs(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        id=clip_id,
        type="normal",
        start=0,
        end=20,
        duration=20,
        transcript_text="通常切り抜き",
        title="通常タイトル",
    )
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    segments = [TranscriptSegment(start=0, end=20, text="通常字幕", confidence=0.9)]
    selected_path = output_dir / "selected_clips.json"
    write_selected_clips(selection, selected_path)
    write_transcript_segments(segments, transcript_output_path(output_dir))
    document = build_subtitle_review(job_id, selection, segments)
    write_subtitle_review(document, subtitle_review_output_path(output_dir))
    write_subtitle_review_summary(document, subtitle_review_summary_path(output_dir))

    with session_factory() as db:
        video = Video(
            id="vid_normal_hook_preview",
            original_filename="source.mp4",
            stored_path=str(source_path),
            duration=20,
            width=1920,
            height=1080,
            fps=30,
            has_audio=True,
        )
        job = Job(
            id=job_id,
            video_id=video.id,
            status="preparing_subtitle_review",
            progress=70,
            current_step="冒頭フック映像を準備中",
            settings_json={"burnSubtitles": True, "shortMaxDuration": 1},
        )
        db.add_all([video, job])
        db.commit()

    def fake_exact_renderer(
        _input_path: str | Path,
        renderer_output_dir: str | Path,
        **kwargs: Any,
    ) -> ExactPreviewResult:
        spec = build_subtitle_review_preview_spec(
            candidate=kwargs["candidate"],
            transcript_segments=kwargs["transcript_segments"],
            settings=kwargs["settings"],
            source_fingerprint=kwargs["source_fingerprint"],
            source_width=kwargs["source_width"],
            source_height=kwargs["source_height"],
            candidate_index=kwargs["candidate_index"],
            overlay_title_expected=kwargs["overlay_title_expected"],
        )
        spec_hash = subtitle_review_preview_spec_hash(spec)
        artifacts = exact_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            spec_hash,
        )
        artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        artifacts.video_path.write_bytes(b"normal hook preview")
        artifacts.subtitle_path.write_text("ass", encoding="utf-8")
        artifacts.spec_path.write_text(json.dumps(spec), encoding="utf-8")
        live_spec = build_live_subtitle_review_preview_spec(spec)
        live_spec_hash = subtitle_review_preview_spec_hash(live_spec)
        live_artifacts = live_subtitle_review_preview_paths(
            renderer_output_dir,
            clip_id,
            live_spec_hash,
        )
        live_artifacts.video_path.parent.mkdir(parents=True, exist_ok=True)
        live_artifacts.video_path.write_bytes(b"normal hook live preview")
        live_artifacts.spec_path.write_text(json.dumps(live_spec), encoding="utf-8")
        return ExactPreviewResult(
            path=artifacts.video_path,
            subtitle_path=artifacts.subtitle_path,
            spec_path=artifacts.spec_path,
            spec_hash=spec_hash,
            live_path=live_artifacts.video_path,
            live_spec_path=live_artifacts.spec_path,
            live_spec_hash=live_spec_hash,
        )

    statuses = run_subtitle_review_hook_scene_update(
        job_id,
        clip_id,
        5,
        7,
        session_factory=session_factory,
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            subtitle_review_exact_preview_renderer=fake_exact_renderer,
        ),
    )

    assert statuses == ["preparing_subtitle_review", "awaiting_subtitle_review"]
    persisted = load_subtitle_review(subtitle_review_output_path(output_dir))
    assert persisted.clips[0].hook_scene_start == 5
    assert persisted.clips[0].hook_scene_end == 7
    stored_selection = CandidateSelection.model_validate(
        json.loads(selected_path.read_text(encoding="utf-8"))
    )
    assert stored_selection.normal_clips[0].hook_scene_start == 5
    assert stored_selection.normal_clips[0].hook_scene_end == 7
