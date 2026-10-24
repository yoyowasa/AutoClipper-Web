"""Capture evidence in the artifacts that already own the decision, without new files."""

import json
import logging
from pathlib import Path
from functools import wraps

from app.production_choices import (
    ChoiceCandidate, append_choice, choice_values, dump_history, merge_history, value_hash,
)


logger = logging.getLogger(__name__)


def best_effort_capture(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            logger.warning("Choice capture failed: operation=%s errorType=%s", function.__name__, type(exc).__name__)
            # Mapping writers need the original payload; model writers return None.
            return args[0] if isinstance(args[0], dict) else None
    return wrapped


CONTENT_GROUPS = {
    "title_hook": ("title", "publicationTitle", "hookText", "hookDurationSeconds", "hookSceneStart", "hookSceneEnd",
                   "selectedTitleId", "recommendedTitleId", "thumbnailKicker", "thumbnailLine1", "thumbnailLine2"),
    "framing": ("framingOffsetX", "framingOffsetY", "framingZoom", "shortLayout"),
    "text_style": ("titleStyle", "hookStyle", "subtitleStyle", "resolvedTitleStyle", "resolvedHookStyle", "resolvedSubtitleStyle"),
}


def read_history(path: Path | None) -> list:
    if path is None or not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("choiceHistory", [])


def capture_document(document, path: Path | None, *, kind: str, source="unrecorded", clip_ids=None, kinds=None) -> None:
    """Called at existing save boundaries. Preview/status-only saves add no decisions."""
    try:
        history = merge_history(read_history(path), document.choice_history)
        payload = document.model_dump(mode="json", by_alias=True)
        if kind == "plan" and document.state not in {"awaiting_review", "approved", "manual_editing"}:
            document.choice_history = history
            return
        for clip in payload["clips"]:
            if clip_ids is not None and clip["id"] not in clip_ids:
                continue
            if kind == "plan":
                from app.candidates.manual_ranges import MANUAL_SELECTION_REASON
                groups = {"range": {key: clip.get(key) for key in (
                    "type", "start", "end", "hookSceneStart", "hookSceneEnd", "longformReason")}}
                revision = f"clip-plan:{document.created_at}:{document.revision}"
            else:
                from app.posting_metadata import build_post_metadata_revision_hash
                groups = {key: {name: clip.get(name) for name in names} for key, names in CONTENT_GROUPS.items()}
                groups["post_copy"] = {
                    "postMetadataSource": clip.get("postMetadataSource"),
                    # Posting descriptions can contain contact details. Keep comparison hashes, not their body.
                    **{name: value_hash(clip.get(key)) for name, key in (
                        ("descriptionHash", "youtubeDescription"), ("tagsHash", "youtubeTags"), ("hashtagsHash", "youtubeHashtags"))},
                }
                if source == "manual" and path is not None and path.is_file():
                    old_clip = next((c for c in json.loads(path.read_text(encoding="utf-8")).get("clips", [])
                                     if c["id"] == clip["id"]), None)
                    copy_keys = ("thumbnailKicker", "thumbnailLine1", "thumbnailLine2")
                    if old_clip and any(old_clip.get(key, "") != clip.get(key, "") for key in copy_keys):
                        append_choice(history, kind="thumbnail", clipId=clip["id"], stage="applied", source="manual",
                                      values={key: clip.get(key, "") for key in copy_keys},
                                      policyVersion="subtitle-review-v1", reason="manual_thumbnail_copy")
                segment_ids = set(clip.get("segmentIds", []))
                revision = build_post_metadata_revision_hash(
                    clip_id=clip["id"], clip_type=clip["type"], start=clip["start"], end=clip["end"],
                    segments=[{"segmentId": s["id"], "text": s["text"],
                               "start": min(clip["duration"], max(0, s["start"] - clip["start"])),
                               "end": min(clip["duration"], max(0, s["end"] - clip["start"]))}
                              for s in sorted(payload["segments"], key=lambda s: s["index"]) if s["id"] in segment_ids])
            for choice_kind, values in groups.items():
                if kinds is not None and choice_kind not in kinds:
                    continue
                # Compare actual values, independently of preview state and save timestamps.
                previous = next((c for c in reversed(history) if c.kind == choice_kind and c.clipId == clip["id"]), None)
                if previous and previous.values == values and previous.inputRevision == revision:
                    continue
                candidates = []
                selected_id = None
                if choice_kind == "title_hook" and clip.get("postMetadataRevisionHash") == revision:
                    selected_id = next((c["id"] for c in clip.get("titleCandidates", [])
                                        if c["id"] == clip.get("selectedTitleId") and c["title"] == clip.get("publicationTitle")), None)
                    candidates = [ChoiceCandidate(id=c["id"], values=choice_values(c), reason=c.get("reason"),
                                  outcome="selected" if c["id"] == selected_id else "not_selected")
                                  for c in clip.get("titleCandidates", [])]
                resolved_source = source
                if kind == "plan" and (clip["id"] in document.settings.get("keptClipIds", []) or
                                       clip.get("selectionReason") == MANUAL_SELECTION_REASON):
                    resolved_source = "manual"
                append_choice(history, kind=choice_kind, clipId=clip["id"], source=resolved_source,
                              timeBasis="source",
                              stage="observed" if resolved_source == "unrecorded" else "applied", values=values,
                              inputRevision=revision, policyVersion="clip-plan-v3" if kind == "plan" else "subtitle-review-v1",
                              reason=clip.get("selectionReason") if kind == "plan" else None, candidates=candidates,
                              selectedIds=[selected_id] if selected_id else [],
                              recommendedId=clip.get("recommendedTitleId") if candidates else None)
        if kind == "plan" and path is not None and path.is_file():
            before = json.loads(path.read_text(encoding="utf-8"))
            ids = {clip["id"] for clip in payload["clips"]}
            for clip in before.get("clips", []):
                if clip["id"] not in ids:
                    append_choice(history, kind="range", scope="job", stage="removed", source=source,
                                  inputRevision=f"clip-plan:{document.created_at}:{document.revision}",
                                  candidates=[ChoiceCandidate(id=clip["id"], values=choice_values(clip), outcome="not_selected")])
        document.choice_history = history
    except Exception as exc:
        logger.warning("Choice capture failed: kind=%s errorType=%s", kind, type(exc).__name__)


@best_effort_capture
def capture_auto_review_outcome(document, clip_id: str, *, error_type: str | None = None, input_revision=None) -> None:
    from app.jobs.automation import HUMAN_SUBTITLE_REVIEW_POLICY, SUBTITLE_ONLY_AUTO_POLICY
    clip = next(item for item in document.clips if item.id == clip_id)
    manual_override = document.subtitle_only_auto and bool(set(clip.manual_decision_fields) & {
        "title", "publication_title", "hook_text", "hook_scene_start", "hook_scene_end",
        "youtube_description", "youtube_tags", "youtube_hashtags", "selected_title_id", "post_metadata_source",
    })
    append_choice(
        document.choice_history, kind="title_hook", clipId=clip_id, stage="observed",
        source="manual" if manual_override else "automatic",
        policyVersion=SUBTITLE_ONLY_AUTO_POLICY if document.subtitle_only_auto else HUMAN_SUBTITLE_REVIEW_POLICY,
        inputRevision=input_revision,
        reason=f"automatic_copy_failed:{error_type}" if error_type else (
            "explicit_manual_override_preserved" if manual_override else
            "confirmed_subtitles_used_for_automatic_decision" if document.subtitle_only_auto else "human_subtitle_review_required"
        ),
        selectedIds=[clip.selected_title_id] if not error_type and clip.selected_title_id else [],
        values=choice_values(clip.model_dump(by_alias=True, mode="json")) if not error_type else {},
    )


@best_effort_capture
def capture_proposals(payload: dict, path: Path, *, kind, policy_version, clip_id=None) -> dict:
    history = merge_history(read_history(path), payload.get("choiceHistory", []))
    if payload.get("state") == "ready":
        append_choice(history, kind=kind, clipId=clip_id, scope="clip" if clip_id else "job", stage="proposed",
                      source="automatic" if policy_version else "unrecorded",
                      timeBasis="clip",
                      inputRevision=payload.get("revisionHash") or payload.get("inputHash") or payload.get("requestId"),
                      policyVersion=policy_version, recommendedId=payload.get("recommendedSuggestionId", payload.get("recommendedId")),
                      candidates=[ChoiceCandidate(id=c["id"], values=choice_values({**c,
                          **({"thumbnailKicker": c["heading"], "thumbnailLine1": c["upper"], "thumbnailLine2": c["lower"]}
                             if "heading" in c else {})}), reason=c.get("reason")) for c in payload.get("suggestions", [])])
    return {**payload, "choiceHistory": dump_history(history)}


@best_effort_capture
def retain_discarded_review_history(plan, review, output: Path) -> None:
    from app.jobs.title_hook_suggestions import title_hook_suggestions_path
    plan.choice_history = merge_history(plan.choice_history, review.choice_history, *[
        read_history(title_hook_suggestions_path(output, clip.id)) for clip in review.clips
    ])


@best_effort_capture
def capture_selection(selection, path: Path) -> None:
    history = merge_history(read_history(path), selection.choice_history)
    candidates = [ChoiceCandidate(id=c.id, outcome="selected", reason=c.selection_reason or c.reason,
                                  values=choice_values({"type": c.type, "start": c.start, "end": c.end,
                                                        "score": c.final_score, "openingScore": c.opening_score,
                                                        "topicKey": c.topic_key, "longformReason": c.longform_reason}))
                  for c in [*selection.normal_clips, *selection.shorts]]
    candidates += [ChoiceCandidate(id=c.candidate_id, outcome="rejected", reason=",".join(c.reasons),
                                   values=choice_values({"type": c.type, **c.details})) for c in selection.rejected_candidates]
    append_choice(history, kind="range", scope="job", source="unrecorded", stage="observed",
                  timeBasis="source",
                  inputRevision=value_hash([c.model_dump() for c in candidates]), policyVersion=selection.selection_policy,
                  candidates=candidates, selectedIds=[c.id for c in candidates if c.outcome == "selected"])
    selection.choice_history = history


@best_effort_capture
def thumbnail_choice(payload: dict, *, clip_id: str, source="unrecorded") -> dict:
    history = merge_history(payload.get("choiceHistory", []))
    keys = {
        "source": "thumbnail_subject_source", "assetId": "thumbnail_character_asset_id", "emotion": "thumbnail_emotion",
        "cropMode": "thumbnail_crop_mode", "templateVersion": "thumbnail_template_version",
        "templateDesign": "thumbnail_design",
        "subjectPlacement": "thumbnail_subject_placement", "textStyles": "thumbnail_text_styles",
        "thumbnailKicker": "thumbnail_kicker", "thumbnailLine1": "thumbnail_line1", "thumbnailLine2": "thumbnail_line2",
        "thumbnailFrameSeconds": "thumbnail_frame_seconds", "frameCandidateId": "thumbnail_frame_candidate_id",
    }
    chosen = payload.get("thumbnail_frame_candidate_id")
    append_choice(history, kind="thumbnail", clipId=clip_id, stage="published", source=source,
                  timeBasis="clip",
                  inputRevision=str(payload.get("thumbnail_render_revision", 0)), policyVersion="thumbnail-existing-v1",
                  reason=payload.get("thumbnail_subject_reason"), values=choice_values({k: payload.get(v) for k, v in keys.items()}),
                  selectedIds=[chosen] if chosen else [], candidates=[ChoiceCandidate(
                      id=c["id"], outcome="selected" if c["id"] == chosen else "not_selected",
                      values=choice_values({"second": c["second"], "score": c.get("score"), "closeAvailable": c.get("close_available")}))
                      for c in payload.get("thumbnail_frame_candidates", [])])
    return {**payload, "choiceHistory": dump_history(history)}
