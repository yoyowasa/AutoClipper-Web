"""Per-cue patches inherit the current clip style; legacy full snapshots migrate in memory."""
from dataclasses import asdict
from app.candidates.merge_boundaries import ClipTextStyle


def manual_style(fields, name):
    return any(field == name or field.startswith(name + ".") for field in fields)


def inherit_cue_style(base, patch, layout, adjustment=None):
    from app.render.subtitles_ass import resolve_clip_text_style
    resolved = resolve_clip_text_style(base, layout, role="subtitle")
    values = {key: value for key, value in asdict(resolved).items() if key in ClipTextStyle.model_fields}
    changes = patch.model_dump(exclude_unset=True)
    if "font_preset" in changes and "font_name" not in changes:
        values.update(font_name=None, bold=None)
    if {"x_percent", "y_percent"}.intersection(changes) and "position_mode" not in changes:
        changes["position_mode"] = "explicit"
    values.update(changes)
    if adjustment is not None:
        values.update(adjustment.model_dump(exclude_unset=True))
    return ClipTextStyle.model_validate(values)


def normalize_legacy_cues(payload, changes=None):
    for clip in payload.get("clips", []):
        default = clip.get("resolvedDefaultSubtitleStyle") or {}
        migrated = False
        for row in clip.get("subtitleStyles", []):
            if "styleVersion" in row or not default:
                continue
            original = row.get("style", {})
            row["style"] = {key: value for key, value in original.items() if key not in default or value != default[key]}
            # Position mode describes the coordinates, not a separate human choice.
            if not {"xPercent", "yPercent"}.intersection(row["style"]):
                row["style"].pop("positionMode", None)
            if changes is not None and {"fontSize", "xPercent", "yPercent"}.intersection(set(original) - set(row["style"])):
                changes.append((clip["id"], row["start"], row["end"], dict(original)))
            row["styleVersion"] = 2
            migrated = True
        if migrated and "subtitle_styles" in clip.get("manualDecisionFields", []):
            fields = set(clip["manualDecisionFields"]) - {"subtitle_styles"}
            for row in clip.get("subtitleStyles", []):
                fields.update("subtitle_styles." + ClipTextStyle.model_fields[key].alias
                              for key in ClipTextStyle.model_fields if ClipTextStyle.model_fields[key].alias in row["style"])
            clip["manualDecisionFields"] = sorted(fields)
    return payload


def cue_manual_changes(before, after):
    old = {(s.start, s.end): s.style.model_dump(by_alias=True, exclude_unset=True) for s in before}
    fields = set()
    for row in after:
        patch = row.style.model_dump(by_alias=True, exclude_unset=True)
        previous = old.get((row.start, row.end), {})
        fields.update("subtitle_styles." + key for key in patch if previous.get(key) != patch[key])
    if len(after) < len(before):
        fields.add("subtitle_styles.removed")
    return fields


def cue_manual_rows(before, after):
    old = {(s.start, s.end): s.style.model_dump(by_alias=True, exclude_unset=True) for s in before}
    result = []
    for row in after:
        patch = row.style.model_dump(by_alias=True, exclude_unset=True)
        previous = old.get((row.start, row.end), {})
        changed = {key: value for key, value in patch.items() if key not in previous or previous[key] != value}
        if changed:
            result.append({"start": row.start, "end": row.end, "style": changed})
    return result


def record_cue_inheritance(document, changes):
    from app.jobs.overlay_layout_repair import refresh_overlay_styles, POLICY
    from app.overlay_geometry import OverlayLayoutNotice
    from app.production_choices import append_choice, choice_values
    from app.render.subtitles_ass import SubtitleLayout, resolve_clip_text_style
    for clip_id, start, end, original in changes:
        clip = next(c for c in document.clips if c.id == clip_id)
        refresh_overlay_styles(clip)
        row = next(s for s in clip.subtitle_styles if (s.start, s.end) == (start, end))
        layout = (SubtitleLayout.short() if clip.type == "short" else
                  SubtitleLayout.normal(clip.preview_width or 1920, clip.preview_height or 1080))
        resolved = resolve_clip_text_style(inherit_cue_style(clip.subtitle_style, row.style, layout), layout, role="subtitle")
        old_size, old_y = original.get("fontSize", resolved.font_size), original.get("yPercent", resolved.y_percent)
        shift = (resolved.y_percent - old_y) * (clip.preview_height or layout.height) / 100
        if old_size == resolved.font_size and abs(shift) < .01:
            continue
        hook = clip.hook_scene_end - clip.hook_scene_start if clip.hook_scene_start is not None else 0
        relative_start, relative_end = max(0., start - clip.start + hook), min(clip.duration + hook, end - clip.start + hook)
        segment = next((s for s in document.segments if s.id in clip.segment_ids and (s.start, s.end) == (start, end)), None)
        clip.overlay_layout_notices.append(OverlayLayoutNotice(role="subtitle:inherited", start=relative_start, end=relative_end,
            text=segment.text if segment else "字幕", boundary="clip書式から継承", overflowPx=0,
            fontSizeBefore=old_size, fontSizeAfter=resolved.font_size, shiftPx=round(shift, 2)))
        append_choice(document.choice_history, kind="text_style", source="fallback", clipId=clip.id, stage="applied",
            policyVersion=POLICY, timeBasis="clip", reason="legacy_cue_style_inherited",
            values=choice_values({"overlayRepair": {"role": "subtitle:inherited", "start": relative_start, "end": relative_end,
                "before": {"fontSize": old_size, "yPercent": old_y},
                "after": {"fontSize": resolved.font_size, "yPercent": resolved.y_percent}, "shiftPx": round(shift, 2)}}))


def cue_style_values(rows):
    return [row.model_dump(mode="json", by_alias=True) for row in rows]
