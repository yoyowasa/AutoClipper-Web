"""Discard a review transactionally, preserving the approved selection."""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.jobs.clip_plan import ClipPlanDocument, clip_plan_output_path, write_clip_plan
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument, reviewed_transcript_output_path, subtitle_review_output_path,
    subtitle_review_preview_path, subtitle_review_source_path, subtitle_review_summary_path,
)
from app.models import Job, utc_now
from app.jobs.title_hook_suggestions import title_hook_suggestions_path, title_hook_suggestion_input_path

logger = logging.getLogger(__name__)


def discard_review_and_restore_plan(
    db: Session, job: Job, plan: ClipPlanDocument, review: SubtitleReviewDocument, output: Path,
) -> None:
    """Caller holds the review document lock; commit only after all file changes."""
    plan_path = clip_plan_output_path(output)
    selected_path = output / "selected_clips.json"
    selection = CandidateSelection.model_validate_json(selected_path.read_text(encoding="utf-8"))
    by_id = {clip.id: clip for clip in plan.clips}
    for candidate in [*selection.normal_clips, *selection.shorts]:
        clip = by_id.get(candidate.id)
        if clip is not None:
            candidate.hook_scene_start = clip.hook_scene_start
            candidate.hook_scene_end = clip.hook_scene_end
    originals = {path: path.read_bytes() for path in (plan_path, selected_path)}
    discarded = [subtitle_review_output_path(output), subtitle_review_summary_path(output),
                 subtitle_review_source_path(output, review), reviewed_transcript_output_path(output)]
    # The flat <clip digest>.mp4 files belong to clip-plan review. Keep those.
    discarded.extend(subtitle_review_preview_path(output, clip.id).with_suffix("") for clip in review.clips)
    discarded.extend(path for clip in review.clips for path in (
        title_hook_suggestions_path(output, clip.id), title_hook_suggestion_input_path(output, clip.id)))
    staging = output / f".discarded-review-{uuid4().hex}"
    moved: list[tuple[Path, Path]] = []
    cleanup = True
    try:
        staging.mkdir()
        for index, path in enumerate(discarded):
            if path.exists():
                backup = staging / str(index)
                path.replace(backup)
                moved.append((path, backup))
        plan.state = "awaiting_review"
        plan.boundary_reedit = False
        plan.subtitle_review_generation = uuid4().hex
        plan.updated_at = datetime.now(UTC).isoformat()
        write_clip_plan(plan, plan_path)
        write_selected_clips(selection, selected_path)
        # Before approval this is the exact settings snapshot; older plans store it in settings.
        job.settings_json = dict(plan.review_entry_settings if plan.review_entry_settings is not None else plan.settings)
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP[job.status]
        job.current_step = CURRENT_STEP_MAP[job.status]
        job.error_code = job.error_message = None
        job.updated_at = utc_now()
        db.commit()
    except Exception:
        db.rollback()
        try:
            for path, payload in originals.items():
                path.write_bytes(payload)
            for path, backup in reversed(moved):
                backup.replace(path)
        except Exception:
            cleanup = False  # Preserve the only backup if restoration itself fails.
            raise
        raise
    finally:
        # Failed cleanup must not turn a committed return into a misleading HTTP failure.
        try:
            if cleanup:
                shutil.rmtree(staging)
        except OSError:
            logger.warning("Could not remove discarded review backup for job %s", job.id)
