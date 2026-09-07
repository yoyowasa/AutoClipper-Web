import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Sequence

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle, TextFontPreset
from app.candidates.select_candidates import CandidateSelection
from app.overlay_text import (
    balanced_overlay_lines,
    fit_overlay_text,
    normalize_overlay_text,
    overlay_text_width_units,
)


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
DEFAULT_NORMAL_WIDTH = 1920
DEFAULT_NORMAL_HEIGHT = 1080
DEFAULT_SHORT_MAX_CHARS_PER_LINE = 16
DEFAULT_NORMAL_MAX_CHARS_PER_LINE = 28
DEFAULT_SUBTITLE_MAX_LINES = 2
DEFAULT_MIN_SUBTITLE_DURATION = 1.1
DEFAULT_MAX_SUBTITLE_DURATION = 4.2
DEFAULT_MIN_GAP_BETWEEN_SUBTITLES = 0.08
DEFAULT_ASS_FONT = "Noto Sans CJK JP"
DEFAULT_ASS_TITLE_FONT = "Noto Sans JP Black"
DEFAULT_SHORT_SUBTITLE_FONT_SIZE = 76
DEFAULT_SHORT_TITLE_FONT_SIZE = 88
DEFAULT_SHORT_SUBTITLE_OUTLINE = 5
DEFAULT_SHORT_SUBTITLE_SHADOW = 2
DEFAULT_SHORT_MARGIN_X = 86
DEFAULT_SHORT_LOWER_MARGIN = 250
DEFAULT_SHORT_TOP_MARGIN = 150
DEFAULT_SHORT_TITLE_X_PERCENT = 50.0
DEFAULT_SHORT_TITLE_Y_PERCENT = 12.5
DEFAULT_SHORT_HOOK_X_PERCENT = 50.0
DEFAULT_SHORT_HOOK_Y_PERCENT = 18.75
DEFAULT_SUBTITLE_ALIGNMENT = 2
DEFAULT_TITLE_ALIGNMENT = 8
DEFAULT_SUBTITLE_PRIMARY_COLOR = "#FFFFFF"
DEFAULT_SUBTITLE_OUTLINE_COLOR = "#000000"
TEXT_FONT_PRESETS: dict[TextFontPreset, tuple[str, bool]] = {
    "chikara_yowaku": ("851CHIKARA-YOWAKU", False),
    "keifont": ("Keifont", False),
    "mushin": ("Mushin", False),
    "ankoku_zonji": ("AnkokuZombic", False),
    "killgo_nb": ("GN-KMBFont-UB-NewstyleKanaB", False),
    "tanuki_magic": ("Tanuki Permanent Marker", False),
    "sans": ("Noto Sans CJK JP", False),
    "sans_bold": ("Noto Sans CJK JP", True),
    "noto_black": ("Noto Sans JP Black", False),
    "heavy": ("Source Han Sans JP Heavy", True),
    "mplus_extrabold": ("M PLUS 1 ExtraBold", False),
    "mplus_rounded_extrabold": ("Rounded Mplus 1c ExtraBold", False),
    "chikara": ("851CHIKARA-DZUYOKU-KANA-A", False),
    "dela_gothic": ("Dela Gothic One", False),
    "corporate_logo": ("Corporate-Logo-Bold-ver3", True),
    "serif": ("Noto Serif CJK JP", False),
    "mono": ("Noto Sans Mono CJK JP", True),
}
PUNCTUATION_BREAKS = "。、！？!?"
PHRASE_BREAKS = "、，, "
SOFT_JA_BOUNDARIES = "でにはをがともやへ"


@dataclass(frozen=True)
class SubtitleRenderSettings:
    max_chars_per_line_short: int = DEFAULT_SHORT_MAX_CHARS_PER_LINE
    max_chars_per_line_normal: int = DEFAULT_NORMAL_MAX_CHARS_PER_LINE
    max_lines: int = DEFAULT_SUBTITLE_MAX_LINES
    min_subtitle_duration: float = DEFAULT_MIN_SUBTITLE_DURATION
    max_subtitle_duration: float = DEFAULT_MAX_SUBTITLE_DURATION
    min_gap_between_subtitles: float = DEFAULT_MIN_GAP_BETWEEN_SUBTITLES
    subtitle_font_name: str = DEFAULT_ASS_FONT
    title_font_name: str = DEFAULT_ASS_TITLE_FONT
    subtitle_primary_color: str = DEFAULT_SUBTITLE_PRIMARY_COLOR
    subtitle_outline_color: str = DEFAULT_SUBTITLE_OUTLINE_COLOR
    short_font_name: str | None = None
    short_font_size: int | None = None
    short_title_font_size: int | None = None
    short_outline: int | None = None
    short_shadow: int | None = None
    short_margin_x: int | None = None
    short_lower_margin: int | None = None
    short_top_margin: int | None = None
    short_subtitle_alignment: int | None = None
    short_title_alignment: int | None = None
    short_subtitle_x_percent: float | None = None
    short_subtitle_y_percent: float | None = None
    short_primary_color: str | None = None
    short_outline_color: str | None = None
    normal_font_name: str | None = None
    normal_font_size: int | None = None
    normal_title_font_size: int | None = None
    normal_outline: int | None = None
    normal_shadow: int | None = None
    normal_margin_x: int | None = None
    normal_lower_margin: int | None = None
    normal_top_margin: int | None = None
    normal_subtitle_alignment: int | None = None
    normal_title_alignment: int | None = None
    normal_subtitle_x_percent: float | None = None
    normal_subtitle_y_percent: float | None = None
    normal_primary_color: str | None = None
    normal_outline_color: str | None = None


@dataclass(frozen=True)
class SubtitleEvent:
    start: float
    end: float
    text: str
    style: ClipTextStyle | None = None


