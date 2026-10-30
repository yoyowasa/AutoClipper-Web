"""Connect file inspection to existing targeted rendering and publication recovery."""

from copy import deepcopy
from app.inspection.models import failures, stop_message
from app.inspection.service import FinalInspectionFailed, inspect_final_outputs
from app.jobs.pipeline_common import PipelineExpectedError
from app.jobs.subtitle_review import apply_reviewed_clip_content, write_subtitle_review, subtitle_review_output_path
from app.production_choices import append_choice, choice_values

REPAIR_POLICY = "final-output-local-repair-v1"


def restore_manual_editor(db, job, paths, message):
    from app.jobs.clip_plan import load_clip_plan, write_clip_plan, clip_plan_output_path
    from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP

    path = clip_plan_output_path(paths.job_outputs(job.id))
    plan = load_clip_plan(path)
    plan.state = "manual_editing"
    plan.settings = {**plan.settings, "manualEditFinalized": False}
    write_clip_plan(plan, path)
    job.settings_json = {**(job.settings_json or {}), "manualEditFinalized": False}
    job.status, job.progress = "awaiting_manual_edit", PROGRESS_MAP["awaiting_manual_edit"]
    job.current_step = CURRENT_STEP_MAP["awaiting_manual_edit"]
    job.error_code, job.error_message = "final_output_incomplete", message
    db.commit()


def regenerate_content(document, clip, *, source, paths, settings, dependencies):
    from app.jobs.title_hook_suggestions import apply_recommended_title_hook_suggestions
    from app.jobs.automatic_thumbnail_copy import confirmed_thumbnail_copy, COPY_FIELDS
    from app.intelligence.choice_policy_runtime import choose_title_suggestion
    from app.intelligence.performance_hints import active_hint_uses

    preserved = {name: deepcopy(getattr(clip, name)) for name in clip.manual_decision_fields if hasattr(clip, name)}
    hints = (
        active_hint_uses(settings.get("_performanceHints"), target="title_hook", format=clip.type)
        if settings.get("usePerformanceHints", True)
        else []
    )
    artifact = dependencies.auto_title_hook_generator(
        document=document,
        clip_id=clip.id,
        source_path=source,
        paths=paths,
        model=str(settings.get("titleHookModel") or "codex-default"),
        force_regenerate=True,
        audience_familiarity="unknown" if settings.get("audienceFamiliarity") == "unknown" else "known",
        **({"performance_hints": hints} if hints else {}),
    )
    try:
        apply_recommended_title_hook_suggestions(
            document,
            artifact,
            youtube_source_title=str(settings.get("youtubeSourceTitle") or ""),
            youtube_source_url=str(settings.get("youtubeSourceUrl") or ""),
            youtube_posting_profile=settings.get("youtubePostingProfile"),
            selected_suggestion_id=choose_title_suggestion(artifact, settings, clip.type),
        )
        if clip.type == "normal":
            state, _, _ = confirmed_thumbnail_copy(document, clip, paths, dependencies.thumbnail_copy_generator, force_regenerate=True)
            if state["state"] != "ready":
                raise ValueError("thumbnail copy unavailable")
            selected = next(s for s in state["suggestions"] if s["id"] == state["recommendedId"])
            for attr, value in zip(COPY_FIELDS.values(), (selected["heading"], selected["upper"], selected["lower"])):
                setattr(clip, attr, value)
    finally:
        for name, value in preserved.items():
            setattr(clip, name, value)
    append_choice(
        document.choice_history,
        kind="title_hook",
        clipId=clip.id,
        stage="applied",
        source="fallback",
        policyVersion=REPAIR_POLICY,
        reason="final_output_content_mismatch",
        values=choice_values(clip.model_dump(by_alias=True, mode="json")),
    )


def refit_subtitle(document, clip, *, settings, video):
    from app.jobs.automatic_text_style import choose_emphasis, choose_text_styles
    from app.jobs.quality_gate import _subtitle_events_for_review_clip
    from app.render.render_short import SHORT_BANNER_HEIGHT
    from app.render.subtitles_ass import SubtitleLayout

    layout = (
        SubtitleLayout.short(settings)
        if clip.type == "short"
        else SubtitleLayout.normal(video.width or 1920, video.height or 1080, settings)
    )
    top = SHORT_BANNER_HEIGHT if clip.type == "short" and settings.get("shortTopBannerEnabled") else 0
    bottom = layout.height - (SHORT_BANNER_HEIGHT if clip.type == "short" and settings.get("shortBottomBannerEnabled") else 0)
    events, _ = _subtitle_events_for_review_clip(document, clip, width=layout.width, height=layout.height)
    manual = list(clip.manual_decision_fields)
    try:
        clip.manual_decision_fields = list(set(manual) | {"title_style", "hook_style"})
        choose_text_styles(clip, layout, events=events, top=top, bottom=bottom, settings=settings)
        choose_emphasis(clip, [s for s in document.segments if s.id in clip.segment_ids], layout, top=top, bottom=bottom, settings=settings)
    finally:
        clip.manual_decision_fields = manual
    append_choice(
        document.choice_history,
        kind="text_style",
        clipId=clip.id,
        stage="applied",
        source="fallback",
        policyVersion=REPAIR_POLICY,
        reason="final_output_subtitle_safe_area",
        values=choice_values({"subtitleStyle": clip.subtitle_style.model_dump(by_alias=True)}),
    )
    if "subtitle_styles" not in manual:
        append_choice(
            document.choice_history,
            kind="effects",
            clipId=clip.id,
            stage="applied",
            source="fallback",
            policyVersion=REPAIR_POLICY,
            reason="final_output_subtitle_safe_area",
            values=choice_values({"subtitleStyles": [s.model_dump(by_alias=True) for s in clip.subtitle_styles]}),
        )


