"""Decide normal thumbnail copy from confirmed review input, before publication."""

import os

from app.jobs.thumbnail_copy import (
    build_copy_payload, copy_request, copy_state_path, confirmed_copy_state_path,
    generate_validated_copy, read_copy_state, write_copy_state,
)
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.production_choice_capture import best_effort_capture
from app.production_choices import append_choice, dump_history, merge_history, value_hash
from app.scoring.thumbnail_copy import THUMBNAIL_COPY_PROMPT_VERSION, CodexThumbnailCopyGenerator, ThumbnailCopySubjectError


COPY_FIELDS = {"thumbnailKicker": "thumbnail_kicker", "thumbnailLine1": "thumbnail_line1", "thumbnailLine2": "thumbnail_line2"}


def manually_selected_copy(review, clip_id: str, values: dict) -> bool:
    previous = None
    manual = None
    for choice in review.choice_history:
        if choice.clipId != clip_id:
            continue
        current = {key: choice.values.get(key, "") for key in COPY_FIELDS}
        if choice.kind == "thumbnail" and choice.source == "manual" and choice.stage == "applied":
            manual = current
        elif choice.kind == "title_hook" and any(key in choice.values for key in COPY_FIELDS):
            # Older 1-A records grouped thumbnail copy with title/hook. A subtitle or
            # publication-title edit alone must not be mistaken for manual copy.
            if choice.source == "manual" and previous is not None and current != previous:
                manual = current
            previous = current
    return manual is not None and manual == values


def decide_thumbnail_copy(*, review, export, paths, metadata: dict, generator=None) -> dict:
    clip = next(c for c in review.clips if c.id == export.candidate_id)
    values = {key: getattr(clip, attr) for key, attr in COPY_FIELDS.items()}
    history = merge_history(metadata.get("choiceHistory", []))
    if manually_selected_copy(review, clip.id, values):
        append_choice(history, kind="thumbnail", clipId=clip.id, stage="applied", source="manual",
                      values=values, policyVersion=THUMBNAIL_COPY_PROMPT_VERSION, reason="manual_thumbnail_copy_preserved")
        return {**metadata, **{attr: values[key] for key, attr in COPY_FIELDS.items()},
                "thumbnail_copy_source": "manual", "thumbnail_copy_error": None,
                "thumbnail_copy_recommended_id": None, "thumbnail_copy_selected_id": None, "choiceHistory": dump_history(history)}
    if clip.type != "normal" or not clip.confirmed or review.state not in {"render_queued", "rendering", "completed"}:
        raise ValueError("確定した通常動画の字幕からサムネ文言を生成してください。")
    source = [s.model_dump() for s in review.segments if s.id in set(clip.segment_ids)]
    payload = build_copy_payload(source, start=clip.start, end=clip.end, publication_title=export.title)
    content_hash = value_hash({"payload": payload, "start": clip.start, "end": clip.end, "version": THUMBNAIL_COPY_PROMPT_VERSION})
    # Keep retries/re-exports of the same confirmed input in the existing suggestion
    # directory. Export IDs can change after a failed publication.
    path = confirmed_copy_state_path(paths, export.job_id, clip.id, content_hash)
    with subtitle_review_document_lock(paths.job_outputs(export.job_id)):
        state = read_copy_state(path)
        generate = state.get("contentHash") != content_hash
        if generate:
            state = {"state": "generating", "contentHash": content_hash, "payload": payload, "clipId": clip.id,
                     "promptVersion": THUMBNAIL_COPY_PROMPT_VERSION, "suggestions": [], "recommendedId": None,
                     "requestId": content_hash, "error": None}
            write_copy_state(path, state)
    if generate:
        try:
            active = generator or CodexThumbnailCopyGenerator(
                storage_root=paths.root, job_id=export.job_id, clip_id=f"thumb_{clip.id}",
                model=os.environ.get("CODEX_TITLE_HOOK_MODEL", "codex-default"),
            )
            result = generate_validated_copy(active, payload)
            state.update(**result.model_dump(by_alias=True), state="ready")
        except Exception as exc:
            error = str(exc) if type(exc) is ValueError or isinstance(exc, ThumbnailCopySubjectError) else (
                "サムネ文言を生成できませんでした。Codexの接続を確認して再生成してください。"
            )
            state.update(state="failed", error=error, errorType=type(exc).__name__)
        write_copy_state(path, state)
        state = read_copy_state(path)
    if state["state"] != "ready":
        state.update(state="failed", error=state.get("error") or "サムネ文言の自動生成が中断されました。")
    selected = next((s for s in state["suggestions"] if s["id"] == state["recommendedId"]), None) if state["state"] == "ready" else None
    if selected:
        values = dict(zip(COPY_FIELDS, (selected["heading"], selected["upper"], selected["lower"]), strict=True))
    history = merge_history(history, state.get("choiceHistory", []))
    append_choice(history, kind="thumbnail", clipId=clip.id, stage="applied", source="automatic" if selected else "fallback",
                  values=values, inputRevision=content_hash, policyVersion=THUMBNAIL_COPY_PROMPT_VERSION,
                  selectedIds=[selected["id"]] if selected else [], recommendedId=state["recommendedId"] if selected else None,
                  reason=selected["reason"] if selected else f"thumbnail_copy_failed:{state.get('errorType', 'Interrupted')}")
    # Completed editing can reuse these exact proposals. Its stale-video guard still
    # includes the real rendered file's identity, unlike the confirmed-input cache.
    request = copy_request(payload, start=clip.start, end=clip.end, video_stat=paths.resolve_stored_file(export.video_path).stat())
    write_copy_state(copy_state_path(paths, export), {**state, **request, "choiceHistory": dump_history(history)})
    return {**metadata, **{attr: values[key] for key, attr in COPY_FIELDS.items()},
            "thumbnail_copy_source": "automatic" if selected else "fallback",
            "thumbnail_copy_error": state.get("error"), "thumbnail_copy_recommended_id": state["recommendedId"] if selected else None,
            "thumbnail_copy_selected_id": selected["id"] if selected else None, "choiceHistory": dump_history(history)}


