"""Bounded geometric correction; never edits text, colour, font, outlines or line breaks."""
import math
from dataclasses import asdict, replace, is_dataclass

from app.candidates.merge_boundaries import ClipTextStyle, SubtitleStyleOverride
from app.overlay_geometry import OverlayLayoutNotice, measure_overlay
from app.production_choices import append_choice, choice_values, value_hash
from app.render.subtitles_ass import SubtitleLayout, resolve_clip_text_style, ResolvedTextStyle

POLICY = "overlay-layout-repair-v1"
MIN_FONT_SIZE = 12  # fitted_style and ClipTextStyle use the same lower bound.
MAX_REPAIR_PASSES = 3


def refresh_overlay_styles(clip):
    if not clip.preview_width or not clip.preview_height:
        return
    layout = SubtitleLayout.short() if clip.type == "short" else SubtitleLayout.normal(clip.preview_width, clip.preview_height)
    defaults = {f"default_{role}_style": ClipTextStyle.model_validate(value.model_dump())
                for role in ("title", "hook", "subtitle")
                if (value := getattr(clip, f"resolved_default_{role}_style")) is not None}
    layout = replace(layout, **defaults)
    for role in ("title", "hook", "subtitle"):
        previous = getattr(clip, f"resolved_{role}_style")
        if previous is not None:
            default = getattr(clip, f"resolved_default_{role}_style") or previous
            style = getattr(clip, f"{role}_style")
            if style is None:
                setattr(clip, f"resolved_{role}_style", default.model_copy(deep=True))
                continue
            resolved = resolve_clip_text_style(style, layout, role=role)
            if style.position_mode == "layout":
                resolved = replace(resolved, x_percent=default.x_percent, y_percent=default.y_percent,
                    alignment=default.alignment, margin_x=default.margin_x, margin_v=default.margin_v,
                    position_override=default.position_override)
            setattr(clip, f"resolved_{role}_style", type(previous).model_validate(asdict(resolved)))



def _correct(row, width, height):
    original = row["style"]
    if not is_dataclass(original):
        values = original.model_dump()
        original = ResolvedTextStyle(**values, style_alignment=values["alignment"])
    candidate = original
    for size in range(original.font_size, MIN_FONT_SIZE - 1, -1):
        candidate = replace(original, font_size=size)
        measured = measure_overlay(row, width=width, height=height, style=candidate)
        if measured["fits"]:
            return replace(candidate, font_size=measured["effectiveFontSize"]), 0.
    measured = measure_overlay(row, width=width, height=height, style=candidate)
    low, high = measured["verticalBounds"]
    if not measured["fitsWidth"] or high - low > row["safe_bottom"] - row["safe_top"]:
        return None, 0.
    shift = max(row["safe_top"] - low, 0.) + min(row["safe_bottom"] - high, 0.)
    # Explicit styles anchor at the centre, including when the original used ASS bottom alignment.
    anchor = (low + high) / 2 + shift
    anchor = math.floor(anchor) if shift < 0 else math.ceil(anchor)
    shift = anchor - (low + high) / 2
    moved = replace(candidate, y_percent=anchor / height * 100, position_mode="explicit",
                    alignment=5, margin_x=0, margin_v=0, position_override=True)
    if not 5 <= moved.y_percent <= 95 or not measure_overlay(row, width=width, height=height, style=moved)["fits"]:
        return None, 0.
    return moved, shift


def adjustment_input(document, clip, row):
    segment = next((s for s in document.segments if s.id in clip.segment_ids and (s.start, s.end) == (row.start, row.end)), None)
    return value_hash({"base": clip.resolved_subtitle_style.model_dump() if clip.resolved_subtitle_style else None,
                      "cue": row.style.model_dump(exclude_unset=True), "text": segment.text if segment else None,
                      "singleLine": segment.single_line if segment else False, "size": [clip.preview_width, clip.preview_height],
                      "banners": [document.short_top_banner_enabled, document.short_bottom_banner_enabled]})