def inspect_pipeline_outputs(
    *,
    db,
    job,
    video,
    source,
    selection,
    segments,
    settings,
    paths,
    render_paths,
    dependencies,
    exports,
    normal_result,
    short_result,
    document=None,
    retained_exports=(),
    automation_mode=None,
):
    from app.jobs import runner

    def progress(label):
        job.current_step = f"{label}の完成MP4を検査中"
        db.commit()

    def repair(clip_id, action):
        clip = next((c for c in document.clips if c.id == clip_id), None) if document is not None else None
        if action == "regenerate_content":
            regenerate_content(document, clip, source=source, paths=paths, settings=settings, dependencies=dependencies)
        elif action == "refit_subtitle":
            refit_subtitle(document, clip, settings=settings, video=video)
        if document is not None:
            revised = apply_reviewed_clip_content(selection, document)
            selection.normal_clips, selection.shorts = revised.normal_clips, revised.shorts
            write_subtitle_review(document, subtitle_review_output_path(paths.job_outputs(job.id)))
        old = [e for e in exports if e.candidate_id == clip_id]
        new_normal, new_short, replacements, _ = runner._render_selected_outputs(
            db=db,
            job=job,
            video=video,
            input_path=source,
            selection=selection,
            transcript_segments=segments,
            settings=settings,
            storage_paths=render_paths,
            asset_storage_paths=paths,
            dependencies=dependencies,
            visited_statuses=[],
            render_clip_ids={clip_id},
        )
        if not replacements or new_normal.failures or new_short.failures:
            raise ValueError("targeted repair render failed")
        for item in old:
            db.delete(item)
        db.commit()
        replacement = replacements[0]
        if old:
            exports[:] = [replacement if e.candidate_id == clip_id else e for e in exports]
        else:
            exports.extend(replacements)
        for result, new in ((normal_result, new_normal), (short_result, new_short)):
            if any(e.candidate_id == clip_id for e in result.exports):
                result.exports[:] = [new.exports[0] if e.candidate_id == clip_id else e for e in result.exports]
            else:
                result.exports.extend(new.exports)
            result.failures[:] = [f for f in result.failures if f.candidate_id != clip_id] + new.failures
        runner.generate_export_thumbnails(
            exports=replacements,
            selection=selection,
            input_path=source,
            job_output_dir=render_paths.job_outputs(job.id),
            normal_renderer=dependencies.normal_thumbnail_renderer,
            short_renderer=dependencies.short_thumbnail_renderer,
            character_style=settings.get("normalThumbnailStyle"),
            db=db,
            job=job,
            paths=paths,
            **({"review_document": document, "copy_generator": dependencies.thumbnail_copy_generator} if document is not None else {}),
        )
        if automation_mode is not None:
            gate_exports = (
                runner._project_staged_exports_for_quality_gate(
                    exports, staging_job_dir=render_paths.job_outputs(job.id), canonical_job_dir=paths.job_outputs(job.id)
                )
                if render_paths != paths
                else exports
            )
            gate = runner.evaluate_post_render_quality_gate(
                job_id=job.id,
                expected_export_count=len(selection.normal_clips) + len(selection.shorts),
                exports=[*gate_exports, *retained_exports],
                render_failures=[*normal_result.failures, *short_result.failures],
                mode=automation_mode,
                document=document,
            )
            written = runner._try_write_quality_gate_decision(
                gate, runner.quality_gate_decision_path(paths.job_outputs(job.id), "post_render")
            )
            if automation_mode in {"auto", "guarded"} and (written is None or gate.route != "continue"):
                raise ValueError("existing final quality gate rejected repaired output")
            if action == "regenerate_content" and document is not None:
                content = runner.evaluate_content_quality_gate(
                    job_id=job.id,
                    document=document,
                    settings=settings,
                    mode=automation_mode,
                    title_hook_evidence=runner._load_title_hook_evidence(paths.job_outputs(job.id), document),
                )
                written = runner._try_write_quality_gate_decision(
                    content, runner.quality_gate_decision_path(paths.job_outputs(job.id), "content")
                )
                if automation_mode in {"auto", "guarded"} and (written is None or content.route != "continue"):
                    raise ValueError("existing content gate rejected repaired proposal")
        return replacements[0], next(c for c in [*selection.normal_clips, *selection.shorts] if c.id == clip_id)

    inspector = dependencies.final_output_inspector or inspect_final_outputs
    try:
        result = inspector(
            exports=exports,
            selection=selection,
            source=source,
            segments=segments,
            settings=settings,
            video=video,
            paths=paths,
            job_id=job.id,
            document=document,
            repair=repair,
            progress=progress,
            clip_ids={c.id for c in [*selection.normal_clips, *selection.shorts]} - {e.candidate_id for e in retained_exports},
        )
        exports[:] = result
        if document is not None:
            document.automatic_stop_reasons = []
    except FinalInspectionFailed as error:
        if document is not None:
            document.state = "awaiting_review"
            document.automatic_stop_reasons = [stop_message(r) for r in error.records if r.outcome != "pass"]
            write_subtitle_review(document, subtitle_review_output_path(paths.job_outputs(job.id)))
        raise PipelineExpectedError(
            "final_output_incomplete",
            str(error),
            details={
                "finalInspection": [
                    {"clipLabel": r.label, "reason": stop_message(r), "repairCount": sum(bool(a.repair) for a in r.attempts)}
                    for r in error.records
                    if failures(r)
                ]
            },
        ) from None
    except (OSError, ValueError):
        raise PipelineExpectedError("final_output_record_failed", "完成検査の記録を保存できないため停止しました。") from None