@best_effort_capture
def record_manual_copy(payload: dict, *, db, paths, export, revision) -> dict:
    if payload.get("thumbnail_copy_source") != "manual":
        return payload
    from app.jobs.thumbnail_copy import build_copy_input
    state = read_copy_state(copy_state_path(paths, export))
    keys = {"heading": "thumbnail_kicker", "upper": "thumbnail_line1", "lower": "thumbnail_line2"}
    matched = None
    try:
        if state.get("inputHash") == build_copy_input(db, paths, export)["inputHash"] and state.get("state") == "ready":
            matches = [s["id"] for s in state["suggestions"]
                       if all(s[key].strip() == payload.get(attr, "") for key, attr in keys.items())]
            matched = matches[0] if len(matches) == 1 else None
    except (OSError, ValueError):
        pass  # Manual copy remains editable without usable confirmed subtitle input.
    payload["thumbnail_copy_selected_id"] = matched
    payload["thumbnail_copy_recommended_id"] = state.get("recommendedId") if matched else None
    history = merge_history(payload.get("choiceHistory", []))
    append_choice(history, kind="thumbnail", clipId=export.candidate_id, source="manual", stage="applied",
                  inputRevision=str(revision), selectedIds=[matched] if matched else [],
                  recommendedId=payload["thumbnail_copy_recommended_id"],
                  values={key: payload.get(attr, "") for key, attr in (
                      ("thumbnailKicker", "thumbnail_kicker"), ("thumbnailLine1", "thumbnail_line1"),
                      ("thumbnailLine2", "thumbnail_line2"))})
    payload["choiceHistory"] = dump_history(history)
    return payload
