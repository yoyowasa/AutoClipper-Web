from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import ExportItem, Job, Video
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths
from app.video.heatmap import heatmap_sidecar_path


TERMINAL_JOB_STATUSES = ("completed", "failed")
CLAIMED_JOB_STATUS = "_storage_cleanup_pending"
CONTAINER_STORAGE_PREFIX = "/app/storage/"


@dataclass(frozen=True)
class CleanupResult:
    removed_jobs: int
    removed_videos: int
    removed_files: int
    errors: tuple[str, ...]


def _naive_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is not None:
        current = current.astimezone(UTC).replace(tzinfo=None)
    return current


def _non_negative(value: int, name: str) -> int:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _terminal_cutoff(retention_days: int, now: datetime | None) -> datetime:
    days = _non_negative(retention_days, "terminal_retention_days")
    return _naive_utc(now) - timedelta(days=days)


def count_cleanup_eligible_jobs(
    session: Session,
    terminal_retention_days: int,
    now: datetime | None = None,
) -> int:
    cutoff = _terminal_cutoff(terminal_retention_days, now)
    statement = select(func.count(Job.id)).where(
        Job.status.in_(TERMINAL_JOB_STATUSES),
        Job.updated_at <= cutoff,
    )
    return int(session.scalar(statement) or 0)


def count_cleanup_eligible_videos(
    session: Session,
    terminal_retention_days: int,
    orphan_retention_hours: int,
    now: datetime | None = None,
) -> int:
    terminal_cutoff = _terminal_cutoff(terminal_retention_days, now)
    orphan_hours = _non_negative(orphan_retention_hours, "orphan_retention_hours")
    orphan_cutoff = _naive_utc(now) - timedelta(hours=orphan_hours)
    expired_job_ids = select(Job.id).where(
        Job.status.in_(TERMINAL_JOB_STATUSES),
        Job.updated_at <= terminal_cutoff,
    )
    statement = select(func.count(Video.id)).where(
        Video.created_at <= orphan_cutoff,
        ~Video.jobs.any(
            or_(
                Job.status.not_in(TERMINAL_JOB_STATUSES),
                Job.updated_at > terminal_cutoff,
            )
        ),
        ~Video.exports.any(ExportItem.job_id.not_in(expired_job_ids)),
    )
    return int(session.scalar(statement) or 0)


def _claim_expired_jobs(
    session: Session,
    candidate_ids: list[str],
    terminal_cutoff: datetime,
) -> list[tuple[str, str]]:
    if not candidate_ids:
        return []
    statement = (
        update(Job)
        .where(
            Job.id.in_(candidate_ids),
            Job.status.in_(TERMINAL_JOB_STATUSES),
            Job.updated_at <= terminal_cutoff,
        )
        .values(status=CLAIMED_JOB_STATUS)
        .returning(Job.id, Job.video_id)
    )
    return [(str(job_id), str(video_id)) for job_id, video_id in session.execute(statement)]


def _delete_orphan_videos(
    session: Session,
    candidate_ids: list[str],
    orphan_cutoff: datetime,
) -> list[tuple[str, str]]:
    if not candidate_ids:
        return []
    statement = (
        delete(Video)
        .where(
            Video.id.in_(candidate_ids),
            Video.created_at <= orphan_cutoff,
            ~Video.jobs.any(),
            ~Video.exports.any(),
        )
        .returning(Video.id, Video.stored_path)
    )
    return [(str(video_id), str(stored_path)) for video_id, stored_path in session.execute(statement)]


def _resolve_stored_path(value: str, storage_root: Path) -> Path:
    normalized = value.replace("\\", "/")
    if normalized.startswith(CONTAINER_STORAGE_PREFIX):
        relative = PurePosixPath(normalized.removeprefix(CONTAINER_STORAGE_PREFIX))
        return storage_root.joinpath(*relative.parts)

    path = Path(value)
    if path.is_absolute():
        return path
    if PureWindowsPath(value).is_absolute() and os.name != "nt":
        return path
    return storage_root / path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _inspect_deletion_target(path: Path, storage_root: Path, blobs_root: Path) -> tuple[int, str | None]:
    if not _is_within(path, storage_root) or path.resolve(strict=False) == storage_root.resolve(strict=False):
        return 0, "outside storage root"
    if _is_within(path, blobs_root):
        return 0, "canonical blob path cannot be deleted directly"
    if not _lexists(path):
        return 0, None
    if _is_reparse_or_symlink(path):
        return 0, "symlink or reparse point refused"

    if path.is_file():
        return 1, None
    if not path.is_dir():
        return 0, "unsupported filesystem entry"

    file_count = 0
    try:
        for current_root, directory_names, file_names in os.walk(path, topdown=True, followlinks=False):
            current = Path(current_root)
            for name in (*directory_names, *file_names):
                child = current / name
                if _is_reparse_or_symlink(child):
                    return 0, f"nested symlink or reparse point refused: {child}"
            file_count += len(file_names)
    except OSError as exc:
        return 0, f"could not inspect target: {exc}"
    return file_count, None


