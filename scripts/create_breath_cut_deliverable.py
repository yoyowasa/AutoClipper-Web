"""Create an optional breath-cut MP4 from completed AutoClipper job artifacts.

This script is intentionally separate from the production pipeline. It reads
existing job JSON files, removes selected silence intervals, writes a plan plus
ASS/filter artifacts, and optionally renders through the Docker worker service.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FONT = "源ノ角ゴシック JP Heavy"
BREAK_CHARS = "。、！？!?、,"
SUBTITLE_SAFE_WIDTH = 1030
MIN_FONT_SIZE = 44
DEFAULT_SUBTITLE_X = 540
DEFAULT_SUBTITLE_Y = 1240
FONT_DIR = ROOT / "storage" / "fonts"


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str = ""


@dataclass(frozen=True)
class Interval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class SoftCutInterval:
    start: float
    end: float
    keep_silence: float


@dataclass(frozen=True)
class SubtitleEvent:
    start: float
    end: float
    text: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a breath-cut MP4 from AutoClipper job artifacts.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--source-container-path",
        default=None,
        help=(
            "Input MP4 path inside the Docker worker container, for example "
            "/app/storage/outputs/job_x/shorts/short_01.mp4. Required unless --dry-run is used."
        ),
    )
    parser.add_argument("--silence-json", type=Path, default=None)
    parser.add_argument("--output-name", default="short_01_breath_cut.mp4")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write breath_cut_plan.json, ASS, and filter_complex.txt, but skip ffmpeg rendering.",
    )
    parser.add_argument(
        "--docker-service",
        default="worker",
        help="docker compose service used for ffmpeg rendering.",
    )
    parser.add_argument("--min-cut-silence", type=float, default=0.35)
    parser.add_argument("--keep-silence", type=float, default=0.08)
    parser.add_argument("--speech-margin", type=float, default=0.04)
    parser.add_argument(
        "--protect-interval",
        action="append",
        default=[],
        help="Source timeline interval to keep uncut, formatted as start:end seconds. Can be repeated.",
    )
    parser.add_argument(
        "--soft-cut-interval",
        action="append",
        default=[],
        help=(
            "Source timeline interval to shorten even when protected, formatted as "
            "start:end:keep_seconds. Can be repeated."
        ),
    )
    parser.add_argument("--max-chars", type=int, default=22)
    parser.add_argument("--base-font-size", type=int, default=70)
    parser.add_argument("--font-name", default=DEFAULT_FONT)
    parser.add_argument(
        "--font-file",
        type=Path,
        default=None,
        help="Optional .ttf/.ttc/.otf file to copy into storage/fonts and expose to libass fontsdir.",
    )
    parser.add_argument("--subtitle-x", type=int, default=DEFAULT_SUBTITLE_X)
    parser.add_argument("--subtitle-y", type=int, default=DEFAULT_SUBTITLE_Y)
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def validate_args(args: argparse.Namespace) -> None:
    if not args.dry_run and not args.source_container_path:
        raise ValueError("--source-container-path is required unless --dry-run is used.")
    if args.output_name.endswith((".ass", ".json", ".txt")):
        raise ValueError("--output-name must be a rendered media filename, usually .mp4.")
    if args.min_cut_silence < 0:
        raise ValueError("--min-cut-silence must be non-negative.")
    if args.keep_silence < 0:
        raise ValueError("--keep-silence must be non-negative.")
    if args.speech_margin < 0:
        raise ValueError("--speech-margin must be non-negative.")
    if args.max_chars < 4:
        raise ValueError("--max-chars must be at least 4.")
    if args.base_font_size < MIN_FONT_SIZE:
        raise ValueError(f"--base-font-size must be at least {MIN_FONT_SIZE}.")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_intervals(values: list[str]) -> list[Interval]:
    intervals: list[Interval] = []
    for value in values:
        if ":" not in value:
            raise ValueError(f"Invalid interval {value!r}. Use start:end seconds.")
        start_text, end_text = value.split(":", 1)
        start = float(start_text)
        end = float(end_text)
        if end <= start:
            raise ValueError(f"Invalid interval {value!r}. End must be greater than start.")
        intervals.append(Interval(start, end))
    return merge_intervals(intervals)


def parse_soft_cut_intervals(values: list[str]) -> list[SoftCutInterval]:
    intervals: list[SoftCutInterval] = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid soft cut interval {value!r}. Use start:end:keep_seconds.")
        start = float(parts[0])
        end = float(parts[1])
        keep_silence = float(parts[2])
        if end <= start:
            raise ValueError(f"Invalid soft cut interval {value!r}. End must be greater than start.")
        if keep_silence < 0:
            raise ValueError(f"Invalid soft cut interval {value!r}. keep_seconds must be non-negative.")
        intervals.append(SoftCutInterval(start, end, keep_silence))
    return intervals


def timestamp(seconds: float) -> str:
    total_centiseconds = int(max(0.0, seconds) * 100 + 0.5)
    hours = total_centiseconds // 360000
    total_centiseconds %= 360000
    minutes = total_centiseconds // 6000
    total_centiseconds %= 6000
    secs = total_centiseconds // 100
    centiseconds = total_centiseconds % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def split_text(text: str, max_chars: int) -> list[str]:
    remaining = normalize_text(text)
    chunks: list[str] = []
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_at = -1
        search_end = min(len(remaining) - 1, max_chars)
        for index in range(search_end, max(4, max_chars // 2) - 1, -1):
            if remaining[index] in BREAK_CHARS:
                split_at = index + 1
                break
        if split_at < 0:
            for index in range(search_end, max(4, max_chars // 2) - 1, -1):
                if remaining[index] in " のはをがでにと":
                    split_at = index + 1
                    break
        if split_at < 0:
            split_at = max_chars

        chunk = remaining[:split_at].strip()
        remaining = remaining[split_at:].strip()
        while remaining and remaining[0] in "、。,.!?！？":
            chunk += remaining[0]
            remaining = remaining[1:].strip()
        chunks.append(chunk)

    if len(chunks) >= 2 and len(chunks[-1]) <= 2:
        chunks[-2] = f"{chunks[-2]}{chunks[-1]}"
        chunks.pop()
    return chunks


def text_width_units(text: str) -> float:
    units = 0.0
    for char in text:
        if char.isascii():
            units += 0.56 if char.isalnum() else 0.35
        elif char in "、。,.!?！？・":
            units += 0.52
        else:
            units += 1.0
    return max(1.0, units)


def font_size_for_single_line(text: str, base_font_size: int) -> int:
    estimated_size = int(SUBTITLE_SAFE_WIDTH / text_width_units(text))
    return max(MIN_FONT_SIZE, min(base_font_size, estimated_size))


def uniform_font_size(events: list[SubtitleEvent], base_font_size: int) -> int:
    if not events:
        return base_font_size
    return min(font_size_for_single_line(event.text, base_font_size) for event in events)


def position_override(text: str, *, subtitle_x: int, subtitle_y: int) -> str:
    return f"{{\\pos({subtitle_x},{subtitle_y})}}" + text


def escape_ass(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def cut_intervals(
    silences: list[Interval],
    transcripts: list[Segment],
    *,
    min_cut_silence: float,
    keep_silence: float,
    speech_margin: float,
    protected_intervals: list[Interval],
    soft_cut_intervals: list[SoftCutInterval],
) -> list[Interval]:
    cuts: list[Interval] = []
    for silence in silences:
        if silence.duration < min_cut_silence:
            continue
        soft_cut = matching_soft_cut(silence, soft_cut_intervals)
        if soft_cut is not None:
            start = max(silence.start, soft_cut.start) + soft_cut.keep_silence / 2
            end = min(silence.end, soft_cut.end) - soft_cut.keep_silence / 2
            cut = Interval(round(start, 6), round(end, 6))
            if cut.duration >= 0.08:
                cuts.append(cut)
            continue

        start = silence.start + keep_silence / 2
        end = silence.end - keep_silence / 2
        for segment in transcripts:
            if start < segment.end < end:
                start = max(start, segment.end + speech_margin)
            elif segment.end <= start and start - segment.end < speech_margin:
                start = max(start, segment.end + speech_margin)
            if start < segment.start < end:
                end = min(end, segment.start - speech_margin)
            elif end <= segment.start and segment.start - end < speech_margin:
                end = min(end, segment.start - speech_margin)
        cut = Interval(round(start, 6), round(end, 6))
        if cut.duration >= 0.08 and not overlaps_any(cut, protected_intervals):
            cuts.append(cut)
    return merge_intervals(cuts)


def matching_soft_cut(silence: Interval, soft_cut_intervals: list[SoftCutInterval]) -> SoftCutInterval | None:
    for soft_cut in soft_cut_intervals:
        if silence.start < soft_cut.end and soft_cut.start < silence.end:
            return soft_cut
    return None


def overlaps_any(interval: Interval, protected_intervals: list[Interval]) -> bool:
    return any(interval.start < protected.end and protected.start < interval.end for protected in protected_intervals)


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for interval in sorted(intervals, key=lambda item: item.start):
        if not merged or interval.start > merged[-1].end:
            merged.append(interval)
        else:
            previous = merged[-1]
            merged[-1] = Interval(previous.start, max(previous.end, interval.end))
    return merged


def keep_intervals(duration: float, cuts: list[Interval]) -> list[Interval]:
    keeps: list[Interval] = []
    cursor = 0.0
    for cut in cuts:
        if cut.start > cursor:
            keeps.append(Interval(round(cursor, 6), round(min(cut.start, duration), 6)))
        cursor = max(cursor, cut.end)
    if cursor < duration:
        keeps.append(Interval(round(cursor, 6), round(duration, 6)))
    return [item for item in keeps if item.duration > 0.02]


def map_time(value: float, cuts: list[Interval]) -> float:
    shifted = value
    for cut in cuts:
        if value >= cut.end:
            shifted -= cut.duration
        elif cut.start < value < cut.end:
            shifted -= value - cut.start
            break
    return round(max(0.0, shifted), 3)


def subtitle_events(transcripts: list[Segment], cuts: list[Interval], duration: float, *, max_chars: int) -> list[SubtitleEvent]:
    events: list[SubtitleEvent] = []
    for segment in transcripts:
        start = map_time(segment.start, cuts)
        end = min(map_time(segment.end, cuts), duration)
        if end <= start:
            continue
        chunks = split_text(segment.text, max_chars=max_chars)
        total = sum(max(1, len(chunk)) for chunk in chunks)
        cursor = start
        segment_duration = end - start
        for index, chunk in enumerate(chunks):
            weight = max(1, len(chunk))
            chunk_end = end if index == len(chunks) - 1 else cursor + segment_duration * weight / total
            events.append(SubtitleEvent(start=cursor, end=chunk_end, text=chunk))
            cursor = chunk_end
    return events


def build_ass(
    transcripts: list[Segment],
    cuts: list[Interval],
    duration: float,
    *,
    max_chars: int,
    base_font_size: int,
    font_name: str,
    subtitle_x: int,
    subtitle_y: int,
) -> tuple[str, int, int]:
    events = subtitle_events(transcripts, cuts, duration, max_chars=max_chars)
    shared_font_size = uniform_font_size(events, base_font_size)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Subtitle,{font_name},{shared_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "1,0,0,0,100,100,0,0,1,4,2,5,40,40,0,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for event in events:
        text = position_override(escape_ass(event.text), subtitle_x=subtitle_x, subtitle_y=subtitle_y)
        lines.append(f"Dialogue: 0,{timestamp(event.start)},{timestamp(event.end)},Subtitle,,0,0,0,,{text}")
    return "\n".join(lines) + "\n", shared_font_size, len(events)


def build_filter(keeps: list[Interval], subtitle_container_path: str, font_dir_container_path: str | None = None) -> str:
    parts: list[str] = []
    concat_inputs: list[str] = []
    for index, keep in enumerate(keeps):
        parts.append(f"[0:v]trim=start={keep.start:.6f}:end={keep.end:.6f},setpts=PTS-STARTPTS[v{index}]")
        parts.append(f"[0:a]atrim=start={keep.start:.6f}:end={keep.end:.6f},asetpts=PTS-STARTPTS[a{index}]")
        concat_inputs.append(f"[v{index}][a{index}]")
    parts.append(f"{''.join(concat_inputs)}concat=n={len(keeps)}:v=1:a=1[vcat][acat]")
    ass_filter = f"ass='{subtitle_container_path}'"
    if font_dir_container_path is not None:
        ass_filter += f":fontsdir='{font_dir_container_path}'"
    parts.append(f"[vcat]{ass_filter}[vout]")
    return ";\n".join(parts) + "\n"


def import_font_file(font_file: Path | None) -> tuple[Path | None, str | None]:
    if font_file is None:
        if FONT_DIR.exists() and any(path.suffix.lower() in {".ttf", ".ttc", ".otf"} for path in FONT_DIR.glob("*")):
            return None, "/app/storage/fonts"
        return None, None
    source = font_file if font_file.is_absolute() else ROOT / font_file
    if not source.exists():
        raise FileNotFoundError(f"Font file not found: {source}")
    if source.suffix.lower() not in {".ttf", ".ttc", ".otf"}:
        raise ValueError(f"Unsupported font file extension: {source.suffix}")

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    target = FONT_DIR / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target, "/app/storage/fonts"


def build_ffmpeg_command(
    source_container_path: str,
    filter_container_path: str,
    output_container_path: str,
    *,
    docker_service: str,
) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        docker_service,
        "ffmpeg",
        "-y",
        "-i",
        source_container_path,
        "-filter_complex_script",
        filter_container_path,
        "-map",
        "[vout]",
        "-map",
        "[acat]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        output_container_path,
    ]


def run_ffmpeg(
    source_container_path: str,
    filter_container_path: str,
    output_container_path: str,
    *,
    docker_service: str,
) -> None:
    command = build_ffmpeg_command(
        source_container_path,
        filter_container_path,
        output_container_path,
        docker_service=docker_service,
    )
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    args = parse_args()
    job_dir = ROOT / "storage" / "outputs" / args.job_id
    output_dir = job_dir / "breath_cut"
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = read_json(job_dir / "video_metadata.json")
    duration = float(metadata["duration"])
    transcripts = [
        Segment(float(item["start"]), float(item["end"]), normalize_text(str(item["text"])))
        for item in read_json(job_dir / "transcript_segments.json")
    ]
    silence_path = args.silence_json if args.silence_json is not None else job_dir / "silence_segments.json"
    if not silence_path.is_absolute():
        silence_path = ROOT / silence_path
    silences = [
        Interval(float(item["start"]), min(float(item["end"]), duration))
        for item in read_json(silence_path)
    ]
    protected_intervals = parse_intervals(args.protect_interval)
    soft_cut_intervals = parse_soft_cut_intervals(args.soft_cut_interval)
    cuts = cut_intervals(
        silences,
        transcripts,
        min_cut_silence=args.min_cut_silence,
        keep_silence=args.keep_silence,
        speech_margin=args.speech_margin,
        protected_intervals=protected_intervals,
        soft_cut_intervals=soft_cut_intervals,
    )
    new_duration = round(duration - sum(item.duration for item in cuts), 3)
    keeps = keep_intervals(duration, cuts)

    subtitle_path = output_dir / "short_01_breath_cut.ass"
    filter_path = output_dir / "filter_complex.txt"
    output_path = output_dir / args.output_name
    subtitle_container_path = f"/app/storage/outputs/{args.job_id}/breath_cut/{subtitle_path.name}"
    filter_container_path = f"/app/storage/outputs/{args.job_id}/breath_cut/{filter_path.name}"
    output_container_path = f"/app/storage/outputs/{args.job_id}/breath_cut/{output_path.name}"
    imported_font_path, font_dir_container_path = import_font_file(args.font_file)

    ass_document, subtitle_font_size, subtitle_event_count = build_ass(
        transcripts,
        cuts,
        new_duration,
        max_chars=args.max_chars,
        base_font_size=args.base_font_size,
        font_name=args.font_name,
        subtitle_x=args.subtitle_x,
        subtitle_y=args.subtitle_y,
    )
    subtitle_path.write_text(ass_document, encoding="utf-8")
    filter_path.write_text(build_filter(keeps, subtitle_container_path, font_dir_container_path), encoding="utf-8")
    (output_dir / "breath_cut_plan.json").write_text(
        json.dumps(
            {
                "source_duration": duration,
                "output_duration_estimate": new_duration,
                "cut_count": len(cuts),
                "cut_seconds": round(sum(item.duration for item in cuts), 3),
                "protected_intervals": [item.__dict__ for item in protected_intervals],
                "soft_cut_intervals": [item.__dict__ for item in soft_cut_intervals],
                "cuts": [item.__dict__ for item in cuts],
                "keeps": [item.__dict__ for item in keeps],
                "subtitle_font_name": args.font_name,
                "subtitle_font_file": str(imported_font_path) if imported_font_path is not None else None,
                "subtitle_font_dir": str(FONT_DIR) if font_dir_container_path is not None else None,
                "subtitle_font_size": subtitle_font_size,
                "subtitle_event_count": subtitle_event_count,
                "subtitle_position": {"x": args.subtitle_x, "y": args.subtitle_y},
                "subtitle_path": str(subtitle_path),
                "output_path": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.dry_run:
        print(output_dir / "breath_cut_plan.json")
        return

    run_ffmpeg(
        args.source_container_path,
        filter_container_path,
        output_container_path,
        docker_service=args.docker_service,
    )
    print(output_path)


if __name__ == "__main__":
    main()
