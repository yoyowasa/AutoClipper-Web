"""Confirmed auto clips reuse the existing preview and render queues."""

from fastapi import HTTPException

from app.jobs.manual_framing import framing_edit_error, record_manual_framing
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.status import PROGRESS_MAP, CURRENT_STEP_MAP
from app.jobs.subtitle_review import confirm_review_clip, update_review_clip_framing
from app.jobs.subtitle_review_preview import subtitle_review_document_lock, refresh_subtitle_review_preview_states
from app.jobs.subtitle_review import refresh_review_render_contract
from app.models import utc_now


def update_automatic_framing(job, video, clip_id, request, db, paths, enqueue_preview, *, reset=False, enqueue_decisions=None):
    from app.api import jobs

    directory = paths.job_outputs(job.id)
    with subtitle_review_document_lock(directory):
        db.refresh(job)
        if job.status not in {"awaiting_subtitle_review", "completed"}:
            raise HTTPException(409, "書き出し中は画角を変更できません。完了後に調整してください。")
        if rerender_publication_is_unresolved(directory):
            raise HTTPException(409, "前回の再書き出しの復旧が必要なため、画角を変更できません。")
        if job.status == "completed" and not jobs._reedit_artifacts_available(job.id, video, paths):
            raise HTTPException(409, "元動画または再編集用のデータがないため、画角を変更できません。")
        document = jobs._get_subtitle_review_or_404(job.id, paths)
        clip = next((c for c in document.clips if c.id == clip_id), None)
        if clip is None:
            raise HTTPException(404, "対象のclipがありません。")
        if error := framing_edit_error(document, clip):
            raise HTTPException(409, error)
        if reset and clip.type != "short":
            raise HTTPException(422, "画角を自動に戻せるのはショートだけです。")
        if reset and "framing" not in clip.manual_decision_fields:
            return document
        if not reset and (clip.framing_offset_x == round(request.framing_offset_x, 2)
                and clip.framing_offset_y == round(request.framing_offset_y, 2)
                and clip.framing_zoom == round(request.framing_zoom, 3)
                and (request.short_layout is None or request.short_layout == (clip.short_layout or document.short_layout))):
            return document
        before = clip.model_copy(deep=True)
        if job.status == "completed":
            document.render_revision += 1
            document.render_clip_ids = [clip_id]
            document.state = "awaiting_review"
        if reset:
            jobs._defer_subtitle_review_previews_unlocked(document, {clip_id})
            from app.jobs.manual_framing import restore_automatic_framing
            revision = restore_automatic_framing(document, clip)
            queued = []
        else:
            _save_manual_framing(job, video, clip, request, document, before)
            jobs._defer_subtitle_review_previews_unlocked(document, {clip_id})
            document, queued, _ = refresh_subtitle_review_preview_states(
                job=job, video=video, document=document, paths=paths, clip_ids={clip_id}, generate_exact=True)
        confirm_review_clip(document, clip_id)
        jobs._write_subtitle_review_unlocked(document, paths)
        if job.status == "completed":
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP[job.status]
            job.current_step = CURRENT_STEP_MAP[job.status]
            job.updated_at = utc_now()
            db.commit()
    if reset:
        try:
            enqueue_decisions(job.id, clip_id, revision, framing_only=True)
        except Exception as exc:
            from app.jobs.confirmed_clip_decisions import record_decision_failure
            record_decision_failure(paths, job.id, clip_id, revision,
                                    "画角の再自動決定を登録できませんでした。字幕を確定して再試行してください。")
            raise HTTPException(503, "画角の再自動決定を登録できませんでした。") from exc
        return document
    return jobs._enqueue_subtitle_review_previews(job_id=job.id, document=document, queued=queued,
                                                 paths=paths, enqueue_preview=enqueue_preview)


def _save_manual_framing(job, video, clip, request, document, before):
    try:
        update_review_clip_framing(document, clip.id, framing_offset_x=request.framing_offset_x,
                                   framing_offset_y=request.framing_offset_y, framing_zoom=request.framing_zoom)
        if request.short_layout is not None and request.short_layout != (clip.short_layout or document.short_layout):
            clip.short_layout = request.short_layout
            clip.automatic_crop = None
        refresh_review_render_contract(document, render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
                                       render_settings=dict(job.settings_json or {}),
                                       source_width=video.width, source_height=video.height)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    clip.manual_decision_fields = sorted(set(clip.manual_decision_fields) | {"framing"})
    record_manual_framing(document, clip, before)
