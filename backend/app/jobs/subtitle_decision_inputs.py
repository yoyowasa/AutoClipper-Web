"""Dependencies of the existing generators; no new model or prompt."""
from app.production_choices import value_hash

ALL_TARGETS = {"title_hook", "thumbnail_copy", "thumbnail_image", "framing", "text_style", "effects"}


def decision_inputs(document, clip):
    text = [(s.id, s.start, s.end, s.text) for s in document.segments if s.id in set(clip.segment_ids)]
    content = [clip.title, clip.publication_title, clip.hook_text]
    image = [clip.start, clip.end, clip.thumbnail_frame_seconds]
    # Video-frame harvesting is geometric and range-based; only fallback asset
    # emotion selection consumes subtitles and copy (the existing first 8 rows).
    if clip.automatic_thumbnail and clip.automatic_thumbnail.get("thumbnail_character_asset_id"):
        image += [text[:8], content, clip.thumbnail_kicker, clip.thumbnail_line1, clip.thumbnail_line2]
    return {key: value_hash(value) for key, value in {
        "title_hook": text,
        "thumbnail_copy": [text, content],
        "thumbnail_image": image,
        "framing": [text, content, clip.hook_scene_start, clip.hook_scene_end],
        "text_style": [clip.title, clip.hook_text],
        "effects": [text, content],
    }.items()}


def changed_targets(before, previous, document, clip):
    old = previous.automatic_decision_inputs or decision_inputs(before, previous)
    current = decision_inputs(document, clip)
    targets = {key for key in ALL_TARGETS if old.get(key) != current[key]}
    if previous.automatic_decision_state in {"queued", "generating", "failed"}:
        targets |= (set(previous.automatic_decision_targets) if previous.automatic_decision_targets is not None else ALL_TARGETS)
    if previous.automatic_decision_state == "idle":
        targets = set(ALL_TARGETS)
    if clip.type != "normal":
        targets -= {"thumbnail_copy", "thumbnail_image"}
    if "framing" in clip.manual_decision_fields:
        targets.discard("framing")
    if "subtitle_styles" in clip.manual_decision_fields:
        targets.discard("effects")
    return targets
