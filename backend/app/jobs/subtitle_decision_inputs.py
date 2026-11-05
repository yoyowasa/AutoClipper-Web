"""Dependencies of the existing generators; no new model or prompt."""
from app.cue_styles import manual_style, cue_style_values
from app.production_choices import value_hash

ALL_TARGETS = {"title_hook", "thumbnail_copy", "thumbnail_image", "framing", "text_style", "effects"}


def decision_inputs(document, clip):
    ids = set(clip.segment_ids)
    text = [(s.id, s.start, s.end, s.text) for s in document.segments if s.id in ids]
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
    if manual_style(clip.manual_decision_fields, "subtitle_styles"):
        targets.discard("effects")
    return targets


def subtitle_edit_targets(before, previous, document, clip):
    # Per-cue styles belong to the clip, not to shared transcript rows. A style
    # change only needs the existing preview/render continuation, never Codex.
    if (cue_style_values(previous.subtitle_styles) != cue_style_values(clip.subtitle_styles)
            and decision_inputs(before, previous) == decision_inputs(document, clip)):
        return set()
    targets = changed_targets(before, previous, document, clip)
    if cue_style_values(previous.subtitle_styles) != cue_style_values(clip.subtitle_styles):
        targets.discard("effects")  # Do not overwrite cue styles submitted with text edits.
    return targets
