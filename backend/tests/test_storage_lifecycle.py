from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ExportItem, Job, Video
from app.storage.lifecycle import (
    _claim_expired_jobs,
    _delete_orphan_videos,
    cleanup_expired_storage,
    count_cleanup_eligible_jobs,
    count_cleanup_eligible_videos,
)
from app.storage.paths import StoragePaths
from app.video.heatmap import heatmap_sidecar_path


NOW = datetime(2026, 8, 28, 12, 0, 0)


@pytest.fixture()
def storage_session(tmp_path: Path) -> tuple[StoragePaths, Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    session = Session(engine)
    try:
        yield storage, session
    finally:
        session.close()
        engine.dispose()


def _add_video(
    session: Session,
    storage: StoragePaths,
    video_id: str,
    *,
    created_at: datetime,
) -> tuple[Video, Path]:
    upload_path = storage.uploads / f"{video_id}.mp4"
    upload_path.write_bytes(f"source:{video_id}".encode())
    heatmap_sidecar_path(upload_path).write_text("{}", encoding="utf-8")
    video = Video(
        id=video_id,
        original_filename=f"{video_id}.mp4",
        stored_path=str(upload_path),
        created_at=created_at,
    )
    session.add(video)
    return video, upload_path


def _add_job(
    session: Session,
    storage: StoragePaths,
    video: Video,
    job_id: str,
    *,
    status: str,
    updated_at: datetime,
    with_export: bool = True,
) -> tuple[Job, Path, Path]:
    job = Job(
        id=job_id,
        video_id=video.id,
        status=status,
        progress=100 if status in {"completed", "failed"} else 50,
        current_step=status,
        settings_json={},
        created_at=updated_at,
        updated_at=updated_at,
    )
    session.add(job)
    output_dir = storage.outputs / job_id
    output_dir.mkdir(parents=True)
    output_path = output_dir / "result.mp4"
    output_path.write_bytes(b"rendered")
    temp_dir = storage.temp / job_id
    temp_dir.mkdir(parents=True)
    (temp_dir / "audio.wav").write_bytes(b"temporary")
    if with_export:
        session.add(
            ExportItem(
                id=f"exp_{job_id}",
                job_id=job_id,
                video_id=video.id,
                candidate_id=None,
                type="short",
                title=job_id,
                duration=1.0,
                score=1.0,
                video_path=str(output_path),
                subtitle_path=None,
                metadata_path=None,
                created_at=updated_at,
            )
        )
    return job, output_dir, temp_dir


def _count(session: Session, model: type[Video] | type[Job] | type[ExportItem]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_cleanup_removes_expired_completed_and_failed_jobs(storage_session: tuple[StoragePaths, Session]) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=10)
    targets: list[Path] = []
    for suffix, status in (("completed", "completed"), ("failed", "failed")):
        video, upload_path = _add_video(session, storage, f"vid_{suffix}", created_at=old)
        _job, output_dir, temp_dir = _add_job(
            session,
            storage,
            video,
            f"job_{suffix}",
            status=status,
            updated_at=old,
        )
        targets.extend((upload_path, heatmap_sidecar_path(upload_path), output_dir, temp_dir))
    session.commit()

    assert count_cleanup_eligible_jobs(session, 7, NOW) == 2
    assert count_cleanup_eligible_videos(session, 7, 24, NOW) == 2
    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 2
    assert result.removed_videos == 2
    assert result.removed_files == 8
    assert result.errors == ()
    assert _count(session, Job) == 0
    assert _count(session, ExportItem) == 0
    assert _count(session, Video) == 0
    assert all(not path.exists() for path in targets)


def test_cleanup_keeps_recent_and_nonterminal_jobs(storage_session: tuple[StoragePaths, Session]) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=30)
    cases = (
        ("recent", "completed", NOW - timedelta(days=1)),
        ("awaiting", "awaiting_subtitle_review", old),
        ("running", "rendering_shorts", old),
    )
    target_paths: list[Path] = []
    for suffix, status, updated_at in cases:
        video, upload_path = _add_video(session, storage, f"vid_{suffix}", created_at=old)
        _job, output_dir, temp_dir = _add_job(
            session,
            storage,
            video,
            f"job_{suffix}",
            status=status,
            updated_at=updated_at,
        )
        target_paths.extend((upload_path, output_dir, temp_dir))
    session.commit()

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 0
    assert result.removed_videos == 0
    assert result.removed_files == 0
    assert result.errors == ()
    assert _count(session, Job) == 3
    assert _count(session, ExportItem) == 3
    assert _count(session, Video) == 3
    assert all(path.exists() for path in target_paths)


