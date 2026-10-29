"""Comparable recorded options; unique wording/ranges remain per-video evidence."""

OPTION_KEYS = {
    "range": ("type",),
    "title_hook": ("intent",),
    "thumbnail": ("source", "cropMode", "templateVersion", "emotion"),
    "framing": ("shortLayout", "resolvedLayout"),
    "effects": ("additionalEffects",),
    "post_copy": ("postMetadataSource",),
    "publication": ("postMetadataSource",),
}


def choice_options(kind, role, values):
    if kind == "text_style":
        style = values.get(role, {})
        return {key: style[key] for key in ("fontPreset", "fontSize", "bold") if key in style} if isinstance(style, dict) else {}
    return {key: values[key] for key in OPTION_KEYS.get(kind, ()) if key in values}


def bounded_values(values):
    import json
    omitted = len(json.dumps(values, ensure_ascii=False)) > 2000
    return {"values": None if omitted else values, "values_omitted": omitted}
