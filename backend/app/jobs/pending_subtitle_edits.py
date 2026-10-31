"""Keep subtitle edits durable while an immutable render snapshot is running."""
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import select

from app.jobs.subtitle_review import (SubtitleReviewDocument, load_subtitle_review, subtitle_review_output_path,
    subtitle_review_summary_path, write_subtitle_review, write_subtitle_review_summary, confirm_review_clip)
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.jobs.subtitle_review_edits import remap_clip_segment_ids
from app.jobs.status import PROGRESS_MAP, CURRENT_STEP_MAP
from app.models import Job, ExportItem, utc_now
from app.storage.json_io import write_json_atomic


class PendingSubtitleEdits(BaseModel):
    document: SubtitleReviewDocument
    clip_ids: list[str]


def pending_view(document, paths):
    document = document.model_copy(update={"pending_subtitle_clip_ids": []})
    path = paths.pending_subtitle_edits(document.job_id)
    if not path.is_file():
        return document
    saved = PendingSubtitleEdits.model_validate_json(path.read_text(encoding="utf-8"))
    if (saved.document.created_at, saved.document.preview_generation) != (document.created_at, document.preview_generation):
        return document
    result = merge_subtitles(document, saved.document, set(saved.clip_ids))
    result.pending_subtitle_clip_ids = saved.clip_ids
    return result


def merge_subtitles(latest, edited, ids):
    result = latest.model_copy(deep=True)
    result.has_saved_review_changes = bool(ids) or result.has_saved_review_changes
    by_id = {}
    for segment in result.segments:
        owners = [id for id in segment.affected_clip_ids if id not in ids]
        if owners:
            segment.affected_clip_ids = owners
            by_id[segment.id] = segment
    mapping = {}
    for segment in edited.segments:
        owners = [id for id in segment.affected_clip_ids if id in ids]
        if not owners:
            continue
        segment = segment.model_copy(deep=True, update={"affected_clip_ids": owners})
        if segment.id in by_id:
            protected = by_id[segment.id]
            if protected.model_dump(exclude={"affected_clip_ids", "clip_scoped"}) == segment.model_dump(
                exclude={"affected_clip_ids", "clip_scoped"}):
                protected.affected_clip_ids.extend(owners)
                continue
            mapping[segment.id] = f"seg_{uuid4().hex}"
            segment.id = mapping[segment.id]
        by_id[segment.id] = segment
    scoped = {i for s in by_id.values() if s.clip_scoped for i in (s.source_indices or [s.index])}
    for segment in by_id.values():
        if scoped.intersection(segment.source_indices or [segment.index]):
            segment.clip_scoped = True
    result.segments = sorted(by_id.values(), key=lambda s: (s.start, s.end))
    for clip in result.clips:
        if clip.id in ids:
            source = next(c for c in edited.clips if c.id == clip.id)
            clip.segment_ids = list(source.segment_ids)
            clip.subtitle_styles = [s.model_copy(deep=True) for s in source.subtitle_styles]
            remap_clip_segment_ids(clip, mapping)
    return result


def save_pending(document, affected, paths):
    old = paths.pending_subtitle_edits(document.job_id)
    ids = set(affected)
    if old.is_file():
        previous = PendingSubtitleEdits.model_validate_json(old.read_text(encoding="utf-8"))
        if (previous.document.created_at, previous.document.preview_generation) == (document.created_at, document.preview_generation):
            ids.update(previous.clip_ids)
    payload = PendingSubtitleEdits(document=document, clip_ids=sorted(ids))
    write_json_atomic(old, payload.model_dump(mode="json"))
    document.pending_subtitle_clip_ids = sorted(ids)
    return document


def activate_pending(db, job_id, paths, enqueue=None):
    """After render commit/rollback, use the existing decision/preview/render queues."""
    pending_path = paths.pending_subtitle_edits(job_id)
    if not pending_path.is_file():
        return False
    directory = paths.job_outputs(job_id)
    revisions = []
    with subtitle_review_document_lock(directory):
        job = db.get(Job, job_id)
        if job is None:
            return False
        db.refresh(job)
        if job.status in {"rendering_normal_clips", "rendering_shorts", "packaging_zip"}:
            return False
        from app.jobs.publication_state import rerender_publication_is_unresolved
        if rerender_publication_is_unresolved(directory):
            return False
        path = subtitle_review_output_path(directory)
        latest = load_subtitle_review(path)
        updated = pending_view(latest, paths)
        ids = set(updated.pending_subtitle_clip_ids)
        if not ids:
            return False
        from app.jobs.confirmed_clip_decisions import queue_clip_decisions
        from app.jobs.subtitle_decision_inputs import changed_targets
        updated.state = "awaiting_review"
        updated.render_revision += 1
        exports = set(db.scalars(select(ExportItem.candidate_id).where(ExportItem.job_id == job.id)))
        updated.render_clip_ids = sorted(ids) if {c.id for c in updated.clips}.issubset(exports) else None
        updated.pending_subtitle_clip_ids = []
        for clip in updated.clips:
            if clip.id in ids:
                before = next(c for c in latest.clips if c.id == clip.id)
                revisions.append((clip.id, queue_clip_decisions(updated, clip, manual_fields=set(),
                    targets=changed_targets(latest, before, updated, clip))))
                confirm_review_clip(updated, clip.id)
        write_subtitle_review(updated, path)
        write_subtitle_review_summary(updated, subtitle_review_summary_path(directory))
        job.status, job.error_code, job.error_message = "awaiting_subtitle_review", None, None
        job.progress, job.current_step = PROGRESS_MAP[job.status], CURRENT_STEP_MAP[job.status]
        job.updated_at = utc_now()
        db.commit()
        pending_path.unlink()
    if enqueue is None:
        from app.jobs.queue import enqueue_confirmed_clip_decisions
        enqueue = enqueue_confirmed_clip_decisions
    for clip_id, revision in revisions:
        try:
            enqueue(job_id, clip_id, revision)
        except Exception:
            from app.jobs.confirmed_clip_decisions import record_decision_failure
            record_decision_failure(paths, job_id, clip_id, revision, "字幕変更後の自動処理を登録できませんでした。再試行してください。")
    return True


def maintain_pending_subtitle_edits(db, paths):
    for path in paths.outputs.glob("*/subtitle_review_pending_edits.json"):
        activate_pending(db, path.parent.name, paths)
