import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
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


@dataclass(frozen=True)
class SubtitleEvent:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleLayout:
    width: int
    height: int
    font_size: int
    title_font_size: int
    outline: int
    shadow: int
    margin_x: int
    lower_margin: int
    top_margin: int
    max_chars_per_line: int
    max_lines: int
    min_subtitle_duration: float
    max_subtitle_duration: float
    min_gap_between_subtitles: float

    @classmethod
    def short(cls, settings: SubtitleRenderSettings | dict[str, Any] | None = None) -> "SubtitleLayout":
        parsed_settings = parse_subtitle_settings(settings)
        return cls(
            width=SHORT_WIDTH,
            height=SHORT_HEIGHT,
            font_size=76,
            title_font_size=88,
            outline=5,
            shadow=2,
            margin_x=86,
            lower_margin=250,
            top_margin=150,
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
        font_size = max(42, min(72, round(safe_height * 0.06)))
        return cls(
            width=safe_width,
            height=safe_height,
            font_size=font_size,
            title_font_size=max(font_size + 6, round(safe_height * 0.07)),
            outline=max(3, round(safe_height * 0.004)),
            shadow=max(1, round(safe_height * 0.002)),
            margin_x=round(safe_width * 0.08),
            lower_margin=round(safe_height * 0.08),
            top_margin=round(safe_height * 0.08),
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


def _style_line(
    name: str,
    font_size: int,
    layout: SubtitleLayout,
    alignment: int,
    margin_v: int,
) -> str:
    return (
        f"Style: {name},Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"1,0,0,0,100,100,0,0,1,{layout.outline},{layout.shadow},{alignment},"
        f"{layout.margin_x},{layout.margin_x},{margin_v},1"
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
    subtitle_events = subtitle_events_for_candidate(transcript_segments, candidate, active_layout)
    title_text = _normalize_text(top_title if top_title is not None else (candidate.overlay_title or ""))
    include_title = candidate.type == "short" and bool(title_text)

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
        _style_line("Subtitle", active_layout.font_size, active_layout, alignment=2, margin_v=active_layout.lower_margin),
        _style_line("Title", active_layout.title_font_size, active_layout, alignment=8, margin_v=active_layout.top_margin),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if include_title:
        lines.append(
            "Dialogue: "
            f"1,{format_ass_timestamp(0.0)},{format_ass_timestamp(candidate.duration)},"
            f"Title,,0,0,0,,"
            f"{_escape_ass_text(split_subtitle_lines(title_text, max_chars_per_line=20, max_lines=2))}"
        )

    for event in subtitle_events:
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
            f"Subtitle,,0,0,0,,{text}"
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
