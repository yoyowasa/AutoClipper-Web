"""Identify explicit draft changes, independently of subtitle revision changes."""

from app.production_choice_capture import CONTENT_GROUPS


def changed_manual_fields(before, after, request) -> set[str]:
    changed = set()
    for name in request.model_fields_set - {"segments", "post_metadata_revision_hash"}:
        if name == "framing":
            if request.framing is not None and any(
                getattr(request.framing, field) is not None
                and getattr(before, field) != getattr(request.framing, field)
                and getattr(before, field) != getattr(after, field)
                for field in request.framing.model_fields_set
            ):
                changed.add(name)
        elif (getattr(request, name) != getattr(before, name)
              and getattr(before, name) != getattr(after, name)):
            # Compare both input and saved result: server-side invalidation and
            # normalization are not human decisions.
            changed.add(name)
    return changed


def manual_choice_kinds(fields: set[str], request) -> set[str]:
    aliases = {type(request).model_fields[name].alias or name for name in fields}
    kinds = {kind for kind, names in CONTENT_GROUPS.items() if aliases.intersection(names)}
    if "subtitle_styles" in fields:
        kinds.add("effects")
    if "framing" in fields:
        kinds.add("framing")
    if fields.intersection({"youtube_description", "youtube_tags", "youtube_hashtags", "post_metadata_source"}):
        kinds.add("post_copy")
    if fields.intersection({"title_candidates", "selected_title_id", "recommended_title_id"}):
        kinds.add("title_hook")
    if fields.intersection({"thumbnail_kicker", "thumbnail_line1", "thumbnail_line2", "thumbnail_frame_seconds"}):
        kinds.add("thumbnail")
    return kinds
