"""Atomic subtitle-only mutations, preserving confirmation and manual decisions."""
import shutil

from fastapi import HTTPException

from app.jobs.automation import is_subtitle_only_auto
from app.jobs.subtitle_review import update_review_segment, subtitle_review_source_path, transcript_output_path, confirm_review_clip
from app.jobs.subtitle_structure import edit_subtitle_structure
from app.jobs.subtitle_review_edits import editable_clip_ids
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.status import PROGRESS_MAP, CURRENT_STEP_MAP
from app.models import utc_now


def mutate_subtitles(job, video, request, db, paths, enqueue_decisions, enqueue_preview, *, structure=False):
    from app.api import jobs
    directory = paths.job_outputs(job.id)
    revisions = []
    queued = []
    with subtitle_review_document_lock(directory):
        db.refresh(job)
        document = jobs._get_subtitle_review_or_404(job.id, paths)
        from app.jobs.pending_subtitle_edits import pending_view
        before = document.model_copy(deep=True)
        document = pending_view(document, paths)
        auto = document.subtitle_only_auto and is_subtitle_only_auto(job.settings_json or {})
        target = next((c for c in document.clips if c.id == request.clip_id), None)
        completed = job.status == "completed" and document.state == "completed"
        busy = auto and target is not None and target.confirmed and (
            job.status in {"rendering_normal_clips", "rendering_shorts", "packaging_zip"}
            or document.state in {"render_queued", "rendering"})
        if not (job.status == "awaiting_subtitle_review" and document.state == "awaiting_review") and not (
            completed and auto and target is not None and target.confirmed
        ) and not busy:
            raise HTTPException(409, "字幕を編集できる状態ではありません。書き出し中は完了後に自動反映します。")
        if not busy and rerender_publication_is_unresolved(directory):
            raise HTTPException(409, "前回の再書き出しの復旧が必要なため、字幕を変更できません。")
        if completed and not jobs._reedit_artifacts_available(job.id, video, paths):
            raise HTTPException(409, "元動画または再編集用のデータがないため、字幕を変更できません。")
        try:
            if structure:
                affected = edit_subtitle_structure(document, request)
                snapshot = subtitle_review_source_path(directory, document)
                if not snapshot.exists():
                    shutil.copyfile(transcript_output_path(directory), snapshot)
            else:
                affected = update_batch(document, request)
        except KeyError as exc:
            raise HTTPException(404, "字幕または対象動画が見つかりません。") from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not affected:
            return document
        if busy:
            from app.jobs.pending_subtitle_edits import save_pending
            # Never overwrite the render snapshot or start another render in HTTP.
            snapshot = subtitle_review_source_path(directory, document)
            if not snapshot.exists():
                shutil.copyfile(transcript_output_path(directory), snapshot)
            return save_pending(document, affected, paths)
        affected.update(document.pending_subtitle_clip_ids)
        document.pending_subtitle_clip_ids = []
        confirmed = {c.id for c in before.clips if auto and c.confirmed and c.id in affected}
        jobs._defer_subtitle_review_previews_unlocked(document, affected)
        if completed:
            document.render_revision += 1
            document.render_clip_ids = sorted(affected)
            document.state = "awaiting_review"
        from app.jobs.confirmed_clip_decisions import queue_clip_decisions
        from app.jobs.subtitle_decision_inputs import changed_targets
        for clip in document.clips:
            if clip.id not in confirmed:
                continue
            previous = next(c for c in before.clips if c.id == clip.id)
            revision = queue_clip_decisions(document, clip, manual_fields=set(),
                targets=changed_targets(before, previous, document, clip))
            confirm_review_clip(document, clip.id)
            revisions.append((clip.id, revision))
        # Save-only structural edits never confirm an unconfirmed clip. A live
        # source is refreshed only when its range/hook inputs actually changed.
        if confirmed:
            from app.jobs.subtitle_review_preview import refresh_subtitle_review_preview_states
            document, queued, _ = refresh_subtitle_review_preview_states(
                job=job, video=video, document=document, paths=paths, clip_ids=confirmed)
        for clip_id in confirmed:
            confirm_review_clip(document, clip_id)
        jobs._write_subtitle_review_unlocked(document, paths)
        if completed:
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP[job.status]
            job.current_step = CURRENT_STEP_MAP[job.status]
            job.updated_at = utc_now()
            db.commit()
        paths.pending_subtitle_edits(job.id).unlink(missing_ok=True)
    for clip_id, revision in revisions:
        try:
            enqueue_decisions(job.id, clip_id, revision)
        except Exception:
            from app.jobs.confirmed_clip_decisions import record_decision_failure
            record_decision_failure(paths, job.id, clip_id, revision, "字幕変更後の自動処理を登録できませんでした。再試行してください。")
            document = jobs._get_subtitle_review_or_404(job.id, paths)
    return jobs._enqueue_subtitle_review_previews(job_id=job.id, document=document, queued=queued,
        paths=paths, enqueue_preview=enqueue_preview, preserve_confirmation_for=confirmed)


def update_batch(document, request):
    by_id = {s.id: s for s in document.segments}
    ids = [item.segment_id for item in request.segments]
    if len(ids) != len(set(ids)):
        raise ValueError("字幕の指定が重複しています。")
    target = next((c for c in document.clips if c.id == request.clip_id), None)
    if request.clip_id is not None and target is None:
        raise KeyError(request.clip_id)
    for item in request.segments:
        if item.segment_id not in by_id:
            raise KeyError(item.segment_id)
        if target is not None and item.segment_id not in target.segment_ids:
            raise ValueError("字幕が対象動画に含まれていません。")
        if item.before != by_id[item.segment_id].text:
            raise RuntimeError("字幕が別の操作で更新されています。画面を読み直してください。")
    editable = editable_clip_ids(document, request.clip_id)
    affected = set()
    for item in request.segments:
        if item.text != item.before:
            affected.update(editable.intersection(by_id[item.segment_id].affected_clip_ids))
            update_review_segment(document, item.segment_id, item.text, clip_id=request.clip_id)
    return affected