def test_cleanup_keeps_video_shared_with_nonterminal_job(storage_session: tuple[StoragePaths, Session]) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=10)
    video, upload_path = _add_video(session, storage, "vid_shared", created_at=old)
    _expired, expired_output, expired_temp = _add_job(
        session,
        storage,
        video,
        "job_expired",
        status="completed",
        updated_at=old,
    )
    _active, active_output, active_temp = _add_job(
        session,
        storage,
        video,
        "job_active",
        status="awaiting_clip_review",
        updated_at=old,
    )
    session.commit()

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 1
    assert result.removed_videos == 0
    assert result.removed_files == 2
    assert result.errors == ()
    assert session.get(Job, "job_expired") is None
    assert session.get(Job, "job_active") is not None
    assert session.get(Video, video.id) is not None
    assert upload_path.exists()
    assert not expired_output.exists()
    assert not expired_temp.exists()
    assert active_output.exists()
    assert active_temp.exists()


def test_cleanup_removes_only_expired_orphan_video(storage_session: tuple[StoragePaths, Session]) -> None:
    storage, session = storage_session
    old_video, old_path = _add_video(
        session,
        storage,
        "vid_old_orphan",
        created_at=NOW - timedelta(hours=25),
    )
    recent_video, recent_path = _add_video(
        session,
        storage,
        "vid_recent_orphan",
        created_at=NOW - timedelta(hours=23),
    )
    session.commit()
    old_video_id = old_video.id
    recent_video_id = recent_video.id

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 0
    assert result.removed_videos == 1
    assert result.removed_files == 2
    assert result.errors == ()
    assert session.get(Video, old_video_id) is None
    assert session.get(Video, recent_video_id) is not None
    assert not old_path.exists()
    assert not heatmap_sidecar_path(old_path).exists()
    assert recent_path.exists()


def test_cleanup_refuses_video_path_outside_storage_root(
    storage_session: tuple[StoragePaths, Session],
    tmp_path: Path,
) -> None:
    storage, session = storage_session
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"must survive")
    video = Video(
        id="vid_outside",
        original_filename=outside.name,
        stored_path=str(outside),
        created_at=NOW - timedelta(days=2),
    )
    session.add(video)
    session.commit()

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_videos == 1
    assert result.removed_files == 0
    assert len(result.errors) == 2
    assert all("outside storage root" in error for error in result.errors)
    assert outside.exists()


def test_cleanup_prunes_canonical_blob_after_last_video_reference_is_removed(
    storage_session: tuple[StoragePaths, Session],
) -> None:
    storage, session = storage_session
    blob_dir = storage.uploads / ".blobs" / "ab"
    blob_dir.mkdir(parents=True)
    blob = blob_dir / "abcdef"
    blob.write_bytes(b"shared source")
    sidecar = storage.video_heatmap("vid_blob_orphan")
    sidecar.write_text("{}", encoding="utf-8")
    session.add(
        Video(
            id="vid_blob_orphan",
            original_filename="source.mp4",
            stored_path=str(blob),
            created_at=NOW - timedelta(days=2),
        )
    )
    session.commit()

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_videos == 1
    assert result.removed_files == 2
    assert result.errors == ()
    assert not blob.exists()
    assert not sidecar.exists()


def test_cleanup_keeps_canonical_blob_referenced_by_remaining_video(
    storage_session: tuple[StoragePaths, Session],
) -> None:
    storage, session = storage_session
    blob_dir = storage.uploads / ".blobs" / "cd"
    blob_dir.mkdir(parents=True)
    blob = blob_dir / "cdef"
    blob.write_bytes(b"active source")
    video = Video(
        id="vid_blob_direct",
        original_filename="active.mp4",
        stored_path=str(blob),
        created_at=NOW - timedelta(days=30),
    )
    session.add(video)
    session.add(
        Video(
            id="vid_blob_orphan_shared",
            original_filename="orphan.mp4",
            stored_path=str(blob),
            created_at=NOW - timedelta(days=30),
        )
    )
    orphan_sidecar = storage.video_heatmap("vid_blob_orphan_shared")
    orphan_sidecar.write_text("{}", encoding="utf-8")
    _add_job(
        session,
        storage,
        video,
        "job_blob_active",
        status="awaiting_subtitle_review",
        updated_at=NOW - timedelta(days=30),
    )
    session.commit()

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 0
    assert result.removed_videos == 1
    assert result.removed_files == 1
    assert result.errors == ()
    assert blob.exists()
    assert not orphan_sidecar.exists()


