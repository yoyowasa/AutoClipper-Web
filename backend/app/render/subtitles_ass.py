from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
DEFAULT_NORMAL_WIDTH = 1920
DEFAULT_NORMAL_HEIGHT = 1080
DEFAULT_ASS_FONT = "Noto Sans CJK JP"


@dataclass(frozen=True)
class SubtitleLayout:
    width: int
    height: int
    font_name: str
    font_size: int
    title_font_size: int
    outline: int
    shadow: int
    margin_x: int
    lower_margin: int
    top_margin: int

    @classmethod
    def short(cls) -> "SubtitleLayout":
        return cls(
            width=SHORT_WIDTH,
            height=SHORT_HEIGHT,
            font_name=DEFAULT_ASS_FONT,
            font_size=76,
            title_font_size=88,
            outline=5,
            shadow=2,
            margin_x=86,
            lower_margin=250,
            top_margin=150,
        )

    @classmethod
    def normal(cls, width: int = DEFAULT_NORMAL_WIDTH, height: int = DEFAULT_NORMAL_HEIGHT) -> "SubtitleLayout":
        safe_width = max(320, int(width))
        safe_height = max(240, int(height))
        font_size = max(42, min(72, round(safe_height * 0.06)))
        return cls(
            width=safe_width,
            height=safe_height,
            font_name=DEFAULT_ASS_FONT,
            font_size=font_size,
            title_font_size=max(font_size + 6, round(safe_height * 0.07)),
            outline=max(3, round(safe_height * 0.004)),
            shadow=max(1, round(safe_height * 0.002)),
            margin_x=round(safe_width * 0.08),
            lower_margin=round(safe_height * 0.08),
            top_margin=round(safe_height * 0.08),
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


def split_subtitle_lines(text: str, max_chars_per_line: int = 34) -> str:
    clean_text = _normalize_text(text)
    if not clean_text:
        return ""

    if " " not in clean_text:
        midpoint = min(max_chars_per_line, max(1, len(clean_text) // 2))
        if len(clean_text) <= max_chars_per_line:
            return clean_text
        return f"{clean_text[:midpoint]}\\N{clean_text[midpoint:]}"

    words = clean_text.split(" ")
    first_line: list[str] = []
    second_line: list[str] = []
    active_line = first_line

    for word in words:
        candidate = " ".join([*active_line, word])
        if active_line is first_line and active_line and len(candidate) > max_chars_per_line:
            active_line = second_line
        active_line.append(word)

    lines = [" ".join(first_line).strip()]
    second = " ".join(second_line).strip()
    if second:
        lines.append(second)
    return "\\N".join(line for line in lines[:2] if line)


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


def _style_line(
    name: str,
    font_size: int,
    layout: SubtitleLayout,
    alignment: int,
    margin_v: int,
) -> str:
    return (
        f"Style: {name},{layout.font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
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
    clipped_segments = clipped_transcript_segments(transcript_segments, candidate)
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
            f"Title,,0,0,0,,{_escape_ass_text(split_subtitle_lines(title_text, max_chars_per_line=26))}"
        )

    for segment in clipped_segments:
        text = _escape_ass_text(split_subtitle_lines(segment.text))
        lines.append(
            "Dialogue: "
            f"0,{format_ass_timestamp(segment.start)},{format_ass_timestamp(segment.end)},"
            f"Subtitle,,0,0,0,,{text}"
        )

    return "\n".join(lines) + "\n"


def write_ass_for_candidate(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    output_path: str | Path,
    layout: SubtitleLayout | None = None,
    top_title: str | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_ass_document(
            candidate,
            transcript_segments,
            layout=layout,
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
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    base_dir = Path(output_dir)

    for candidate in [*selection.normal_clips, *selection.shorts]:
        layout = (
            SubtitleLayout.short()
            if candidate.type == "short"
            else SubtitleLayout.normal(width=normal_width, height=normal_height)
        )
        paths[candidate.id] = write_ass_for_candidate(
            candidate,
            transcript_segments,
            base_dir / f"{candidate.id}.ass",
            layout=layout,
        )

    return paths
