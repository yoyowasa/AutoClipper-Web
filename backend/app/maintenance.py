"""Scoped storage maintenance. Nothing is deleted without --execute."""

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.models import ExportItem, Job, Video
from app.storage.completed_previews import completed_preview_paths
from app.storage.lifecycle import (
    CLAIMED_JOB_STATUS,
    _delete_path,
    _inspect_deletion_target,
    _is_reparse_or_symlink,
    _is_within,
    _prune_unlinked_blobs,
    _resolve_stored_path,
    _unique_paths,
)
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths
from app.video.heatmap import heatmap_sidecar_path

DELETABLE_STATUSES = {"completed", "failed", "uploaded", "awaiting_manual_edit", "awaiting_clip_review", "awaiting_subtitle_review"}


@dataclass(frozen=True)
class Target:
    path: str
    kind: str
    bytes: int
    files: int


def _normalized(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Unsafe identifier: {value}")


def _target(path: Path, kind: str, paths: StoragePaths) -> Target | None:
    # Validate parents as well: even an internal junction must not redirect deletion.
    if not _is_within(path, paths.root) or path.resolve() == paths.root.resolve():
        raise ValueError(f"Unsafe storage target: {path}")
    parent = path
    while parent != paths.root:
        if _is_reparse_or_symlink(parent):
            raise ValueError(f"Symlink or reparse point refused: {parent}")
        parent = parent.parent
    if not path.exists():
        return None
    blobs = paths.uploads / ".blobs"
    if kind == "blob":
        if not _is_within(path, blobs) or not path.is_file():
            raise ValueError(f"Unsafe blob: {path}")
        if path.stat().st_nlink != 1:
            return None  # Existing lifecycle keeps blobs that still have hard links.
        files = [path]
    else:
        _count, error = _inspect_deletion_target(path, paths.root, blobs)
        if error:
            raise ValueError(f"{path}: {error}")
        files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    return Target(str(path), kind, sum(item.stat().st_size for item in files), len(files))


def _report(command: str, execute: bool, jobs: list[str], videos: list[str], targets: list[Target]) -> dict:
    return {
        "command": command, "dry_run": not execute, "jobs": jobs, "videos": videos,
        "targets": [asdict(target) for target in targets],
        "total_bytes": sum(target.bytes for target in targets), "errors": [],
    }


def _remove_targets(targets: list[Target], paths: StoragePaths) -> list[str]:
    errors = []
    for target in targets:
        if target.kind == "blob":
            continue
        _count, error = _delete_path(Path(target.path), paths.root, paths.uploads / ".blobs")
        if error:
            errors.append(f"{target.path}: {error}")
    return errors


def prune_completed_previews(db: Session, paths: StoragePaths, *, execute: bool = False) -> dict:
    with storage_mutation_lock(paths.root):
        job_ids = list(db.scalars(select(Job.id).where(Job.status == "completed").order_by(Job.id)))
        targets = []
        for job_id in job_ids:
            _validate_identifier(job_id)
            if rerender_publication_is_unresolved(paths.outputs / job_id):
                raise ValueError(f"Publication unresolved: {job_id}")
            for path in completed_preview_paths(paths, job_id):
                target = _target(path, "preview", paths)
                if target:
                    targets.append(target)
        report = _report("prune-completed-previews", execute, job_ids, [], targets)
        if execute:
            # Hold the SQLite write lock while checking states and deleting previews.
            # A simultaneous retry/reedit cannot turn a planned completed job active.
            for job_id in job_ids:
                result = db.execute(update(Job).where(Job.id == job_id, Job.status == "completed").values(status=Job.status))
                if result.rowcount != 1:
                    db.rollback()
                    raise ValueError(f"Job state changed: {job_id}")
            try:
                report["errors"] = _remove_targets(targets, paths)
            finally:
                db.rollback()  # No job attributes are changed by preview pruning.
        return report


def delete_jobs(db: Session, paths: StoragePaths, job_ids: list[str], *, execute: bool = False) -> dict:
    job_ids = sorted(set(job_ids))
    if not job_ids:
        raise ValueError("Specify at least one job")
    for job_id in job_ids:
        _validate_identifier(job_id)
    with storage_mutation_lock(paths.root):
        jobs = list(db.scalars(select(Job).where(Job.id.in_(job_ids)).execution_options(populate_existing=True)))
        if len(jobs) != len(job_ids):
            raise ValueError(f"Jobs not found: {sorted(set(job_ids) - {job.id for job in jobs})}")
        for job in jobs:
            if job.status not in DELETABLE_STATUSES:
                raise ValueError(f"Job is active or has an unknown state: {job.id}: {job.status}")
            if rerender_publication_is_unresolved(paths.outputs / job.id):
                raise ValueError(f"Publication unresolved: {job.id}")
        videos = list(db.scalars(select(Video).where(
            Video.id.in_({job.video_id for job in jobs}),
            ~Video.jobs.any(Job.id.not_in(job_ids)),
            ~Video.exports.any(ExportItem.job_id.not_in(job_ids)),
        )))
        video_ids = [video.id for video in videos]
        retained_source_paths = {
            _normalized(_resolve_stored_path(value, paths.root))
            for value in db.scalars(select(Video.stored_path).where(Video.id.not_in(video_ids)))
        }
        candidates: list[tuple[Path, str]] = []
        for job_id in job_ids:
            candidates.extend([(paths.outputs / job_id, "job_outputs"), (paths.temp / job_id, "job_temp")])
        for video in videos:
            _validate_identifier(video.id)
            source = _resolve_stored_path(video.stored_path, paths.root)
            candidates.append((paths.video_heatmap(video.id), "heatmap"))
            if _normalized(source) not in retained_source_paths:
                kind = "blob" if _is_within(source, paths.uploads / ".blobs") else "source"
                candidates.extend([(source, kind), (heatmap_sidecar_path(source), "blob" if kind == "blob" else "source_sidecar")])
        unique = _unique_paths([path for path, _kind in candidates])
        kinds = {_normalized(path): kind for path, kind in candidates}
        targets = [target for path in unique if (target := _target(path, kinds[_normalized(path)], paths)) is not None]
        report = _report("delete-jobs", execute, job_ids, sorted(video_ids), targets)
        if not execute:
            return report
        try:
            for job in jobs:
                result = db.execute(update(Job).where(
                    Job.id == job.id, Job.status == job.status, Job.updated_at == job.updated_at,
                ).values(status=CLAIMED_JOB_STATUS))
                if result.rowcount != 1:
                    raise ValueError(f"Job state changed: {job.id}")
            # Recheck Video references inside the write transaction before any deletes.
            current_orphans = set(db.scalars(select(Video.id).where(
                Video.id.in_(video_ids), ~Video.jobs.any(Job.id.not_in(job_ids)),
                ~Video.exports.any(ExportItem.job_id.not_in(job_ids)),
            )))
            current_retained = {
                _normalized(_resolve_stored_path(value, paths.root))
                for value in db.scalars(select(Video.stored_path).where(Video.id.not_in(video_ids)))
            }
            if current_orphans != set(video_ids) or current_retained != retained_source_paths:
                raise ValueError("Source video references changed; rerun maintenance")
            db.execute(delete(ExportItem).where(ExportItem.job_id.in_(job_ids)))
            db.execute(delete(Job).where(Job.id.in_(job_ids)))
            db.execute(delete(Video).where(Video.id.in_(video_ids)))
            db.commit()
        except Exception:
            db.rollback()
            raise
        report["errors"] = _remove_targets(targets, paths)
        # Scope the existing blob pruner to explicitly planned sources. All other
        # blobs, including unrelated unlinked files, remain protected.
        blobs = paths.uploads / ".blobs"
        planned_blobs = {_normalized(Path(target.path)) for target in targets if target.kind == "blob"}
        if planned_blobs:
            protected = {_normalized(path) for path in blobs.rglob("*") if path.is_file()} - planned_blobs
            _count, errors = _prune_unlinked_blobs(blobs, paths.root, protected | retained_source_paths)
            report["errors"].extend(errors)
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prune-completed-previews", "delete-jobs"):
        child = commands.add_parser(command)
        mode = child.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--execute", action="store_true")
        if command == "delete-jobs":
            child.add_argument("--job-id", nargs="+", action="extend", required=True)
    args = parser.parse_args(argv)
    paths = StoragePaths(Path(get_settings().storage_root).resolve())
    try:
        with SessionLocal() as db:
            if args.command == "prune-completed-previews":
                report = prune_completed_previews(db, paths, execute=args.execute)
            else:
                report = delete_jobs(db, paths, args.job_id, execute=args.execute)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["errors"] else 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
