import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoMetadata:
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool


def build_ffprobe_command(input_path: str | Path, ffprobe_bin: str = "ffprobe") -> list[str]:
    return [
        ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_fps(value: Any) -> float | None:
    if not value or value == "0/0":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split("/", maxsplit=1)
    if len(parts) == 1:
        return _parse_float(parts[0])
    numerator = _parse_float(parts[0])
    denominator = _parse_float(parts[1])
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def parse_ffprobe_output(output: str) -> VideoMetadata:
    payload = json.loads(output)
    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        {},
    )
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    duration = _parse_float(video_stream.get("duration"))
    if duration is None:
        duration = _parse_float(payload.get("format", {}).get("duration"))

    fps = _parse_fps(video_stream.get("avg_frame_rate"))
    if fps is None:
        fps = _parse_fps(video_stream.get("r_frame_rate"))

    return VideoMetadata(
        duration=duration,
        width=_parse_int(video_stream.get("width")),
        height=_parse_int(video_stream.get("height")),
        fps=fps,
        has_audio=has_audio,
    )


def probe_metadata(input_path: str | Path, ffprobe_bin: str = "ffprobe") -> VideoMetadata:
    command = build_ffprobe_command(input_path, ffprobe_bin=ffprobe_bin)
    result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return parse_ffprobe_output(result.stdout)
