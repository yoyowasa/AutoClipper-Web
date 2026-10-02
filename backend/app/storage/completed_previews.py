"""Only disposable review videos belong in this cleanup whitelist."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.subtitle_review import SUBTITLE_REVIEW_PREVIEW_DIRNAME
from app.models import Job
from app.render.render_manual_source_proxy import manual_source_proxy_path
from app.storage.lifecycle import _delete_path
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths

logger = logging.getLogger(__name__)


def completed_preview_paths(paths: StoragePaths, job_id: str) -> tuple[Path, ...]:
    output_dir = paths.outputs / job_id
    return output_dir / SUBTITLE_REVIEW_PREVIEW_DIRNAME, manual_source_proxy_path(output_dir)


def prune_job_previews_after_completion(db: Session, job: Job, paths: StoragePaths) -> None:
    """A cleanup error must never undo a successful publication."""
    job_id = job.id
    try:
        with storage_mutation_lock(paths.root):
            db.refresh(job)
            if job.status != "completed" or rerender_publication_is_unresolved(paths.outputs / job.id):
                return
            for path in completed_preview_paths(paths, job.id):
                _removed, error = _delete_path(path, paths.root, paths.uploads / ".blobs")
                if error:
                    logger.warning("Completed preview cleanup failed for %s: %s: %s", job.id, path, error)
    except Exception:
        db.rollback()
        logger.warning("Completed preview cleanup failed for %s", job_id, exc_info=True)
