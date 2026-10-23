"""Record the existing renderer's decisions, without selecting a new visual style."""

import json
from dataclasses import asdict
from pathlib import Path

from app.production_choice_capture import best_effort_capture
from app.production_choices import append_choice, dump_history, merge_history, value_hash
from app.storage.json_io import write_json_atomic


RENDER_DECISION_POLICY = "existing-render-decisions-v1"


def _camel_case(name):
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


@best_effort_capture
def capture_text_fit(records, *, role, style, fit, source):
    """Aggregate identical effective styles. Never retain subtitle text or paths."""
    if records is None:
        return
    values = {
        "role": role, "source": source,
        **{_camel_case(key): value for key, value in asdict(style).items() if key != "style_alignment"},
        "effectiveFontSize": fit.effective_font_size,
        "maxWidthPx": fit.max_width_px, "fits": fit.fits, "overflowReason": fit.overflow_reason,
        "lineCount": len(fit.lines),
    }
    for record in records:
        if {key: value for key, value in record.items() if key != "eventCount"} == values:
            record["eventCount"] += 1
            return
    records.append({**values, "eventCount": 1})


def text_style_source(candidate, layout, role, *, segment_override=False):
    if segment_override:
        return "segment_override"
    if getattr(candidate, f"{role}_style") is not None:
        return "clip_override"
    if getattr(layout, f"default_{role}_style") is not None:
        return "job_settings"
    return "layout_settings"


@best_effort_capture
def record_render_decisions(metadata_path, *, candidate, job, text_fits, requested_layout, subtitle_path,
                            canvas_size, content_viewport=None):
    """Attach published values to the existing export, then its permanent record.

    A character name alone does not prove that a setting still matches a preset.
    Keep the actual setting layer, rather than inventing preset/manual provenance.
    """
    payload = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    history = merge_history(payload.get("choiceHistory", []))
    revision = value_hash({"start": candidate.start, "end": candidate.end,
                           "canvas": canvas_size, "viewport": content_viewport,
                           "ass": Path(subtitle_path).read_text(encoding="utf-8") if subtitle_path else None,
                           "framing": [requested_layout, candidate.framing_offset_x,
                                       candidate.framing_offset_y, candidate.framing_zoom]})
    common = dict(clipId=candidate.id, stage="published", inputRevision=revision, policyVersion=RENDER_DECISION_POLICY)
    strategy = payload.get("crop_strategy") if candidate.type == "short" else "source"
    fallback = payload.get("crop_fallback_reason")
    source = ("default" if candidate.type == "normal" else
              "fallback" if fallback else "automatic" if requested_layout == "auto" else "unrecorded")
    output_size = {"width": canvas_size[0], "height": canvas_size[1]}
    content_height, content_y = content_viewport or (canvas_size[1], 0)
    framing = {
        "shortLayout": requested_layout if candidate.type == "short" else None,
        "resolvedLayout": strategy,
        "settingSource": ("source_video" if candidate.type == "normal" else
                          "clip_override" if candidate.short_layout is not None else
                          "job_settings" if "shortLayout" in (job.settings_json or {}) else "layout_default"),
        "framingOffsetX": candidate.framing_offset_x if candidate.type == "short" else 0,
        "framingOffsetY": candidate.framing_offset_y if candidate.type == "short" else 0,
        "framingZoom": candidate.framing_zoom if candidate.type == "short" else 1,
        "cropX": payload.get("crop_x"), "cropY": payload.get("crop_y"),
        "cropSignalSource": payload.get("crop_signal_source"),
        "cropFallbackReason": fallback, "cropAttemptedStrategies": payload.get("crop_attempted_strategies", []),
        "outputSize": output_size, "contentViewport": {"width": canvas_size[0], "height": content_height, "y": content_y},
    }
    append_choice(history, kind="framing", source=source, reason=fallback or "existing_render_layout", values=framing, **common)
    append_choice(history, kind="text_style", source="automatic", reason="existing_text_fit_preserving_overrides",
                  values={"outputSize": output_size, "renderedTextStyles": text_fits}, **common)
    append_choice(history, kind="effects", source="default", reason="additional_effects_disabled_by_policy",
                  values={"additionalEffects": "none"}, **common)
    payload["choiceHistory"] = dump_history(history)
    write_json_atomic(Path(metadata_path), payload)