def repair_overlay_layout(document, clip_ids=None):
    from app.jobs.quality_gate import overlay_layout_rows
    if document.state == "completed":
        return False
    changed = False
    for clip in document.clips:
        if clip_ids is not None and clip.id not in clip_ids:
            continue
        refresh_overlay_styles(clip)
        for row in clip.subtitle_styles:
            if row.layout_adjustment is not None and row.layout_adjustment_input != adjustment_input(document, clip, row):
                row.layout_adjustment = row.layout_adjustment_input = None
        notices = [item for item in clip.overlay_layout_notices if not item.failed]
        for _ in range(MAX_REPAIR_PASSES):
            repaired = False
            for row in overlay_layout_rows(document, clip):
                if row["style"] is None:
                    continue
                width, height = clip.preview_width, clip.preview_height
                measured = measure_overlay(row, width=width, height=height)
                if measured["fits"]:
                    continue
                fixed, shift = _correct(row, width, height)
                if fixed is None:
                    continue
                before = row["style"]
                if row["role"].startswith("subtitle:"):
                    hook = (clip.hook_scene_end - clip.hook_scene_start) if clip.hook_scene_start is not None else 0
                    low, high = clip.start + row["start"] - hook, clip.start + row["end"] - hook
                    for segment in document.segments:
                        if segment.id not in clip.segment_ids or segment.start >= high or segment.end <= low:
                            continue
                        current = next((s for s in clip.subtitle_styles if (s.start, s.end) == (segment.start, segment.end)), None)
                        patch = current.style if current else ClipTextStyle.model_validate({})
                        adjustment = {"font_size": fixed.font_size}
                        if shift:
                            adjustment.update(y_percent=fixed.y_percent, position_mode="explicit")
                        replacement = SubtitleStyleOverride(start=segment.start, end=segment.end, style=patch,
                            layoutAdjustment=ClipTextStyle.model_validate(adjustment))
                        replacement.layout_adjustment_input = adjustment_input(document, clip, replacement)
                        clip.subtitle_styles = [s for s in clip.subtitle_styles
                                                if (s.start, s.end) != (segment.start, segment.end)] + [replacement]

                else:
                    role = row["role"]
                    values = {key: value for key, value in (asdict(before) if is_dataclass(before) else before.model_dump()).items()
                              if key in ClipTextStyle.model_fields}
                    existing = getattr(clip, f"{role}_style")
                    if existing is not None:
                        values = existing.model_dump()
                    values["font_size"] = fixed.font_size
                    if shift:
                        values.update(y_percent=fixed.y_percent, position_mode="explicit")
                    setattr(clip, f"{role}_style", ClipTextStyle.model_validate(values))
                    refresh_overlay_styles(clip)
                notice = OverlayLayoutNotice(role=row["role"], start=row["start"], end=row["end"], text=row["text"],
                    boundary=measured["boundary"], overflowPx=measured["overflowPx"],
                    fontSizeBefore=before.font_size, fontSizeAfter=fixed.font_size, shiftPx=round(shift, 2))
                notices = [n for n in notices if (n.role, n.start, n.end) != (notice.role, notice.start, notice.end)] + [notice]
                append_choice(document.choice_history, kind="text_style", source="fallback", clipId=clip.id, stage="applied",
                    policyVersion=POLICY, timeBasis="clip", reason="overlay_layout_auto_repaired",
                    values=choice_values({"overlayRepair": {"role": row["role"], "start": row["start"], "end": row["end"],
                        "before": {"fontSize": before.font_size, "yPercent": before.y_percent},
                        "after": {"fontSize": fixed.font_size, "yPercent": fixed.y_percent}, "shiftPx": round(shift, 2)}}))
                repaired = changed = True
            if not repaired:
                break
        # Inspect again with exactly the gate geometry, not the proposed correction.
        for row in overlay_layout_rows(document, clip):
            if row["style"] is None:
                continue
            measured = measure_overlay(row, width=clip.preview_width, height=clip.preview_height)
            if not measured["fits"]:
                notices.append(OverlayLayoutNotice(role=row["role"], start=row["start"], end=row["end"], text=row["text"],
                    failed=True, boundary=measured["boundary"], overflowPx=measured["overflowPx"],
                    fontSizeBefore=row["style"].font_size, fontSizeAfter=row["style"].font_size, shiftPx=0))
        clip.overlay_layout_notices = notices
    return changed
