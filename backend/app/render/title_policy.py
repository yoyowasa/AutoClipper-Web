from __future__ import annotations


SHORT_OVERLAY_TITLE_MODES = {"auto", "always", "high_quality_only", "never"}


def normalize_short_overlay_title_mode(value: str | None) -> str:
    mode = (value or "auto").strip()
    return mode if mode in SHORT_OVERLAY_TITLE_MODES else "auto"


def short_overlay_title_expected(
    *,
    render_mode: str | None,
    stored_mode: str | None,
    top_banner_enabled: bool,
    title_manually_reviewed: bool,
) -> bool:
    if top_banner_enabled:
        return True
    overlay_mode = normalize_short_overlay_title_mode(stored_mode)
    if overlay_mode == "always":
        return True
    if overlay_mode == "never":
        return False
    if (render_mode or "high_quality").strip() == "high_quality":
        return True
    return overlay_mode == "auto" and title_manually_reviewed