@dataclass(frozen=True)
class SubtitleLayout:
    width: int
    height: int
    font_name: str
    title_font_name: str
    font_size: int
    title_font_size: int
    outline: int
    shadow: int
    margin_x: int
    lower_margin: int
    top_margin: int
    subtitle_alignment: int
    title_alignment: int
    primary_color: str
    outline_color: str
    max_chars_per_line: int
    max_lines: int
    min_subtitle_duration: float
    max_subtitle_duration: float
    min_gap_between_subtitles: float
    subtitle_x_percent: float | None = None
    subtitle_y_percent: float | None = None

    @classmethod
    def short(cls, settings: SubtitleRenderSettings | dict[str, Any] | None = None) -> "SubtitleLayout":
        parsed_settings = parse_subtitle_settings(settings)
        return cls(
            width=SHORT_WIDTH,
            height=SHORT_HEIGHT,
            font_name=parsed_settings.short_font_name or parsed_settings.subtitle_font_name,
            title_font_name=parsed_settings.title_font_name,
            font_size=parsed_settings.short_font_size or DEFAULT_SHORT_SUBTITLE_FONT_SIZE,
            title_font_size=parsed_settings.short_title_font_size or DEFAULT_SHORT_TITLE_FONT_SIZE,
            outline=parsed_settings.short_outline if parsed_settings.short_outline is not None else DEFAULT_SHORT_SUBTITLE_OUTLINE,
            shadow=parsed_settings.short_shadow if parsed_settings.short_shadow is not None else DEFAULT_SHORT_SUBTITLE_SHADOW,
            margin_x=(
                parsed_settings.short_margin_x
                if parsed_settings.short_margin_x is not None
                else DEFAULT_SHORT_MARGIN_X
            ),
            lower_margin=(
                parsed_settings.short_lower_margin
                if parsed_settings.short_lower_margin is not None
                else DEFAULT_SHORT_LOWER_MARGIN
            ),
            top_margin=(
                parsed_settings.short_top_margin
                if parsed_settings.short_top_margin is not None
                else DEFAULT_SHORT_TOP_MARGIN
            ),
            subtitle_alignment=parsed_settings.short_subtitle_alignment or DEFAULT_SUBTITLE_ALIGNMENT,
            title_alignment=parsed_settings.short_title_alignment or DEFAULT_TITLE_ALIGNMENT,
            subtitle_x_percent=parsed_settings.short_subtitle_x_percent,
            subtitle_y_percent=parsed_settings.short_subtitle_y_percent,
            primary_color=parsed_settings.short_primary_color or parsed_settings.subtitle_primary_color,
            outline_color=parsed_settings.short_outline_color or parsed_settings.subtitle_outline_color,
            max_chars_per_line=parsed_settings.max_chars_per_line_short,
            max_lines=parsed_settings.max_lines,
            min_subtitle_duration=parsed_settings.min_subtitle_duration,
            max_subtitle_duration=parsed_settings.max_subtitle_duration,
            min_gap_between_subtitles=parsed_settings.min_gap_between_subtitles,
        )

    @classmethod
    def normal(
        cls,
        width: int = DEFAULT_NORMAL_WIDTH,
        height: int = DEFAULT_NORMAL_HEIGHT,
        settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    ) -> "SubtitleLayout":
        parsed_settings = parse_subtitle_settings(settings)
        safe_width = max(320, int(width))
        safe_height = max(240, int(height))
        font_size = parsed_settings.normal_font_size or max(42, min(72, round(safe_height * 0.06)))
        return cls(
            width=safe_width,
            height=safe_height,
            font_name=parsed_settings.normal_font_name or parsed_settings.subtitle_font_name,
            title_font_name=parsed_settings.title_font_name,
            font_size=font_size,
            title_font_size=parsed_settings.normal_title_font_size or max(font_size + 6, round(safe_height * 0.07)),
            outline=parsed_settings.normal_outline if parsed_settings.normal_outline is not None else max(3, round(safe_height * 0.004)),
            shadow=parsed_settings.normal_shadow if parsed_settings.normal_shadow is not None else max(1, round(safe_height * 0.002)),
            margin_x=(
                parsed_settings.normal_margin_x
                if parsed_settings.normal_margin_x is not None
                else round(safe_width * 0.08)
            ),
            lower_margin=(
                parsed_settings.normal_lower_margin
                if parsed_settings.normal_lower_margin is not None
                else round(safe_height * 0.08)
            ),
            top_margin=(
                parsed_settings.normal_top_margin
                if parsed_settings.normal_top_margin is not None
                else round(safe_height * 0.08)
            ),
            subtitle_alignment=parsed_settings.normal_subtitle_alignment or DEFAULT_SUBTITLE_ALIGNMENT,
            title_alignment=parsed_settings.normal_title_alignment or DEFAULT_TITLE_ALIGNMENT,
            subtitle_x_percent=parsed_settings.normal_subtitle_x_percent,
            subtitle_y_percent=parsed_settings.normal_subtitle_y_percent,
            primary_color=parsed_settings.normal_primary_color or parsed_settings.subtitle_primary_color,
            outline_color=parsed_settings.normal_outline_color or parsed_settings.subtitle_outline_color,
            max_chars_per_line=parsed_settings.max_chars_per_line_normal,
            max_lines=parsed_settings.max_lines,
            min_subtitle_duration=parsed_settings.min_subtitle_duration,
            max_subtitle_duration=parsed_settings.max_subtitle_duration,
            min_gap_between_subtitles=parsed_settings.min_gap_between_subtitles,
        )


TextStyleRole = Literal["subtitle", "title", "hook"]
TextStylePositionMode = Literal["explicit", "layout"]


@dataclass(frozen=True)
class ResolvedTextStyle:
    font_preset: TextFontPreset | None
    font_name: str
    font_size: int
    primary_color: str
    outline_color: str
    outline_width: int
    shadow: int
    bold: bool
    alignment: int
    style_alignment: int
    margin_x: int
    margin_v: int
    x_percent: float
    y_percent: float
    position_mode: TextStylePositionMode
    position_override: bool
    outer_outline_color: str = "#FFFFFF"
    outer_outline_width: int = 0


def _coerce_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if math.isnan(parsed) or math.isinf(parsed):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_optional_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, parsed))


