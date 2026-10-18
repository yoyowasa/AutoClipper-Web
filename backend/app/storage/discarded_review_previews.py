"""Retry only the files discarded by a committed review return, never a new generation."""

import json
import logging
from pathlib import Path, PurePosixPath

from app.jobs.subtitle_review import SubtitleReviewDocument, subtitle_review_preview_path, SUBTITLE_REVIEW_PREVIEW_DIRNAME
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.storage.json_io import write_json_atomic
from app.storage.lifecycle import _is_reparse_or_symlink
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths

logger = logging.getLogger(__name__)
CLEANUP_FILENAME = ".discarded-preview-cleanup.json"


def discarded_preview_cleanup_path(output: Path) -> Path:
    return output / CLEANUP_FILENAME


def _target(output: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if len(parts) < 3 or parts[0] != SUBTITLE_REVIEW_PREVIEW_DIRNAME or ".." in parts or "\\" in relative:
        raise ValueError("Invalid discarded preview path")
    path = output.joinpath(*parts)
    if not path.resolve().is_relative_to((output / SUBTITLE_REVIEW_PREVIEW_DIRNAME).resolve()):
        raise ValueError("Invalid discarded preview path")
    current = path
    while current != output:
        if _is_reparse_or_symlink(current):
            raise ValueError("Invalid discarded preview path")
        current = current.parent
    return path


def pending_discarded_previews(output: Path) -> list[str]:
    manifest = discarded_preview_cleanup_path(output)
    if not manifest.exists():
        return []
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(value, str) for value in payload):
        raise ValueError("Invalid discarded preview manifest")
    for value in payload:
        _target(output, value)
    return payload


def register_discarded_previews(output: Path, review: SubtitleReviewDocument) -> None:
    """Called under the review lock, before commit; the caller backs up this JSON too."""
    pending = set(pending_discarded_previews(output))
    for clip in review.clips:
        directory = subtitle_review_preview_path(output, clip.id).with_suffix("")
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(output).as_posix()
                    _target(output, relative)
                    pending.add(relative)
    if pending:
        write_json_atomic(discarded_preview_cleanup_path(output), sorted(pending))


def cleanup_discarded_preview_files(output: Path) -> None:
    """Caller holds the review lock. Open Windows files remain queued for another attempt."""
    manifest = discarded_preview_cleanup_path(output)
    if not manifest.exists():
        return
    pending = pending_discarded_previews(output)
    remaining = []
    for relative in pending:
        path = _target(output, relative)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("%s", path)
            remaining.append(relative)
    if remaining:
        write_json_atomic(manifest, remaining)
    else:
        manifest.unlink(missing_ok=True)


def maintain_discarded_review_previews(paths: StoragePaths) -> None:
    """Media-worker maintenance retries committed cleanup with storage/review locks."""
    with storage_mutation_lock(paths.root):
        for manifest in paths.outputs.glob(f"*/{CLEANUP_FILENAME}"):
            try:
                if _is_reparse_or_symlink(manifest.parent) or _is_reparse_or_symlink(manifest):
                    raise ValueError("Invalid discarded preview manifest")
                with subtitle_review_document_lock(manifest.parent, timeout_seconds=0.1):
                    cleanup_discarded_preview_files(manifest.parent)
            except Exception:
                logger.warning("%s", manifest)
