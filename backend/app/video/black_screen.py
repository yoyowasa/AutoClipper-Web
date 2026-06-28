import json
import re
import subprocess
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field, model_validator


VISUAL_QUALITY_FILENAME = "visual_quality.json"
BLACK_SEGMENT_RE = re.compile(
    r"black_start:\s*(?P<start>-?\d+(?:\.\d+)?)\s+"
    r"black_end:\s*(?P<end>-?\d+(?:\.\d+)?)\s+"
    r"black_duration:\s*(?P<duration>-?\d+(?:\.\d+)?)"
)


class BlackScreenSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "BlackScreenSegment":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class VisualQuality(BaseModel):
    duration: float = Field(ge=0)
    black_screen_ratio: float = Field(ge=0, le=1)
    usable_ratio: float = Field(ge=0, le=1)
    black_seconds: float = Field(ge=0)
    black_segments: list[BlackScreenSegment]


def visual_quality_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / VISUAL_QUALITY_FILENAME


def build_blackdetect_command(
    input_path: str | Path,
    min_duration: float = 0.5,
    pixel_threshold: float = 0.10,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-i",
        str(input_path),
        "-vf",
        f"blackdetect=d={min_duration}:pix_th={pixel_threshold}",
        "-an",
        "-f",
        "null",
        "-",
    ]


def _parse_float(value: str) -> float:
    return max(0.0, float(value))


def parse_blackdetect_log(log_text: str) -> list[BlackScreenSegment]:
    segments: list[BlackScreenSegment] = []
    for match in BLACK_SEGMENT_RE.finditer(log_text):
        start = _parse_float(match.group("start"))
        end = _parse_float(match.group("end"))
        if end > start:
            segments.append(
                BlackScreenSegment(
                    start=start,
                    end=end,
                    duration=end - start,
                )
            )
    return segments


def _merged_intervals(segments: Sequence[BlackScreenSegment]) -> list[tuple[float, float]]:
    intervals = sorted(
        (segment.start, segment.end)
        for segment in segments
        if segment.end > segment.start
    )
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def black_seconds(duration: float, segments: Sequence[BlackScreenSegment]) -> float:
    if duration <= 0:
        return 0.0
    total = 0.0
    for start, end in _merged_intervals(segments):
        clamped_start = min(max(start, 0.0), duration)
        clamped_end = min(max(end, 0.0), duration)
        if clamped_end > clamped_start:
            total += clamped_end - clamped_start
    return min(total, duration)


def build_visual_quality(
    duration: float,
    black_segments: Sequence[BlackScreenSegment],
) -> VisualQuality:
    clean_duration = max(0.0, duration)
    black = black_seconds(clean_duration, black_segments)
    ratio = black / clean_duration if clean_duration > 0 else 0.0
    return VisualQuality(
        duration=clean_duration,
        black_screen_ratio=ratio,
        usable_ratio=1.0 - ratio if clean_duration > 0 else 0.0,
        black_seconds=black,
        black_segments=list(black_segments),
    )


def write_visual_quality(visual_quality: VisualQuality, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(visual_quality.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def detect_black_screen(
    input_path: str | Path,
    min_duration: float = 0.5,
    pixel_threshold: float = 0.10,
    ffmpeg_bin: str = "ffmpeg",
) -> list[BlackScreenSegment]:
    command = build_blackdetect_command(
        input_path,
        min_duration=min_duration,
        pixel_threshold=pixel_threshold,
        ffmpeg_bin=ffmpeg_bin,
    )
    result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return parse_blackdetect_log(result.stderr)


def detect_black_screen_to_json(
    input_path: str | Path,
    output_dir: str | Path,
    duration: float,
    min_duration: float = 0.5,
    pixel_threshold: float = 0.10,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    segments = detect_black_screen(
        input_path,
        min_duration=min_duration,
        pixel_threshold=pixel_threshold,
        ffmpeg_bin=ffmpeg_bin,
    )
    visual_quality = build_visual_quality(duration, segments)
    return write_visual_quality(visual_quality, visual_quality_output_path(output_dir))
