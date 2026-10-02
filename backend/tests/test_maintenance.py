from collections.abc import Generator
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.maintenance as maintenance
import app.storage.completed_previews as previews
from app.db import Base, _create_engine
from app.jobs.publication_state import mark_rerender_publication_unresolved
from app.jobs.runner import run_subtitle_review_preview
from app.models import CharacterAssetHarvest, ClipRejection, ExportItem, Job, SourceClipUsage, Video
from app.storage.paths import StoragePaths


@pytest.fixture
def storage_db(tmp_path: Path) -> Generator[tuple[Session, StoragePaths], None, None]:
    engine = _create_engine(f"sqlite:///{tmp_path / 'maintenance.db'}")
    Base.metadata.create_all(engine)
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure()
    with Session(engine) as db:
        yield db, paths
    engine.dispose()


def seed(db: Session, paths: StoragePaths, *, status: str = "completed") -> tuple[Job, Path]:
    blob = paths.uploads / ".blobs" / "source.mp4"
    blob.parent.mkdir()
    blob.write_bytes(b"source")
    db.add(Video(id="vid_source", original_filename="source.mp4", stored_path=str(blob)))
    db.flush()
    job = Job(id="job_target", video_id="vid_source", status=status)
    db.add(job)
    db.flush()
    output = paths.job_outputs(job.id)
    for name in ["subtitle_review.json", "final.mp4", "final.zip", "thumbnails/final.png", "thumbnails/frames/candidate.jpg"]:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"preserve")
    for preview in previews.completed_preview_paths(paths, job.id):
        if preview.suffix == ".mp4":
            preview.write_bytes(b"proxy")
        else:
            preview.mkdir()
            (preview / "exact.mp4").write_bytes(b"preview")
            (preview / "live.mp4").write_bytes(b"live")
    db.add(ExportItem(id="export", job_id=job.id, video_id=job.video_id, candidate_id="clip", type="normal",
                      title="test", duration=90, score=1, video_path=str(output / "final.mp4")))
    db.add(SourceClipUsage(id="usage", source_key="source", job_id=job.id, clip_type="normal", start=0, end=90))
    db.add(ClipRejection(id="rejection", job_id=job.id, video_id=job.video_id, source_key="source",
                         clip_plan_revision=1, clip_id="clip", clip_type="normal", start=0, end=90, reason="unspecified"))
    db.commit()
    return job, blob