def _coerce_optional_float(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return max(minimum, min(maximum, parsed))


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    parsed = str(value).strip()
    return parsed or default


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _coerce_hex_color(value: Any, default: str) -> str:
    parsed = _coerce_optional_str(value)
    if parsed is None:
        return default
    normalized = parsed.upper()
    if len(normalized) != 7 or not normalized.startswith("#"):
        return default
    try:
        int(normalized[1:], 16)
    except ValueError:
        return default
    return normalized


def _coerce_optional_hex_color(value: Any) -> str | None:
    parsed = _coerce_optional_str(value)
    if parsed is None:
        return None
    normalized = parsed.upper()
    if len(normalized) != 7 or not normalized.startswith("#"):
        return None
    try:
        int(normalized[1:], 16)
    except ValueError:
        return None
    return normalized


def _first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def parse_subtitle_settings(settings: SubtitleRenderSettings | dict[str, Any] | None) -> SubtitleRenderSettings:
    if settings is None:
        return SubtitleRenderSettings()
    if isinstance(settings, SubtitleRenderSettings):
        return settings

    aliases = {
        "maxCharsPerLineShort": "max_chars_per_line_short",
        "maxCharsPerLineNormal": "max_chars_per_line_normal",
        "maxLines": "max_lines",
        "minSubtitleDuration": "min_subtitle_duration",
        "maxSubtitleDuration": "max_subtitle_duration",
        "minGapBetweenSubtitles": "min_gap_between_subtitles",
        "subtitleFontName": "subtitle_font_name",
        "titleFontName": "title_font_name",
        "subtitleTitleFontName": "title_font_name",
        "subtitleFontSize": "subtitle_font_size",
        "titleFontSize": "title_font_size",
        "subtitleTitleFontSize": "title_font_size",
        "subtitleOutline": "subtitle_outline",
        "subtitleShadow": "subtitle_shadow",
        "subtitleMarginX": "subtitle_margin_x",
        "subtitleLowerMargin": "subtitle_lower_margin",
        "subtitleTopMargin": "subtitle_top_margin",
        "subtitleAlignment": "subtitle_alignment",
        "titleAlignment": "title_alignment",
        "subtitleTitleAlignment": "title_alignment",
        "subtitlePrimaryColor": "subtitle_primary_color",
        "subtitleOutlineColor": "subtitle_outline_color",
        "shortSubtitleFontName": "short_font_name",
        "shortSubtitleFontSize": "short_font_size",
        "shortTitleFontSize": "short_title_font_size",
        "shortSubtitleOutline": "short_outline",
        "shortSubtitleShadow": "short_shadow",
        "shortSubtitleMarginX": "short_margin_x",
        "shortSubtitleLowerMargin": "short_lower_margin",
        "shortTitleTopMargin": "short_top_margin",
        "shortSubtitleAlignment": "short_subtitle_alignment",
        "shortTitleAlignment": "short_title_alignment",
        "shortSubtitleXPercent": "short_subtitle_x_percent",
        "shortSubtitleYPercent": "short_subtitle_y_percent",
        "shortSubtitlePrimaryColor": "short_primary_color",
        "shortSubtitleOutlineColor": "short_outline_color",
        "normalSubtitleFontName": "normal_font_name",
        "normalSubtitleFontSize": "normal_font_size",
        "normalTitleFontSize": "normal_title_font_size",
        "normalSubtitleOutline": "normal_outline",
        "normalSubtitleShadow": "normal_shadow",
        "normalSubtitleMarginX": "normal_margin_x",
        "normalSubtitleLowerMargin": "normal_lower_margin",
        "normalTitleTopMargin": "normal_top_margin",
        "normalSubtitleAlignment": "normal_subtitle_alignment",
        "normalTitleAlignment": "normal_title_alignment",
        "normalSubtitleXPercent": "normal_subtitle_x_percent",
        "normalSubtitleYPercent": "normal_subtitle_y_percent",
        "normalSubtitlePrimaryColor": "normal_primary_color",
        "normalSubtitleOutlineColor": "normal_outline_color",
    }
    normalized = {aliases.get(key, key): value for key, value in settings.items()}
    min_duration = _coerce_float(
        normalized.get("min_subtitle_duration"),
        DEFAULT_MIN_SUBTITLE_DURATION,
        minimum=0.2,
        maximum=10.0,
    )
    max_duration = _coerce_float(
        normalized.get("max_subtitle_duration"),
        DEFAULT_MAX_SUBTITLE_DURATION,
        minimum=min_duration,
        maximum=20.0,
    )
    return SubtitleRenderSettings(
        max_chars_per_line_short=_coerce_int(
            normalized.get("max_chars_per_line_short"),
            DEFAULT_SHORT_MAX_CHARS_PER_LINE,
            minimum=6,
            maximum=80,
        ),
        max_chars_per_line_normal=_coerce_int(
            normalized.get("max_chars_per_line_normal"),
            DEFAULT_NORMAL_MAX_CHARS_PER_LINE,
            minimum=8,
            maximum=100,
        ),
        max_lines=_coerce_int(
            normalized.get("max_lines"),
            DEFAULT_SUBTITLE_MAX_LINES,
            minimum=1,
            maximum=2,
        ),
        min_subtitle_duration=min_duration,
        max_subtitle_duration=max_duration,
        min_gap_between_subtitles=_coerce_float(
            normalized.get("min_gap_between_subtitles"),
            DEFAULT_MIN_GAP_BETWEEN_SUBTITLES,
            minimum=0.0,
            maximum=2.0,
        ),
        subtitle_font_name=_coerce_str(normalized.get("subtitle_font_name"), DEFAULT_ASS_FONT),
        title_font_name=_coerce_str(
            normalized.get("title_font_name"),
            DEFAULT_ASS_TITLE_FONT,
        ),
        subtitle_primary_color=_coerce_hex_color(
            normalized.get("subtitle_primary_color"),
            DEFAULT_SUBTITLE_PRIMARY_COLOR,
        ),
        subtitle_outline_color=_coerce_hex_color(
            normalized.get("subtitle_outline_color"),
            DEFAULT_SUBTITLE_OUTLINE_COLOR,
        ),
        short_font_name=_coerce_optional_str(normalized.get("short_font_name")),
        short_font_size=_coerce_optional_int(
            _first_value(normalized, "short_font_size", "subtitle_font_size"),
            minimum=20,
            maximum=220,
        ),
        short_title_font_size=_coerce_optional_int(
            _first_value(normalized, "short_title_font_size", "title_font_size"),
            minimum=20,
            maximum=220,
        ),
        short_outline=_coerce_optional_int(
            _first_value(normalized, "short_outline", "subtitle_outline"),
            minimum=0,
            maximum=20,
        ),
        short_shadow=_coerce_optional_int(
            _first_value(normalized, "short_shadow", "subtitle_shadow"),
            minimum=0,
            maximum=20,
        ),
        short_margin_x=_coerce_optional_int(
            _first_value(normalized, "short_margin_x", "subtitle_margin_x"),
            minimum=0,
            maximum=800,
        ),
        short_lower_margin=_coerce_optional_int(
            _first_value(normalized, "short_lower_margin", "subtitle_lower_margin"),
            minimum=0,
            maximum=1600,
        ),
        short_top_margin=_coerce_optional_int(
            _first_value(normalized, "short_top_margin", "subtitle_top_margin"),
            minimum=0,
            maximum=1600,
        ),
        short_subtitle_alignment=_coerce_optional_int(
            _first_value(normalized, "short_subtitle_alignment", "subtitle_alignment"),
            minimum=1,
            maximum=9,
        ),
        short_title_alignment=_coerce_optional_int(
            _first_value(normalized, "short_title_alignment", "title_alignment"),
            minimum=1,
            maximum=9,
        ),
        short_subtitle_x_percent=_coerce_optional_float(
            normalized.get("short_subtitle_x_percent"),
            minimum=5,
            maximum=95,
        ),
        short_subtitle_y_percent=_coerce_optional_float(
            normalized.get("short_subtitle_y_percent"),
            minimum=5,
            maximum=95,
        ),
        short_primary_color=_coerce_optional_hex_color(normalized.get("short_primary_color")),
        short_outline_color=_coerce_optional_hex_color(normalized.get("short_outline_color")),
        normal_font_name=_coerce_optional_str(normalized.get("normal_font_name")),
        normal_font_size=_coerce_optional_int(
            _first_value(normalized, "normal_font_size", "subtitle_font_size"),
            minimum=12,
            maximum=180,
        ),
        normal_title_font_size=_coerce_optional_int(
            _first_value(normalized, "normal_title_font_size", "title_font_size"),
            minimum=12,
            maximum=180,
        ),
        normal_outline=_coerce_optional_int(
            _first_value(normalized, "normal_outline", "subtitle_outline"),
            minimum=0,
            maximum=20,
        ),
        normal_shadow=_coerce_optional_int(
            _first_value(normalized, "normal_shadow", "subtitle_shadow"),
            minimum=0,
            maximum=20,
        ),
        normal_margin_x=_coerce_optional_int(
            _first_value(normalized, "normal_margin_x", "subtitle_margin_x"),
            minimum=0,
            maximum=1200,
        ),
        normal_lower_margin=_coerce_optional_int(
            _first_value(normalized, "normal_lower_margin", "subtitle_lower_margin"),
            minimum=0,
            maximum=900,
        ),
        normal_top_margin=_coerce_optional_int(
            _first_value(normalized, "normal_top_margin", "subtitle_top_margin"),
            minimum=0,
            maximum=900,
        ),
        normal_subtitle_alignment=_coerce_optional_int(
            _first_value(normalized, "normal_subtitle_alignment", "subtitle_alignment"),
            minimum=1,
            maximum=9,
        ),
        normal_title_alignment=_coerce_optional_int(
            _first_value(normalized, "normal_title_alignment", "title_alignment"),
            minimum=1,
            maximum=9,
        ),
        normal_subtitle_x_percent=_coerce_optional_float(
            normalized.get("normal_subtitle_x_percent"),
            minimum=5,
            maximum=95,
        ),
        normal_subtitle_y_percent=_coerce_optional_float(
            normalized.get("normal_subtitle_y_percent"),
            minimum=5,
            maximum=95,
        ),
        normal_primary_color=_coerce_optional_hex_color(normalized.get("normal_primary_color")),
        normal_outline_color=_coerce_optional_hex_color(normalized.get("normal_outline_color")),
    )


def format_ass_timestamp(seconds: float) -> str:
    total_centiseconds = int(max(0.0, seconds) * 100 + 0.5)
    hours = total_centiseconds // 360000
    total_centiseconds %= 360000
    minutes = total_centiseconds // 6000
    total_centiseconds %= 6000
    secs = total_centiseconds // 100
    centiseconds = total_centiseconds % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _best_break_index(text: str, limit: int, *, minimum: int | None = None) -> int:
    if len(text) <= limit:
        return len(text)

    minimum = minimum if minimum is not None else max(3, int(limit * 0.45))
    search_end = min(limit, len(text) - 1)
    for break_chars in (PUNCTUATION_BREAKS, PHRASE_BREAKS, SOFT_JA_BOUNDARIES):
        for index in range(search_end, minimum - 1, -1):
            if text[index] in break_chars:
                return index + 1

    if " " in text:
        for index in range(search_end, minimum - 1, -1):
            if text[index] == " ":
                return index + 1
    return limit


def split_subtitle_text(text: str, max_chars_per_event: int) -> list[str]:
    clean_text = _normalize_text(text)
    if not clean_text:
        return []

    chunks: list[str] = []
    remaining = clean_text
    while remaining:
        if len(remaining) <= max_chars_per_event:
            chunks.append(remaining)
            break
        break_index = _best_break_index(remaining, max_chars_per_event)
        chunk = remaining[:break_index].strip()
        remaining = remaining[break_index:].strip()
        if not chunk:
            chunk = remaining[:max_chars_per_event].strip()
            remaining = remaining[max_chars_per_event:].strip()
        chunks.append(chunk)
    return chunks


def split_subtitle_lines(
    text: str,
    max_chars_per_line: int = 34,
    max_lines: int = DEFAULT_SUBTITLE_MAX_LINES,
) -> str:
    clean_text = _normalize_text(text)
    if not clean_text:
        return ""

    line_limit = max(1, max_chars_per_line)
    remaining = clean_text
    lines: list[str] = []
    for line_index in range(max(1, max_lines)):
        if not remaining:
            break
        if len(remaining) <= line_limit or line_index == max_lines - 1:
            lines.append(remaining)
            break
        remaining_line_count = max_lines - line_index
        minimum = (
            max(1, len(remaining) - line_limit * (remaining_line_count - 1))
            if len(remaining) <= line_limit * remaining_line_count
            else None
        )
        break_index = _best_break_index(remaining, line_limit, minimum=minimum)
        lines.append(remaining[:break_index].strip())
        remaining = remaining[break_index:].strip()

    return "\\N".join(line for line in lines if line)


def split_overlay_lines(
    text: str,
    max_chars_per_line: int = 20,
    max_lines: int = 2,
) -> str:
    """Honor manual breaks and balance legacy one-line title/hook text."""
    clean_text = normalize_overlay_text(text, max_lines=max_lines)
    if not clean_text:
        return ""
    manual_lines = clean_text.split("\n")
    if len(manual_lines) > 1:
        return "\\N".join(manual_lines)
    if overlay_text_width_units(clean_text) <= max(1, max_chars_per_line):
        return clean_text
    return "\\N".join(balanced_overlay_lines(clean_text, max_lines=max_lines))


def _escape_ass_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def _clip_segment_to_candidate(segment: TranscriptSegment, candidate: Candidate) -> TranscriptSegment | None:
    if segment.clip_id is not None and segment.clip_id != candidate.id:
        return None
    start = max(segment.start, candidate.start)
    end = min(segment.end, candidate.end)
    text = _normalize_text(segment.text)
    if end <= start or not text:
        return None
    return TranscriptSegment(
        start=round(start - candidate.start, 3),
        end=round(end - candidate.start, 3),
        text=text,
        confidence=segment.confidence,
        clipId=segment.clip_id,
    )


def clipped_transcript_segments(
    transcript_segments: Sequence[TranscriptSegment],
    candidate: Candidate,
) -> list[TranscriptSegment]:
    clipped: list[TranscriptSegment] = []
    for segment in transcript_segments:
        clipped_segment = _clip_segment_to_candidate(segment, candidate)
        if clipped_segment is not None:
            clipped.append(clipped_segment)
    return clipped


def _segment_events(segment: TranscriptSegment, layout: SubtitleLayout) -> list[SubtitleEvent]:
    text = _normalize_text(segment.text)
    if not text:
        return []

    duration = max(0.01, segment.end - segment.start)
    max_chars_per_event = max(1, layout.max_chars_per_line * layout.max_lines)
    max_events_for_duration = max(1, int(duration // layout.min_subtitle_duration))
    event_char_limit = max_chars_per_event
    chunks = split_subtitle_text(text, event_char_limit)
    min_events_for_max_duration = max(1, math.ceil(duration / layout.max_subtitle_duration))
    if len(chunks) < min_events_for_max_duration and len(text) >= min_events_for_max_duration * 4:
        event_char_limit = max(4, math.ceil(len(text) / min_events_for_max_duration))
        chunks = split_subtitle_text(text, event_char_limit)
    if len(chunks) > max_events_for_duration:
        event_char_limit = max(max_chars_per_event, math.ceil(len(text) / max_events_for_duration))
        chunks = split_subtitle_text(text, event_char_limit)

    total_weight = sum(max(1, len(chunk)) for chunk in chunks)
    cursor = segment.start
    events: list[SubtitleEvent] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            end = segment.end
        else:
            weight = max(1, len(chunk))
            end = cursor + duration * weight / total_weight
            end = min(end, segment.end)
        if end <= cursor:
            end = min(segment.end, cursor + 0.01)
        events.append(SubtitleEvent(start=round(cursor, 3), end=round(end, 3), text=chunk))
        cursor = end
    return [event for event in events if event.end > event.start and event.text]


def _can_merge_events(previous: SubtitleEvent, current: SubtitleEvent, layout: SubtitleLayout) -> bool:
    if previous.style != current.style:
        return False
    gap = current.start - previous.end
    if gap < -0.01:
        return False
    combined_text = _normalize_text(f"{previous.text} {current.text}")
    max_chars = layout.max_chars_per_line * layout.max_lines
    combined_duration = current.end - previous.start
    needs_more_time = (
        previous.end - previous.start < layout.min_subtitle_duration
        or current.end - current.start < layout.min_subtitle_duration
    )
    return (
        gap <= layout.min_gap_between_subtitles + 0.05
        and combined_duration <= layout.max_subtitle_duration
        and len(combined_text) <= max_chars
        and (needs_more_time or len(previous.text) + len(current.text) <= max_chars)
    )


def _merge_adjacent_events(events: Sequence[SubtitleEvent], layout: SubtitleLayout) -> list[SubtitleEvent]:
    merged: list[SubtitleEvent] = []
    for event in events:
        if merged and _can_merge_events(merged[-1], event, layout):
            previous = merged[-1]
            merged[-1] = SubtitleEvent(
                start=previous.start,
                end=event.end,
                text=_normalize_text(f"{previous.text} {event.text}"),
                style=previous.style,
            )
            continue
        merged.append(event)
    return merged


def _apply_minimum_display_duration(
    events: Sequence[SubtitleEvent],
    *,
    candidate_duration: float,
    layout: SubtitleLayout,
) -> list[SubtitleEvent]:
    adjusted: list[SubtitleEvent] = []
    for index, event in enumerate(events):
        next_start = events[index + 1].start if index + 1 < len(events) else None
        max_allowed_end = (
            next_start - layout.min_gap_between_subtitles if next_start is not None else candidate_duration
        )
        max_end = max(event.start, min(candidate_duration, max_allowed_end))
        target_end = max(event.end, event.start + layout.min_subtitle_duration)
        end = min(target_end, max_end) if max_end > event.start else event.end
        if end <= event.start:
            end = event.end
        adjusted.append(replace(event, end=round(end, 3)))
    return adjusted


def subtitle_events_for_candidate(
    transcript_segments: Sequence[TranscriptSegment],
    candidate: Candidate,
    layout: SubtitleLayout | None = None,
) -> list[SubtitleEvent]:
    active_layout = layout or (
        SubtitleLayout.short() if candidate.type == "short" else SubtitleLayout.normal()
    )
    raw_events: list[SubtitleEvent] = []
    styles_by_range = {(item.start, item.end): item.style for item in candidate.subtitle_styles}
    for source_segment in transcript_segments:
        override = styles_by_range.get((source_segment.start, source_segment.end))
        for segment in clipped_transcript_segments([source_segment], candidate):
            raw_events.extend(
                replace(event, style=override) for event in _segment_events(segment, active_layout)
            )
    merged = _merge_adjacent_events(raw_events, active_layout)
    adjusted = _apply_minimum_display_duration(
        merged,
        candidate_duration=candidate.duration,
        layout=active_layout,
    )
    remapped = _merge_adjacent_events(adjusted, active_layout)
    return _apply_minimum_display_duration(
        remapped,
        candidate_duration=candidate.duration,
        layout=active_layout,
    )


def _hook_scene_duration(candidate: Candidate) -> float:
    if candidate.hook_scene_start is None or candidate.hook_scene_end is None:
        return 0.0
    return candidate.hook_scene_end - candidate.hook_scene_start


def _subtitle_events_with_hook_scene(
    transcript_segments: Sequence[TranscriptSegment],
    candidate: Candidate,
    layout: SubtitleLayout,
) -> tuple[list[SubtitleEvent], float]:
    hook_scene_duration = _hook_scene_duration(candidate)
    body_events = subtitle_events_for_candidate(
        transcript_segments,
        candidate,
        layout,
    )
    hook_text_duration = 0.0
    if _normalize_text(candidate.hook_text or ""):
        hook_text_duration = candidate.hook_duration_seconds or 3.0
    if hook_scene_duration <= 0 and hook_text_duration <= 0:
        return body_events, candidate.duration

    output_duration = candidate.duration + hook_scene_duration
    suppression_end = round(
        min(
            output_duration,
            max(hook_scene_duration, hook_text_duration),
        ),
        3,
    )
    shifted_body_events: list[SubtitleEvent] = []
    for event in body_events:
        shifted_start = round(event.start + hook_scene_duration, 3)
        shifted_end = round(event.end + hook_scene_duration, 3)
        if shifted_end <= suppression_end:
            continue
        shifted_body_events.append(
            SubtitleEvent(
                start=round(max(shifted_start, suppression_end), 3),
                end=shifted_end,
                text=event.text,
                style=event.style,
            )
        )
    return shifted_body_events, output_duration


def subtitle_events_for_candidate_output(
    transcript_segments: Sequence[TranscriptSegment],
    candidate: Candidate,
    layout: SubtitleLayout,
) -> tuple[list[SubtitleEvent], float]:
    """Return the exact subtitle event sequence consumed by ASS rendering."""
    return _subtitle_events_with_hook_scene(
        transcript_segments,
        candidate,
        layout,
    )


def _ass_color(color: str, default: str) -> str:
    normalized = _coerce_hex_color(color, default)
    red = normalized[1:3]
    green = normalized[3:5]
    blue = normalized[5:7]
    return f"&H00{blue}{green}{red}"


def _style_line(
    name: str,
    font_name: str,
    font_size: int,
    layout: SubtitleLayout,
    alignment: int,
    margin_v: int,
    *,
    primary_color: str = DEFAULT_SUBTITLE_PRIMARY_COLOR,
    outline_color: str = DEFAULT_SUBTITLE_OUTLINE_COLOR,
    outline: int | None = None,
    shadow: int | None = None,
    margin_x: int | None = None,
    bold: bool = True,
) -> str:
    ass_primary_color = _ass_color(primary_color, DEFAULT_SUBTITLE_PRIMARY_COLOR)
    ass_outline_color = _ass_color(outline_color, DEFAULT_SUBTITLE_OUTLINE_COLOR)
    resolved_outline = layout.outline if outline is None else outline
    resolved_shadow = layout.shadow if shadow is None else shadow
    resolved_margin_x = layout.margin_x if margin_x is None else margin_x
    return (
        f"Style: {name},{font_name},{font_size},{ass_primary_color},&H000000FF,"
        f"{ass_outline_color},&H80000000,"
        f"{1 if bold else 0},0,0,0,100,100,0,0,1,"
        f"{resolved_outline},{resolved_shadow},{alignment},"
        f"{resolved_margin_x},{resolved_margin_x},{margin_v},1"
    )


def _font_preset_for(font_name: str, bold: bool) -> TextFontPreset | None:
    return next(
        (
            preset
            for preset, (preset_font_name, preset_bold) in TEXT_FONT_PRESETS.items()
            if preset_font_name == font_name and preset_bold is bold
        ),
        None,
    )


def _style_font(
    style: ClipTextStyle,
    *,
    fallback_font_name: str,
) -> tuple[str, bool]:
    preset_font = (
        TEXT_FONT_PRESETS.get(style.font_preset)
        if style.font_preset is not None
        else None
    )
    font_name = style.font_name or (
        preset_font[0] if preset_font is not None else fallback_font_name
    )
    bold = style.bold
    if bold is None:
        bold = preset_font[1] if preset_font is not None else True
    return font_name, bold


def _position_tag(
    x_percent: float,
    y_percent: float,
    layout: SubtitleLayout,
) -> str:
    x = round(layout.width * x_percent / 100)
    y = round(layout.height * y_percent / 100)
    return rf"{{\an5\pos({x},{y})}}"


def _alignment_position(
    alignment: int,
    *,
    margin_x: int,
    margin_v: int,
    layout: SubtitleLayout,
) -> tuple[float, float]:
    if alignment in {1, 4, 7}:
        x = margin_x
    elif alignment in {3, 6, 9}:
        x = layout.width - margin_x
    else:
        x = layout.width / 2

    if alignment in {1, 2, 3}:
        y = layout.height - margin_v
    elif alignment in {7, 8, 9}:
        y = margin_v
    else:
        y = layout.height / 2
    return x * 100 / layout.width, y * 100 / layout.height


def resolve_clip_text_style(
    style: ClipTextStyle | None,
    layout: SubtitleLayout,
    *,
    role: TextStyleRole,
) -> ResolvedTextStyle:
    is_subtitle = role == "subtitle"
    fallback_font_name = layout.font_name if is_subtitle else layout.title_font_name
    fallback_font_size = layout.font_size if is_subtitle else layout.title_font_size
    fallback_alignment = (
        layout.subtitle_alignment if is_subtitle else layout.title_alignment
    )
    fallback_margin_v = layout.lower_margin if is_subtitle else layout.top_margin
    fallback_primary_color = (
        layout.primary_color if is_subtitle else DEFAULT_SUBTITLE_PRIMARY_COLOR
    )
    fallback_outline_color = (
        layout.outline_color if is_subtitle else DEFAULT_SUBTITLE_OUTLINE_COLOR
    )

    if style is None:
        font_name = fallback_font_name
        # Noto Sans JP Black is already the exact heavy face shared with the
        # browser; synthetic ASS bold would make preview and render diverge.
        bold = font_name != DEFAULT_ASS_TITLE_FONT
        font_size = fallback_font_size
        primary_color = fallback_primary_color
        outline_color = fallback_outline_color
        outline_width = layout.outline
        position_mode: TextStylePositionMode = "layout"
    else:
        font_name, bold = _style_font(
            style,
            fallback_font_name=fallback_font_name,
        )
        font_size = style.font_size
        primary_color = style.primary_color
        outline_color = style.outline_color
        outline_width = style.outline_width
        position_mode = style.position_mode

    if position_mode == "explicit" and style is not None:
        x_percent = style.x_percent
        y_percent = style.y_percent
        position_override = True
        style_alignment = 5
        alignment = 5
        margin_x = 0
        margin_v = 0
    else:
        style_alignment = fallback_alignment
        margin_x = layout.margin_x
        margin_v = fallback_margin_v
        if (
            is_subtitle
            and layout.subtitle_x_percent is not None
            and layout.subtitle_y_percent is not None
        ):
            x_percent = layout.subtitle_x_percent
            y_percent = layout.subtitle_y_percent
            position_override = True
            alignment = 5
        elif not is_subtitle and layout.subtitle_y_percent is not None:
            x_percent = (
                DEFAULT_SHORT_TITLE_X_PERCENT
                if role == "title"
                else DEFAULT_SHORT_HOOK_X_PERCENT
            )
            y_percent = (
                DEFAULT_SHORT_TITLE_Y_PERCENT
                if role == "title"
                else DEFAULT_SHORT_HOOK_Y_PERCENT
            )
            position_override = True
            alignment = 5
        else:
            x_percent, y_percent = _alignment_position(
                fallback_alignment,
                margin_x=layout.margin_x,
                margin_v=fallback_margin_v,
                layout=layout,
            )
            position_override = False
            alignment = fallback_alignment

    return ResolvedTextStyle(
        font_preset=_font_preset_for(font_name, bold),
        font_name=font_name,
        font_size=font_size,
        primary_color=primary_color,
        outline_color=outline_color,
        outline_width=outline_width,
        shadow=layout.shadow,
        bold=bold,
        alignment=alignment,
        style_alignment=style_alignment,
        margin_x=margin_x,
        margin_v=margin_v,
        x_percent=x_percent,
        y_percent=y_percent,
        position_mode=position_mode,
        position_override=position_override,
        outer_outline_color=style.outer_outline_color if style else "#FFFFFF",
        outer_outline_width=style.outer_outline_width if style else 0,
    )


def _subtitle_position_tag(
    style: ClipTextStyle | None,
    layout: SubtitleLayout,
) -> str:
    resolved = resolve_clip_text_style(style, layout, role="subtitle")
    if not resolved.position_override:
        return ""
    return _position_tag(
        resolved.x_percent,
        resolved.y_percent,
        layout,
    )


def _clip_style_line(
    name: str,
    style: ClipTextStyle | None,
    layout: SubtitleLayout,
) -> str:
    role: TextStyleRole = (
        "subtitle" if name == "Subtitle" else "title" if name == "Title" else "hook"
    )
    resolved = resolve_clip_text_style(style, layout, role=role)
    return _style_line(
        name,
        resolved.font_name,
        resolved.font_size,
        layout,
        alignment=resolved.style_alignment,
        margin_v=resolved.margin_v,
        primary_color=resolved.primary_color,
        outline_color=resolved.outline_color,
        outline=resolved.outline_width,
        margin_x=resolved.margin_x,
        bold=resolved.bold,
    )


def _outlined_dialogues(line: str, style: ResolvedTextStyle) -> list[str]:
    if not style.outer_outline_width:
        return [line]
    parts = line.split(",", 9)
    parts[0] = f"Dialogue: {int(parts[0].split(':')[1]) - 1}"
    # Both layers share identical glyphs, line breaks, coordinates and times.
    text = re.sub(r"\\(?:bord[0-9.]+|3c&H[0-9A-Fa-f]+&?|shad[0-9.]+)", "", parts[9])
    color = _ass_color(style.outer_outline_color, "#FFFFFF")[4:]  # BGR, without ASS alpha
    parts[9] = rf"{{\bord{style.outline_width + style.outer_outline_width}\3c&H{color}&\shad0}}" + text
    return [",".join(parts), line]


def build_ass_document(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    layout: SubtitleLayout | None = None,
    top_title: str | None = None,
) -> str:
    active_layout = layout or (
        SubtitleLayout.short() if candidate.type == "short" else SubtitleLayout.normal()
    )
    subtitle_events, output_duration = subtitle_events_for_candidate_output(
        transcript_segments,
        candidate,
        active_layout,
    )
    title_text = normalize_overlay_text(
        top_title if top_title is not None else (candidate.overlay_title or "")
    )
    include_title = bool(title_text)
    hook_text = normalize_overlay_text(candidate.hook_text or "")
    include_hook = bool(hook_text)
    hook_end = min(
        output_duration,
        candidate.hook_duration_seconds or 3.0,
    )

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {active_layout.width}",
        f"PlayResY: {active_layout.height}",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        _clip_style_line(
            "Subtitle",
            candidate.subtitle_style,
            active_layout,
        ),
        _clip_style_line(
            "Title",
            candidate.title_style,
            active_layout,
        ),
        _clip_style_line(
            "Hook",
            candidate.hook_style,
            active_layout,
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if include_title:
        title_start = hook_end if include_hook else 0.0
        if candidate.type == "normal":
            title_start = max(title_start, _hook_scene_duration(candidate))
        if title_start < output_duration:
            resolved_title_style = resolve_clip_text_style(
                candidate.title_style,
                active_layout,
                role="title",
            )
            title_fit = fit_overlay_text(
                title_text,
                output_width=active_layout.width,
                font_name=resolved_title_style.font_name,
                font_size=resolved_title_style.font_size,
                margin_x=resolved_title_style.margin_x,
                outline_width=resolved_title_style.outline_width + resolved_title_style.outer_outline_width,
                shadow=resolved_title_style.shadow,
                alignment=resolved_title_style.alignment,
                x_percent=resolved_title_style.x_percent,
            )
            title_position = (
                _position_tag(
                    resolved_title_style.x_percent,
                    resolved_title_style.y_percent,
                    active_layout,
                )
                if resolved_title_style.position_override
                else ""
            )
            lines.extend(_outlined_dialogues(
                "Dialogue: "
                f"1,{format_ass_timestamp(title_start)},{format_ass_timestamp(output_duration)},"
                f"Title,,0,0,0,,"
                f"{title_position}"
                rf"{{\fs{title_fit.effective_font_size}}}"
                f"{_escape_ass_text(title_fit.ass_text)}", resolved_title_style
            ))

    if include_hook:
        resolved_hook_style = resolve_clip_text_style(
            candidate.hook_style,
            active_layout,
            role="hook",
        )
        hook_fit = fit_overlay_text(
            hook_text,
            output_width=active_layout.width,
            font_name=resolved_hook_style.font_name,
            font_size=resolved_hook_style.font_size,
            margin_x=resolved_hook_style.margin_x,
            outline_width=resolved_hook_style.outline_width + resolved_hook_style.outer_outline_width,
            shadow=resolved_hook_style.shadow,
            alignment=resolved_hook_style.alignment,
            x_percent=resolved_hook_style.x_percent,
        )
        hook_position = (
            _position_tag(
                resolved_hook_style.x_percent,
                resolved_hook_style.y_percent,
                active_layout,
            )
            if resolved_hook_style.position_override
            else ""
        )
        lines.extend(_outlined_dialogues(
            "Dialogue: "
            f"2,{format_ass_timestamp(0.0)},{format_ass_timestamp(hook_end)},"
            f"Hook,Hook,0,0,0,,"
            f"{hook_position}"
            rf"{{\fs{hook_fit.effective_font_size}}}"
            f"{_escape_ass_text(hook_fit.ass_text)}", resolved_hook_style
        ))

    for event in subtitle_events:
        event_style = event.style or candidate.subtitle_style
        resolved_subtitle_style = resolve_clip_text_style(event_style, active_layout, role="subtitle")
        subtitle_position = _subtitle_position_tag(event_style, active_layout)
        overrides = ""
        if event.style is not None:
            resolved = resolved_subtitle_style
            overrides = (
                rf"{{\fn{resolved.font_name}\b{int(resolved.bold)}"
                rf"\1c&H{_ass_color(resolved.primary_color, '#FFFFFF')[4:]}&"
                rf"\3c&H{_ass_color(resolved.outline_color, '#000000')[4:]}&"
                rf"\bord{resolved.outline_width}\an{resolved.alignment}}}"
            )
        split_text = split_subtitle_lines(
            event.text,
            max_chars_per_line=active_layout.max_chars_per_line,
            max_lines=min(DEFAULT_SUBTITLE_MAX_LINES, active_layout.max_lines),
        )
        subtitle_fit = fit_overlay_text(
            split_text,
            output_width=active_layout.width,
            font_name=resolved_subtitle_style.font_name,
            font_size=resolved_subtitle_style.font_size,
            margin_x=resolved_subtitle_style.margin_x,
            outline_width=resolved_subtitle_style.outline_width + resolved_subtitle_style.outer_outline_width,
            shadow=resolved_subtitle_style.shadow,
            alignment=resolved_subtitle_style.alignment,
            x_percent=resolved_subtitle_style.x_percent,
            max_lines=min(DEFAULT_SUBTITLE_MAX_LINES, active_layout.max_lines),
        )
        text = _escape_ass_text(subtitle_fit.ass_text)
        lines.extend(_outlined_dialogues(
            "Dialogue: "
            f"0,{format_ass_timestamp(event.start)},{format_ass_timestamp(event.end)},"
            f"Subtitle,,0,0,0,,{overrides}{subtitle_position}"
            rf"{{\fs{subtitle_fit.effective_font_size}}}"
            f"{text}", resolved_subtitle_style
        ))

    return "\n".join(lines) + "\n"


def write_ass_for_candidate(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    output_path: str | Path,
    layout: SubtitleLayout | None = None,
    top_title: str | None = None,
    subtitle_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_ass_document(
            candidate,
            transcript_segments,
            layout=layout
            or (
                SubtitleLayout.short(settings=subtitle_settings)
                if candidate.type == "short"
                else SubtitleLayout.normal(settings=subtitle_settings)
            ),
            top_title=top_title,
        ),
        encoding="utf-8",
    )
    return path


def write_ass_for_selected_clips(
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    output_dir: str | Path,
    normal_width: int = DEFAULT_NORMAL_WIDTH,
    normal_height: int = DEFAULT_NORMAL_HEIGHT,
    subtitle_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    base_dir = Path(output_dir)

    for candidate in [*selection.normal_clips, *selection.shorts]:
        layout = (
            SubtitleLayout.short(settings=subtitle_settings)
            if candidate.type == "short"
            else SubtitleLayout.normal(width=normal_width, height=normal_height, settings=subtitle_settings)
        )
        paths[candidate.id] = write_ass_for_candidate(
            candidate,
            transcript_segments,
            base_dir / f"{candidate.id}.ass",
            layout=layout,
            subtitle_settings=subtitle_settings,
        )

    return paths
