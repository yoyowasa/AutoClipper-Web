"""Project the existing work artifacts into the permanent production record."""

from app.production_choices import append_choice, choice_values, merge_history
from app.production_choice_capture import read_history


def recorded_choices(paths, export, metadata, previous):
    from app.jobs.clip_plan import clip_plan_output_path
    from app.jobs.subtitle_review import subtitle_review_output_path
    from app.jobs.title_hook_suggestions import title_hook_suggestions_path
    from app.jobs.thumbnail_copy import copy_state_path
    from app.candidates.select_candidates import selected_clips_output_path

    root = paths.job_outputs(export.job_id)
    history = merge_history(previous.choiceHistory if previous else [], metadata.get("choiceHistory", []), *[
        read_history(path) for path in (
            selected_clips_output_path(root), clip_plan_output_path(root), subtitle_review_output_path(root),
            title_hook_suggestions_path(root, export.candidate_id), copy_state_path(paths, export),
        )
    ])
    return [choice for choice in history if choice.scope == "job" or choice.clipId == export.candidate_id]


def record_publication(record, *, observed: bool = False):
    """Capture what was published, without pretending to know historical decisions."""
    append_choice(record.choiceHistory, kind="publication", clipId=record.selection.candidateId,
                  stage="observed" if observed else "published",
                  inputRevision=f"{record.recordId}:{record.revision}", policyVersion="production-record-v1",
                  values=choice_values(record.model_dump(mode="json")))
    return record