def test_completed_cleanup_preserves_final_artifacts(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, _blob = seed(db, paths)
    previews.prune_job_previews_after_completion(db, job, paths)
    assert all(not path.exists() for path in previews.completed_preview_paths(paths, job.id))
    retained = sorted(path.relative_to(paths.outputs / job.id).as_posix()
                      for path in (paths.outputs / job.id).rglob("*") if path.is_file())
    assert retained == [
        "final.mp4", "final.zip", "subtitle_review.json", "thumbnails/final.png", "thumbnails/frames/candidate.jpg",
    ]
    assert db.get(Job, job.id).status == "completed"


@pytest.mark.parametrize("raises", [False, True])
def test_cleanup_failure_is_warning_only(
    storage_db: tuple[Session, StoragePaths], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, raises: bool,
) -> None:
    db, paths = storage_db
    job, _blob = seed(db, paths)

    def fail(*_args):
        if raises:
            raise OSError("denied")
        return 0, "denied"

    monkeypatch.setattr(previews, "_delete_path", fail)
    previews.prune_job_previews_after_completion(db, job, paths)
    db.refresh(job)
    assert job.status == "completed"
    assert "cleanup failed" in caplog.text
    assert all(path.exists() for path in previews.completed_preview_paths(paths, job.id))


def test_dry_runs_preserve_rows_and_files(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    before = {str(path): path.read_bytes() for path in paths.root.rglob("*") if path.is_file()}
    prune = maintenance.prune_completed_previews(db, paths)
    delete = maintenance.delete_jobs(db, paths, [job.id])
    assert prune["dry_run"] and prune["total_bytes"] == len(b"proxypreviewlive")
    assert delete["dry_run"] and delete["videos"] == ["vid_source"]
    assert any(target["path"] == str(blob) for target in delete["targets"])
    assert all(Path(path).read_bytes() == content for path, content in before.items())
    assert db.get(Job, job.id).status == "completed"
    assert db.get(ExportItem, "export") is not None


def test_prune_only_completed_jobs(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    waiting = Job(id="job_waiting", video_id=job.video_id, status="awaiting_subtitle_review")
    db.add(waiting)
    db.commit()
    path = previews.completed_preview_paths(paths, waiting.id)[0]
    path.mkdir(parents=True)
    (path / "preview.mp4").write_bytes(b"waiting")
    report = maintenance.prune_completed_previews(db, paths, execute=True)
    assert report["jobs"] == [job.id] and not report["errors"]
    assert path.is_dir() and blob.exists()
    db.refresh(job)
    assert job.status == "completed"


@pytest.mark.parametrize("different_video", [False, True])
def test_delete_keeps_shared_source(storage_db: tuple[Session, StoragePaths], different_video: bool) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    video_id = job.video_id
    if different_video:
        video_id = "vid_other"
        db.add(Video(id=video_id, original_filename="other.mp4", stored_path=str(blob)))
        db.flush()
    db.add(Job(id="job_keep", video_id=video_id, status="completed"))
    db.commit()
    report = maintenance.delete_jobs(db, paths, [job.id], execute=True)
    assert not report["errors"]
    assert db.get(Job, job.id) is None and db.get(ExportItem, "export") is None
    assert not (paths.outputs / job.id).exists()
    assert db.get(Job, "job_keep") is not None
    assert db.get(Video, video_id) is not None and blob.is_file()
    assert db.get(SourceClipUsage, "usage") is not None and db.get(ClipRejection, "rejection") is not None


def test_delete_removes_only_unshared_source_and_keeps_ledgers(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    unrelated = blob.with_name("unrelated.mp4")
    unrelated.write_bytes(b"unrelated unlinked source")
    heatmap = paths.video_heatmap(job.video_id)
    heatmap.write_text("{}", encoding="utf-8")
    report = maintenance.delete_jobs(db, paths, [job.id], execute=True)
    assert not report["errors"] and report["videos"] == ["vid_source"]
    assert db.get(Video, "vid_source") is None and not blob.exists()
    assert not heatmap.exists()
    assert unrelated.is_file()
    assert db.get(SourceClipUsage, "usage") is not None and db.get(ClipRejection, "rejection") is not None


@pytest.mark.parametrize("status", ["queued", "generating_candidates", "rendering_shorts", "reselecting_clips", "packaging_zip"])
@pytest.mark.parametrize("execute", [False, True])
def test_active_job_is_refused(storage_db: tuple[Session, StoragePaths], status: str, execute: bool) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths, status=status)
    with pytest.raises(ValueError, match="active"):
        maintenance.delete_jobs(db, paths, [job.id], execute=execute)
    assert blob.exists() and (paths.outputs / job.id).exists() and db.get(Job, job.id).status == status


def test_source_in_active_harvest_is_kept(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    db.add(CharacterAssetHarvest(id="harvest", preset_id="preset", video_id=job.video_id, state="running"))
    db.commit()
    report = maintenance.delete_jobs(db, paths, [job.id], execute=True)
    assert report["videos"] == [] and db.get(Video, job.video_id) is not None and blob.exists()


def test_publication_and_unsafe_identifiers_are_refused(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    with pytest.raises(ValueError, match="identifier"):
        maintenance.delete_jobs(db, paths, ["../outside"], execute=True)
    mark_rerender_publication_unresolved(paths.outputs / job.id, job_id=job.id, render_revision=2, attempt_id="test")
    with pytest.raises(ValueError, match="Publication unresolved"):
        maintenance.delete_jobs(db, paths, [job.id], execute=True)
    with pytest.raises(ValueError, match="Publication unresolved"):
        maintenance.prune_completed_previews(db, paths, execute=True)
    assert blob.exists()


def test_late_preview_worker_does_not_recreate_completed_previews(storage_db: tuple[Session, StoragePaths]) -> None:
    db, paths = storage_db
    job, _blob = seed(db, paths)
    previews.prune_job_previews_after_completion(db, job, paths)
    result = run_subtitle_review_preview(job.id, "clip", "hash", session_factory=lambda: Session(db.get_bind()), paths=paths)
    assert result == ["completed"]
    assert all(not path.exists() for path in previews.completed_preview_paths(paths, job.id))


def test_cli_defaults_to_dry_run(storage_db: tuple[Session, StoragePaths], monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    monkeypatch.setattr(maintenance, "SessionLocal", lambda: Session(db.get_bind()))
    monkeypatch.setattr(maintenance, "get_settings", lambda: type("Config", (), {"storage_root": str(paths.root)})())
    assert maintenance.main(["delete-jobs", "--job-id", job.id]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert blob.exists() and db.scalar(select(Job.id)) == job.id


def test_claim_refuses_a_job_that_became_active(
    storage_db: tuple[Session, StoragePaths], monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, paths = storage_db
    job, blob = seed(db, paths)
    execute = db.execute
    changed = False

    def change_before_claim(statement, *args, **kwargs):
        nonlocal changed
        if statement.is_update and not changed:
            changed = True
            with Session(db.get_bind()) as other:
                other.get(Job, job.id).status = "queued"
                other.commit()
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", change_before_claim)
    with pytest.raises(ValueError, match="Job state changed"):
        maintenance.delete_jobs(db, paths, [job.id], execute=True)
    db.expire_all()
    assert db.get(Job, job.id).status == "queued" and blob.exists()
    assert (paths.outputs / job.id).exists() and db.get(ExportItem, "export") is not None


def test_job_deletion_error_is_reported_and_keeps_ledgers(
    storage_db: tuple[Session, StoragePaths], monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, paths = storage_db
    job, _blob = seed(db, paths)
    monkeypatch.setattr(maintenance, "_delete_path", lambda *_args: (0, "permission denied"))
    report = maintenance.delete_jobs(db, paths, [job.id], execute=True)
    assert report["errors"] and "permission denied" in report["errors"][0]
    assert db.get(Job, job.id) is None and (paths.outputs / job.id).exists()
    assert db.get(SourceClipUsage, "usage") is not None and db.get(ClipRejection, "rejection") is not None
