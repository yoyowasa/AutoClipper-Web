"""Select readable sizes/positions and sparse, transcript-grounded line emphasis.

Fonts and colours come from the existing character/job style. Sizes and anchors
are resolved from confirmed text, not treated as human-approved preset values.
"""

import math
import re
import unicodedata

from app.candidates.merge_boundaries import ClipTextStyle, SubtitleStyleOverride
from app.overlay_text import fit_overlay_text
from app.render.subtitles_ass import resolve_clip_text_style, split_subtitle_lines


EMPHASIS_SIZE_SCALE = 1.12
EMPHASIS_MAX_FRACTION = .2
EMPHASIS_MIN_SPACING_SECONDS = 8
TOPIC_WORDS = re.compile(r"[一-龯々]{2,}|[ァ-ヶー]{2,}|[a-zA-Z0-9]{2,}")


def fitted_style(base, texts, layout, *, role, safe_top, safe_bottom, cap):
    """Use the renderer's width fitting and the same vertical bounding formula."""
    padding = base.outline_width + base.outer_outline_width + layout.shadow
    sizes = []
    for text, max_lines in texts:
        fit = fit_overlay_text(text, output_width=layout.width, font_name=base.font_name,
                               font_size=cap, margin_x=0, outline_width=base.outline_width + base.outer_outline_width,
                               shadow=layout.shadow, alignment=5, x_percent=base.x_percent, max_lines=max_lines)
        sizes.append(fit.effective_font_size)
    # Outlier lines still use the renderer's per-event fitting, without shrinking
    # every other subtitle to the size of the longest line in the clip.
    size = sorted(sizes)[max(0, math.ceil(len(sizes) * .1) - 1)] if sizes else cap
    max_lines = max((count for _, count in texts), default=2)
    size = min(size, int((safe_bottom - safe_top - 2 * padding) / (1.2 * max_lines)))
    size = max(12, min(220, size))
    half_height = max_lines * size * 1.2 / 2 + padding
    anchor = base.y_percent * layout.height / 100
    anchor = min(max(anchor, safe_top + half_height), safe_bottom - half_height)
    return ClipTextStyle(
        fontPreset=base.font_preset, fontName=base.font_name, bold=base.bold, fontSize=size,
        primaryColor=base.primary_color, outlineColor=base.outline_color, outlineWidth=base.outline_width,
        outerOutlineColor=base.outer_outline_color, outerOutlineWidth=base.outer_outline_width,
        xPercent=base.x_percent, yPercent=round(anchor / layout.height * 100, 4), positionMode="explicit",
    )


def choose_text_styles(clip, layout, *, events, top, bottom):
    manual = set(clip.manual_decision_fields)
    # Default layout sizes are only upper bounds; the actual text determines fit.
    defaults = type(layout).short() if clip.type == "short" else type(layout).normal(layout.width, layout.height)
    texts = {
        "title": [(clip.title, 2)], "hook": [(clip.hook_text, 2)],
        "subtitle": [(split_subtitle_lines(e.text, max_chars_per_line=layout.max_chars_per_line,
                                           max_lines=1 if e.single_line else min(2, layout.max_lines)),
                      1 if e.single_line else min(2, layout.max_lines)) for e in events],
    }
    for role in texts:
        if f"{role}_style" in manual:
            continue
        base = resolve_clip_text_style(getattr(layout, f"default_{role}_style"), layout, role=role)
        low, high = (top, bottom) if role == "subtitle" else (0, top or layout.height * .25)
        if role == "hook":
            high = top or layout.height * .25
        cap = defaults.font_size if role == "subtitle" else defaults.title_font_size
        setattr(clip, f"{role}_style", fitted_style(base, texts[role], layout, role=role,
                                                  safe_top=low + 12, safe_bottom=high - 12, cap=cap))


def choose_emphasis(clip, segments, layout, *, top, bottom):
    """Rank existing subtitle rows; never invent words or change subtitle text."""
    if "subtitle_styles" in clip.manual_decision_fields:
        return [], "explicit_manual_override_preserved"
    tokens = set(TOPIC_WORDS.findall(unicodedata.normalize("NFKC", f"{clip.title} {clip.hook_text}")))
    hook_scene = (clip.hook_scene_end - clip.hook_scene_start) if clip.hook_scene_start is not None else 0
    visible_start = clip.start + max(0, (clip.hook_duration_seconds if clip.hook_text else 0) - hook_scene)
    ranked = []
    for segment in segments:
        text = unicodedata.normalize("NFKC", segment.text)
        # Prefer a line that conveys the already-chosen subject; numbers and
        # questions are weaker signals. Long paragraphs are not emphasis lines.
        topic = any(token in text for token in tokens)
        number = bool(re.search(r"\d", text))
        reaction = bool(re.search(r"[!?]", text))
        score = 3 * topic + number + reaction
        visible_duration = min(segment.end, clip.end) - max(segment.start, visible_start)
        eligible = score > 0 and 2 <= len(text.strip()) <= 38 and visible_duration >= .5
        ranked.append((segment, score if eligible else 0, "selected_copy_topic" if topic else
                       "number_or_question" if number or reaction else "no_emphasis_signal"))
    selected = []
    limit = min(math.ceil(len(segments) * EMPHASIS_MAX_FRACTION), math.ceil(clip.duration / 20))
    for segment, score, _ in sorted(ranked, key=lambda item: (-item[1], item[0].start, item[0].id)):
        if len(selected) >= limit or score == 0:
            break
        if all(abs(segment.start - s.start) >= EMPHASIS_MIN_SPACING_SECONDS for s in selected):
            selected.append(segment)
    base = resolve_clip_text_style(clip.subtitle_style, layout, role="subtitle")
    styles = []
    for segment in sorted(selected, key=lambda s: s.start):
        max_lines = 1 if segment.single_line else min(2, layout.max_lines)
        text = split_subtitle_lines(segment.text, max_chars_per_line=layout.max_chars_per_line, max_lines=max_lines)
        style = fitted_style(base, [(text, max_lines)], layout, role="subtitle", safe_top=top + 12,
                             safe_bottom=bottom - 12, cap=round(base.font_size * EMPHASIS_SIZE_SCALE))
        # Keep character colours; white text gets the yellow
        # emphasis colour, with the preset outline left intact.
        if style.primary_color.upper() == "#FFFFFF":
            style.primary_color = "#FFFF00"
        styles.append(SubtitleStyleOverride(start=segment.start, end=segment.end, style=style))
    clip.subtitle_styles = styles
    return [(s, score, reason, s in selected) for s, score, reason in ranked], "rank_confirmed_subtitle_lines"
