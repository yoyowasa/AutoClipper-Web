"""Make production decisions from one human-confirmed subtitle snapshot."""

from uuid import uuid4

from app.db import SessionLocal
from app.intelligence.performance_hints import active_hint_uses, attach_performance_hints
from app.jobs.automation import is_subtitle_only_auto
from app.jobs.automatic_thumbnail_copy import COPY_FIELDS, confirmed_thumbnail_copy
from app.jobs.subtitle_review import (
    confirm_review_clip, load_subtitle_review, refresh_review_render_contract,
    subtitle_review_output_path, subtitle_review_summary_path, write_subtitle_review, write_subtitle_review_summary,
)
from app.jobs.subtitle_review_preview import refresh_subtitle_review_preview_states, subtitle_review_document_lock
from app.jobs.title_hook_suggestions import apply_recommended_title_hook_suggestions, generate_title_hook_suggestions_for_auto
from app.models import Job, Video
from app.production_choice_capture import capture_auto_review_outcome
from app.storage.paths import get_storage_paths


def queue_clip_decisions(document, clip, request) -> str:
    """Called under the document lock, after subtitle edits have been saved."""
    fields = request.model_fields_set - {"segments", "post_metadata_revision_hash"}
    clip.manual_decision_fields = sorted(set(clip.manual_decision_fields) | fields)
    clip.automatic_decision_revision = uuid4().hex
    clip.automatic_decision_state = "queued"
    clip.automatic_decision_error = None
    clip.preview_deferred = True
    clip.preview_state = "stale"
    clip.preview_video_url = None
    document.subtitle_only_auto = True
    return clip.automatic_decision_revision


def record_decision_failure(paths, job_id, clip_id, revision, message):
    directory = paths.job_outputs(job_id)
    with subtitle_review_document_lock(directory):
        path = subtitle_review_output_path(directory)
        if not path.is_file():
            return
        document = load_subtitle_review(path)
        clip = next((c for c in document.clips if c.id == clip_id), None)
        if clip and clip.automatic_decision_revision == revision and document.state == "awaiting_review":
            clip.automatic_decision_state = "failed"
            clip.automatic_decision_error = f"{clip.id}（元動画 {clip.start:.1f}〜{clip.end:.1f}秒）: {message}"
            write_subtitle_review(document, path)


