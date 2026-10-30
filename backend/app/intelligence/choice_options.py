"""Comparable recorded options; unique wording/ranges remain per-video evidence."""

OPTION_KEYS = {
    "publication_decision": ("publicationDecision",),
    "range": ("type", "audienceFamiliarity", "openingRankWeight", "allocationNormalWeight", "allocationShortWeight", "allocationShare"),
    "title_hook": ("intent",),
    "thumbnail": ("source", "cropMode", "templateVersion", "emotion"),
    "framing": ("shortLayout", "resolvedLayout"),
    "effects": ("additionalEffects", "emphasisTopicWeight", "emphasisNumberWeight", "emphasisReactionWeight", "emphasisSignal"),
    "post_copy": ("postMetadataSource",),
    "publication": ("postMetadataSource",),
}


def choice_options(kind, role, values):
    if kind == "text_style":
        style = values.get(role, {})
        return {key: style[key] for key in ("fontPreset", "fontSize", "bold") if key in style} if isinstance(style, dict) else {}
    options = {key: values[key] for key in OPTION_KEYS.get(kind, ()) if key in values}
    if kind == "range" and values.get("openingScore") is not None:
        score = values["openingScore"]
        options["openingBand"] = "0-5" if score < 5 else "5-10" if score < 10 else "10-15" if score <= 15 else "unknown"
    return options


def bounded_values(values):
    import json
    omitted = len(json.dumps(values, ensure_ascii=False)) > 2000
    return {"values": None if omitted else values, "values_omitted": omitted}
