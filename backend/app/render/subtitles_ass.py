import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.candidates.select_candidates import CandidateSelection


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
TEXT_FONT_PRESETS: dict[str, tuple[str, bool]] = {
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
    title_font_name: str = DEFAULT_ASS_FONT
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
        title_font_name=_coerce_str(normalized.get("title_font_name"), DEFAULT_ASS_FONT),
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


def _escape_ass_text(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def _clip_segment_to_candidate(segment: TranscriptSegment, candidate: Candidate) -> TranscriptSegment | None:
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
        adjusted.append(SubtitleEvent(start=event.start, end=round(end, 3), text=event.text))
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
    for segment in clipped_transcript_segments(transcript_segments, candidate):
        raw_events.extend(_segment_events(segment, active_layout))
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
    hook_duration = _hook_scene_duration(candidate)
    body_events = subtitle_events_for_candidate(
        transcript_segments,
        candidate,
        layout,
    )
    if hook_duration <= 0:
        return body_events, candidate.duration

    hook_candidate = candidate.model_copy(
        update={
            "start": candidate.hook_scene_start,
            "end": candidate.hook_scene_end,
            "duration": hook_duration,
            "hook_scene_start": None,
            "hook_scene_end": None,
        }
    )
    hook_events = subtitle_events_for_candidate(
        transcript_segments,
        hook_candidate,
        layout,
    )
    shifted_body_events = [
        SubtitleEvent(
            start=round(event.start + hook_duration, 3),
            end=round(event.end + hook_duration, 3),
            text=event.text,
        )
        for event in body_events
    ]
    return [*hook_events, *shifted_body_events], candidate.duration + hook_duration


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


def _style_font(style: ClipTextStyle) -> tuple[str, bool]:
    return TEXT_FONT_PRESETS[style.font_preset]


def _position_tag(
    x_percent: float,
    y_percent: float,
    layout: SubtitleLayout,
) -> str:
    x = round(layout.width * x_percent / 100)
    y = round(layout.height * y_percent / 100)
    return rf"{{\an5\pos({x},{y})}}"


def _style_position_tag(style: ClipTextStyle, layout: SubtitleLayout) -> str:
    return _position_tag(style.x_percent, style.y_percent, layout)


def _subtitle_position_tag(
    style: ClipTextStyle | None,
    layout: SubtitleLayout,
) -> str:
    if style is not None:
        return _style_position_tag(style, layout)
    if layout.subtitle_x_percent is None or layout.subtitle_y_percent is None:
        return ""
    return _position_tag(
        layout.subtitle_x_percent,
        layout.subtitle_y_percent,
        layout,
    )


def _clip_style_line(
    name: str,
    style: ClipTextStyle | None,
    layout: SubtitleLayout,
    *,
    fallback_font_name: str,
    fallback_font_size: int,
    fallback_alignment: int,
    fallback_margin_v: int,
    fallback_primary_color: str = DEFAULT_SUBTITLE_PRIMARY_COLOR,
    fallback_outline_color: str = DEFAULT_SUBTITLE_OUTLINE_COLOR,
) -> str:
    if style is None:
        return _style_line(
            name,
            fallback_font_name,
            fallback_font_size,
            layout,
            alignment=fallback_alignment,
            margin_v=fallback_margin_v,
            primary_color=fallback_primary_color,
            outline_color=fallback_outline_color,
        )

    font_name, bold = _style_font(style)
    return _style_line(
        name,
        font_name,
        style.font_size,
        layout,
        alignment=5,
        margin_v=0,
        primary_color=style.primary_color,
        outline_color=style.outline_color,
        outline=style.outline_width,
        margin_x=0,
        bold=bold,
    )


def build_ass_document(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    layout: SubtitleLayout | None = None,
    top_title: str | None = None,
) -> str:
    active_layout = layout or (
        SubtitleLayout.short() if candidate.type == "short" else SubtitleLayout.normal()
    )
    subtitle_events, output_duration = _subtitle_events_with_hook_scene(
        transcript_segments,
        candidate,
        active_layout,
    )
    title_text = _normalize_text(top_title if top_title is not None else (candidate.overlay_title or ""))
    include_title = candidate.type == "short" and bool(title_text)
    hook_text = _normalize_text(candidate.hook_text or "")
    include_hook = candidate.type == "short" and bool(hook_text)
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
            fallback_font_name=active_layout.font_name,
            fallback_font_size=active_layout.font_size,
            fallback_alignment=active_layout.subtitle_alignment,
            fallback_margin_v=active_layout.lower_margin,
            fallback_primary_color=active_layout.primary_color,
            fallback_outline_color=active_layout.outline_color,
        ),
        _clip_style_line(
            "Title",
            candidate.title_style,
            active_layout,
            fallback_font_name=active_layout.title_font_name,
            fallback_font_size=active_layout.title_font_size,
            fallback_alignment=active_layout.title_alignment,
            fallback_margin_v=active_layout.top_margin,
        ),
        _clip_style_line(
            "Hook",
            candidate.hook_style,
            active_layout,
            fallback_font_name=active_layout.title_font_name,
            fallback_font_size=active_layout.title_font_size,
            fallback_alignment=active_layout.title_alignment,
            fallback_margin_v=active_layout.top_margin,
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if include_title:
        title_start = hook_end if include_hook else 0.0
        if title_start < output_duration:
            title_position = (
                _style_position_tag(candidate.title_style, active_layout)
                if candidate.title_style is not None
                else (
                    _position_tag(
                        DEFAULT_SHORT_TITLE_X_PERCENT,
                        DEFAULT_SHORT_TITLE_Y_PERCENT,
                        active_layout,
                    )
                    if active_layout.subtitle_y_percent is not None
                    else ""
                )
            )
            lines.append(
                "Dialogue: "
                f"1,{format_ass_timestamp(title_start)},{format_ass_timestamp(output_duration)},"
                f"Title,,0,0,0,,"
                f"{title_position}"
                f"{_escape_ass_text(split_subtitle_lines(title_text, max_chars_per_line=20, max_lines=2))}"
            )

    if include_hook:
        hook_position = (
            _style_position_tag(candidate.hook_style, active_layout)
            if candidate.hook_style is not None
            else (
                _position_tag(
                    DEFAULT_SHORT_HOOK_X_PERCENT,
                    DEFAULT_SHORT_HOOK_Y_PERCENT,
                    active_layout,
                )
                if active_layout.subtitle_y_percent is not None
                else ""
            )
        )
        lines.append(
            "Dialogue: "
            f"2,{format_ass_timestamp(0.0)},{format_ass_timestamp(hook_end)},"
            f"Hook,Hook,0,0,0,,"
            f"{hook_position}"
            f"{_escape_ass_text(split_subtitle_lines(hook_text, max_chars_per_line=20, max_lines=2))}"
        )

    for event in subtitle_events:
        subtitle_position = _subtitle_position_tag(
            candidate.subtitle_style,
            active_layout,
        )
        text = _escape_ass_text(
            split_subtitle_lines(
                event.text,
                max_chars_per_line=active_layout.max_chars_per_line,
                max_lines=active_layout.max_lines,
            )
        )
        lines.append(
            "Dialogue: "
            f"0,{format_ass_timestamp(event.start)},{format_ass_timestamp(event.end)},"
            f"Subtitle,,0,0,0,,{subtitle_position}{text}"
        )

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