def run_confirmed_clip_decisions(job_id, clip_id, revision, *, session_factory=SessionLocal, paths=None,
                                 generator=generate_title_hook_suggestions_for_auto, thumbnail_generator=None,
                                 enqueue_preview=None, candidate_extractor=None, emotion_selector=None, crop_resolver=None,
                                 framing_selector=None):
    paths = paths or get_storage_paths()
    directory = paths.job_outputs(job_id)
    path = subtitle_review_output_path(directory)
    stage = "タイトル・フック・投稿文の自動決定"
    try:
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job is None or not is_subtitle_only_auto(job.settings_json or {}):
                return "superseded"
            video = db.get(Video, job.video_id)

            def current():
                db.refresh(job)
                if job.status != "awaiting_subtitle_review" or not path.is_file():
                    return None
                doc = load_subtitle_review(path)
                item = next((c for c in doc.clips if c.id == clip_id), None)
                if doc.state != "awaiting_review" or item is None or not item.confirmed:
                    return None
                if item.automatic_decision_revision != revision:
                    return None
                return doc

            with subtitle_review_document_lock(directory):
                document = current()
                if document is None:
                    return "superseded"
                clip = next(c for c in document.clips if c.id == clip_id)
                if clip.automatic_decision_state != "queued":
                    return "superseded"
                clip.automatic_decision_state = "generating"
                write_subtitle_review(document, path)
                generation = (document.created_at, document.preview_generation)

            # No document lock while waiting for Codex. Other clips remain editable.
            settings = attach_performance_hints(db, dict(job.settings_json or {}))
            hints = active_hint_uses(settings.get("_performanceHints"), target="title_hook", format=clip.type) \
                if settings.get("usePerformanceHints", True) else []
            overrides = {name: getattr(clip, name) for name in clip.manual_decision_fields if hasattr(clip, name)}
            artifact = generator(
                document=document, clip_id=clip_id, source_path=paths.resolve_stored_file(video.stored_path), paths=paths,
                model=str(settings.get("titleHookModel") or "codex-default"),
                audience_familiarity="unknown" if settings.get("audienceFamiliarity") == "unknown" else "known",
                **({"performance_hints": hints} if hints else {}),
            )
            apply_recommended_title_hook_suggestions(
                document, artifact, youtube_source_title=str(settings.get("youtubeSourceTitle") or ""),
                youtube_source_url=str(settings.get("youtubeSourceUrl") or ""),
                youtube_posting_profile=settings.get("youtubePostingProfile"),
            )
            for name, value in overrides.items():
                setattr(clip, name, value)
            if clip.type == "normal" and not set(COPY_FIELDS.values()).intersection(overrides):
                stage = "サムネ文言の自動決定"
                state, _payload, _hash = confirmed_thumbnail_copy(document, clip, paths, thumbnail_generator, retry_failed=True)
                if state["state"] != "ready":
                    raise ValueError("サムネ文言の生成結果を検証できませんでした。")
                selected = next(s for s in state["suggestions"] if s["id"] == state["recommendedId"])
                for attr, value in zip(COPY_FIELDS.values(), (selected["heading"], selected["upper"], selected["lower"]), strict=True):
                    setattr(clip, attr, value)
            if clip.type == "normal":
                stage = "サムネ画像の自動決定"
                from app.jobs.confirmed_thumbnail import prepare_confirmed_thumbnail
                prepare_confirmed_thumbnail(db, paths, job, video, document, clip,
                                            extractor=candidate_extractor, selector=emotion_selector)
            stage = "画角・文字サイズ・字幕強調の自動決定"
            content_choice, framing_revision = None, None
            if clip.type == "short" and "framing" not in clip.manual_decision_fields:
                from app.jobs.content_framing import choose_content_framing
                content_choice, framing_revision = choose_content_framing(
                    document, clip, paths=paths, source=paths.resolve_stored_file(video.stored_path), selector=framing_selector,
                )
            from app.jobs.automatic_visual_decisions import decide_visuals
            decide_visuals(document, clip, settings=settings, video=video,
                           source=paths.resolve_stored_file(video.stored_path), crop_resolver=crop_resolver,
                           content_choice=content_choice, framing_revision=framing_revision)
            stage = "正式プレビューの準備"
            with subtitle_review_document_lock(directory):
                latest = current()
                if latest is None or (latest.created_at, latest.preview_generation) != generation:
                    return "superseded"
                # Replace only this clip; never overwrite another clip's concurrent edits.
                latest.clips = [clip if c.id == clip_id else c for c in latest.clips]
                from app.production_choices import merge_history
                latest.choice_history = merge_history(latest.choice_history, document.choice_history)
                latest, _ = refresh_review_render_contract(
                    latest, render_mode=str(settings.get("mode", "high_quality")), render_settings=settings,
                    source_width=video.width, source_height=video.height,
                )
                latest, queued, _ = refresh_subtitle_review_preview_states(
                    job=job, video=video, document=latest, paths=paths, clip_ids={clip_id}, generate_exact=True,
                )
                clip.automatic_decision_state = "ready"
                confirm_review_clip(latest, clip_id)
                capture_auto_review_outcome(latest, clip_id, input_revision=artifact.revision_hash)
                write_subtitle_review(latest, path)
                write_subtitle_review_summary(latest, subtitle_review_summary_path(directory))
            if enqueue_preview is None:
                from app.jobs.queue import enqueue_subtitle_review_preview
                enqueue_preview = enqueue_subtitle_review_preview
            for queued_clip, spec_hash in queued:
                enqueue_preview(job_id, queued_clip, spec_hash)
            # A repeated confirmation can reuse an already-ready exact preview.
            # The final transition must not depend on a new preview job being queued.
            from app.jobs.runner import _prepare_auto_render_after_preview, _restore_auto_review_after_enqueue_failure
            render_revision = _prepare_auto_render_after_preview(
                db=db, job=job, video=video, storage_paths=paths, expected_review=latest,
            )
            if render_revision is not None:
                from app.jobs.queue import enqueue_subtitle_review_render
                try:
                    enqueue_subtitle_review_render(job_id, render_revision)
                except Exception:
                    _restore_auto_review_after_enqueue_failure(db=db, job=job, storage_paths=paths)
                    raise
            return "ready"
    except Exception as exc:
        # Never expose Codex output or exception text. The failed stage is actionable.
        record_decision_failure(paths, job_id, clip_id, revision,
                                f"{stage}で停止しました（{type(exc).__name__}）。字幕を確定して再試行してください。")
        return "failed"