def test_cleanup_rolls_back_database_before_deleting_files_when_commit_fails(
    storage_session: tuple[StoragePaths, Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=10)
    video, upload = _add_video(session, storage, "vid_rollback", created_at=old)
    _job, output_dir, temp_dir = _add_job(
        session,
        storage,
        video,
        "job_rollback",
        status="completed",
        updated_at=old,
    )
    session.commit()
    original_commit = session.commit

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        cleanup_expired_storage(
            session,
            storage,
            terminal_retention_days=7,
            orphan_retention_hours=24,
            now=NOW,
        )
    monkeypatch.setattr(session, "commit", original_commit)

    assert session.get(Job, "job_rollback") is not None
    assert session.get(Video, "vid_rollback") is not None
    assert _count(session, ExportItem) == 1
    assert upload.exists()
    assert output_dir.exists()
    assert temp_dir.exists()


def test_cleanup_claim_rechecks_status_after_candidate_selection(
    storage_session: tuple[StoragePaths, Session],
) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=10)
    video, _upload = _add_video(session, storage, "vid_reopened", created_at=old)
    job, _output, _temp = _add_job(
        session,
        storage,
        video,
        "job_reopened",
        status="completed",
        updated_at=old,
    )
    session.commit()
    candidate_ids = list(
        session.scalars(
            select(Job.id).where(
                Job.status.in_(("completed", "failed")),
                Job.updated_at <= NOW - timedelta(days=7),
            )
        )
    )

    with Session(session.get_bind()) as concurrent:
        reopened = concurrent.get(Job, job.id)
        assert reopened is not None
        reopened.status = "awaiting_subtitle_review"
        concurrent.commit()
    claimed = _claim_expired_jobs(session, candidate_ids, NOW - timedelta(days=7))

    assert claimed == []
    session.expire_all()
    session.refresh(job)
    assert job.status == "awaiting_subtitle_review"


def test_orphan_video_delete_rechecks_job_after_candidate_selection(
    storage_session: tuple[StoragePaths, Session],
) -> None:
    storage, session = storage_session
    old = NOW - timedelta(days=2)
    video, _upload = _add_video(session, storage, "vid_claimed", created_at=old)
    session.commit()
    candidate_ids = list(
        session.scalars(
            select(Video.id).where(
                Video.created_at <= NOW - timedelta(hours=24),
                ~Video.jobs.any(),
                ~Video.exports.any(),
            )
        )
    )

    with Session(session.get_bind()) as concurrent:
        concurrent.add(
            Job(
                id="job_claimed",
                video_id=video.id,
                status="queued",
                progress=5,
                current_step="Queued",
                settings_json={},
                created_at=NOW,
                updated_at=NOW,
            )
        )
        concurrent.commit()
    deleted = _delete_orphan_videos(
        session,
        candidate_ids,
        NOW - timedelta(hours=24),
    )

    assert deleted == []
    assert session.get(Video, video.id) is not None


def test_cleanup_retries_old_filesystem_orphans_without_database_rows(
    storage_session: tuple[StoragePaths, Session],
) -> None:
    storage, session = storage_session
    old_timestamp = (NOW - timedelta(days=10)).timestamp()
    output_dir = storage.outputs / "job_unreferenced"
    output_dir.mkdir()
    output_file = output_dir / "result.mp4"
    output_file.write_bytes(b"orphan output")
    upload = storage.uploads / "vid_unreferenced.mp4"
    upload.write_bytes(b"orphan source")
    sidecar = heatmap_sidecar_path(upload)
    sidecar.write_text("{}", encoding="utf-8")
    incoming = storage.uploads / ".incoming" / "vid_stale.part"
    incoming.parent.mkdir()
    incoming.write_bytes(b"partial")
    for path in (output_file, output_dir, upload, sidecar, incoming):
        os.utime(path, (old_timestamp, old_timestamp))

    result = cleanup_expired_storage(
        session,
        storage,
        terminal_retention_days=7,
        orphan_retention_hours=24,
        now=NOW,
    )

    assert result.removed_jobs == 0
    assert result.removed_videos == 0
    assert result.removed_files == 4
    assert result.errors == ()
    assert not output_dir.exists()
    assert not upload.exists()
    assert not sidecar.exists()
    assert not incoming.exists()