def _delete_path(path: Path, storage_root: Path, blobs_root: Path) -> tuple[int, str | None]:
    file_count, error = _inspect_deletion_target(path, storage_root, blobs_root)
    if error is not None or not _lexists(path):
        return 0, error
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        return 0, str(exc)
    return file_count, None


def _prune_unlinked_blobs(
    blobs_root: Path,
    storage_root: Path,
    protected_paths: set[str],
) -> tuple[int, list[str]]:
    if not _lexists(blobs_root):
        return 0, []
    if not _is_within(blobs_root, storage_root) or _is_reparse_or_symlink(blobs_root):
        return 0, [f"{blobs_root}: unsafe canonical blob root"]

    removed = 0
    errors: list[str] = []
    files: list[Path] = []
    directories: list[Path] = []
    pending = [blobs_root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if _is_reparse_or_symlink(path):
                        errors.append(f"{path}: symlink or reparse point refused")
                        continue
                    if not _is_within(path, blobs_root):
                        errors.append(f"{path}: outside canonical blob root")
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                        directories.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(path)
        except OSError as exc:
            errors.append(f"{directory}: could not enumerate canonical blobs: {exc}")

    for path in files:
        try:
            normalized_path = os.path.normcase(str(path.resolve(strict=False)))
            if normalized_path not in protected_paths and path.stat().st_nlink == 1:
                path.unlink()
                removed += 1
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    return removed, errors


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for path in paths:
        key = os.path.normcase(str(path.resolve(strict=False)))
        unique.setdefault(key, path)
    return list(unique.values())


def _is_older_than(path: Path, cutoff: datetime) -> bool:
    try:
        cutoff_timestamp = cutoff.replace(tzinfo=UTC).timestamp()
        return path.lstat().st_mtime <= cutoff_timestamp
    except OSError:
        return False


def _direct_children(root: Path, storage_root: Path) -> tuple[list[Path], list[str]]:
    if not _lexists(root):
        return [], []
    if not _is_within(root, storage_root) or _is_reparse_or_symlink(root):
        return [], [f"{root}: unsafe orphan scan root"]
    children: list[Path] = []
    errors: list[str] = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                path = Path(entry.path)
                if _is_reparse_or_symlink(path):
                    errors.append(f"{path}: symlink or reparse point refused")
                    continue
                children.append(path)
    except OSError as exc:
        errors.append(f"{root}: could not scan orphan entries: {exc}")
    return children, errors


def _orphan_filesystem_targets(
    paths: StoragePaths,
    *,
    remaining_job_ids: set[str],
    remaining_video_ids: set[str],
    remaining_stored_paths: list[str],
    terminal_cutoff: datetime,
    orphan_cutoff: datetime,
) -> tuple[list[Path], list[str]]:
    storage_root = paths.root.resolve(strict=False)
    targets: list[Path] = []
    errors: list[str] = []

    for root in (paths.outputs, paths.temp):
        children, scan_errors = _direct_children(root, storage_root)
        errors.extend(scan_errors)
        for path in children:
            if (
                path.name.startswith("job_")
                and path.name not in remaining_job_ids
                and _is_older_than(path, terminal_cutoff)
            ):
                targets.append(path)

    protected_uploads = {
        os.path.normcase(str(_resolve_stored_path(value, storage_root).resolve(strict=False)))
        for value in remaining_stored_paths
    }
    upload_children, upload_errors = _direct_children(paths.uploads, storage_root)
    errors.extend(upload_errors)
    for path in upload_children:
        if not path.name.startswith("vid_") or not path.is_file():
            continue
        normalized = os.path.normcase(str(path.resolve(strict=False)))
        if normalized in protected_uploads:
            continue
        if path.name.endswith(".heatmap.json"):
            media_path = Path(str(path)[: -len(".heatmap.json")])
            media_normalized = os.path.normcase(str(media_path.resolve(strict=False)))
            if media_normalized in protected_uploads:
                continue
        if _is_older_than(path, orphan_cutoff):
            targets.append(path)

    incoming_children, incoming_errors = _direct_children(
        paths.uploads / ".incoming",
        storage_root,
    )
    errors.extend(incoming_errors)
    targets.extend(path for path in incoming_children if _is_older_than(path, orphan_cutoff))

    heatmap_children, heatmap_errors = _direct_children(paths.heatmaps, storage_root)
    errors.extend(heatmap_errors)
    for path in heatmap_children:
        suffix = ".heatmap.json"
        if not path.name.endswith(suffix) or not path.is_file():
            continue
        video_id = path.name[: -len(suffix)]
        if video_id not in remaining_video_ids and _is_older_than(path, orphan_cutoff):
            targets.append(path)
    return targets, errors


def _cleanup_expired_storage_unlocked(
    session: Session,
    paths: StoragePaths,
    *,
    terminal_retention_days: int,
    orphan_retention_hours: int,
    now: datetime | None = None,
) -> CleanupResult:
    terminal_cutoff = _terminal_cutoff(terminal_retention_days, now)
    orphan_hours = _non_negative(orphan_retention_hours, "orphan_retention_hours")
    orphan_cutoff = _naive_utc(now) - timedelta(hours=orphan_hours)
    canonical_blobs_root = paths.uploads.resolve(strict=False) / ".blobs"

    candidate_job_ids = list(
        session.scalars(
            select(Job.id).where(
                Job.status.in_(TERMINAL_JOB_STATUSES),
                Job.updated_at <= terminal_cutoff,
            )
        ).all()
    )
    claimed_jobs = _claim_expired_jobs(session, candidate_job_ids, terminal_cutoff)
    job_ids = [job_id for job_id, _video_id in claimed_jobs]
    filesystem_targets = [
        target
        for job_id in job_ids
        for target in (paths.outputs / job_id, paths.temp / job_id)
    ]

    try:
        if job_ids:
            session.execute(delete(ExportItem).where(ExportItem.job_id.in_(job_ids)))
            session.execute(
                delete(Job).where(
                    Job.id.in_(job_ids),
                    Job.status == CLAIMED_JOB_STATUS,
                )
            )
            session.flush()

        orphan_video_candidates = list(
            session.execute(
                select(Video.id, Video.stored_path).where(
                    Video.created_at <= orphan_cutoff,
                    ~Video.jobs.any(),
                    ~Video.exports.any(),
                )
            ).all()
        )
        deleted_videos = _delete_orphan_videos(
            session,
            [str(video_id) for video_id, _stored_path in orphan_video_candidates],
            orphan_cutoff,
        )
        video_ids = [video_id for video_id, _stored_path in deleted_videos]
        for video_id, stored_path_value in deleted_videos:
            stored_path = _resolve_stored_path(stored_path_value, paths.root)
            filesystem_targets.append(paths.video_heatmap(video_id))
            if not _is_within(stored_path, canonical_blobs_root):
                filesystem_targets.extend(
                    (stored_path, heatmap_sidecar_path(stored_path))
                )
        remaining_job_ids = set(session.scalars(select(Job.id)).all())
        remaining_video_ids = set(session.scalars(select(Video.id)).all())
        remaining_stored_paths = list(session.scalars(select(Video.stored_path)).all())
        session.commit()
    except Exception:
        session.rollback()
        raise

    storage_root = paths.root.resolve(strict=False)
    blobs_root = paths.uploads.resolve(strict=False) / ".blobs"
    protected_blob_paths = {
        os.path.normcase(str(resolved.resolve(strict=False)))
        for value in remaining_stored_paths
        for resolved in (_resolve_stored_path(value, storage_root),)
        if _is_within(resolved, blobs_root)
    }
    orphan_targets, orphan_errors = _orphan_filesystem_targets(
        paths,
        remaining_job_ids=remaining_job_ids,
        remaining_video_ids=remaining_video_ids,
        remaining_stored_paths=remaining_stored_paths,
        terminal_cutoff=terminal_cutoff,
        orphan_cutoff=orphan_cutoff,
    )
    filesystem_targets.extend(orphan_targets)
    removed_files = 0
    errors: list[str] = list(orphan_errors)
    for target in _unique_paths(filesystem_targets):
        removed, error = _delete_path(target, storage_root, blobs_root)
        removed_files += removed
        if error is not None:
            errors.append(f"{target}: {error}")

    pruned_blobs, blob_errors = _prune_unlinked_blobs(
        blobs_root,
        storage_root,
        protected_blob_paths,
    )
    removed_files += pruned_blobs
    errors.extend(blob_errors)

    return CleanupResult(
        removed_jobs=len(job_ids),
        removed_videos=len(video_ids),
        removed_files=removed_files,
        errors=tuple(errors),
    )


def cleanup_expired_storage(
    session: Session,
    paths: StoragePaths,
    *,
    terminal_retention_days: int,
    orphan_retention_hours: int,
    now: datetime | None = None,
) -> CleanupResult:
    with storage_mutation_lock(paths.root):
        return _cleanup_expired_storage_unlocked(
            session,
            paths,
            terminal_retention_days=terminal_retention_days,
            orphan_retention_hours=orphan_retention_hours,
            now=now,
        )
