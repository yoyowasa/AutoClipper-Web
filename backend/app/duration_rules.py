import math
from typing import Any

NORMAL_MIN_SECONDS = 90.0
NORMAL_MAX_SECONDS = 600.0
NORMAL_LONGFORM_MAX_SECONDS = 1800.0
SHORT_MAX_DEFAULT_SECONDS = 75.0
SHORT_MAX_CEILING_SECONDS = 180.0


def validate_clip_duration(clip_type: str, duration: float, *, short_max: float) -> str | None:
    if not math.isfinite(duration) or duration <= 0:
        return "切り抜きの終了は開始より後にしてください。"
    if clip_type == "normal" and duration < NORMAL_MIN_SECONDS:
        return "通常切り抜きは90秒以上です。"
    if clip_type == "normal" and duration > NORMAL_LONGFORM_MAX_SECONDS:
        return "通常切り抜きは最長30分です。"
    if clip_type == "short" and duration > short_max:
        return f"ショートは{short_max:g}秒以内です（設定の上限）。"
    return None


def selection_duration_rejection(
    clip_type: str, duration: float, *, short_max: float, longform_reason: str = "", manual: bool = False,
) -> str | None:
    """Search settings are hints; automatic long clips require a content reason."""
    if validate_clip_duration(clip_type, duration, short_max=short_max):
        return "duration_out_of_range"
    if clip_type == "normal" and duration > NORMAL_MAX_SECONDS and not manual and not longform_reason.strip():
        return "longform_without_reason"
    return None


def effective_short_max(settings: dict[str, Any]) -> float:
    return _bounded_setting(settings, "shortMaxDuration", SHORT_MAX_DEFAULT_SECONDS, 1.0, SHORT_MAX_CEILING_SECONDS)


def _bounded_setting(settings: dict[str, Any], key: str, default: float, lower: float, upper: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return max(lower, min(upper, value))


def duration_search_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Bound legacy search settings without rewriting the persisted job."""
    minimum = _bounded_setting(settings, "normalMinDuration", NORMAL_MIN_SECONDS, NORMAL_MIN_SECONDS, NORMAL_MAX_SECONDS)
    maximum = _bounded_setting(settings, "normalMaxDuration", NORMAL_MAX_SECONDS, NORMAL_MIN_SECONDS, NORMAL_MAX_SECONDS)
    short_max = effective_short_max(settings)
    return {
        **settings,
        "normalMinDuration": minimum,
        "normalMaxDuration": max(minimum, maximum),
        "shortMinDuration": _bounded_setting(settings, "shortMinDuration", 20.0, 0.0, short_max),
        "shortMaxDuration": short_max,
    }


def completed_clip_duration(clip_type: str, start: float, end: float, hook_start: float | None, hook_end: float | None) -> float:
    hook = hook_end - hook_start if clip_type == "short" and hook_start is not None and hook_end is not None else 0.0
    return end - start + hook
