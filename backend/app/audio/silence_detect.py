import json
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field, model_validator


SILENCE_SEGMENTS_FILENAME = "silence_segments.json"
SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<start>-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(
    r"silence_end:\s*(?P<end>-?\d+(?:\.\d+)?).*?silence_duration:\s*(?P<duration>-?\d+(?:\.\d+)?)"
)


class SilenceSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "SilenceSegment":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


def silence_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / SILENCE_SEGMENTS_FILENAME


def build_silence_detect_command(
    input_path: str | Path,
    noise_db: int = -35,
    min_duration: float = 0.5,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-i",
        str(input_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f",
        "null",
        "-",
    ]


def _parse_float(value: str) -> float:
    return max(0.0, float(value))


def parse_silence_detect_log(log_text: str, audio_duration: float | None = None) -> list[SilenceSegment]:
    segments: list[SilenceSegment] = []
    current_start: float | None = None

    for line in log_text.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_start = _parse_float(start_match.group("start"))
            continue

        end_match = SILENCE_END_RE.search(line)
        if end_match and current_start is not None:
            end = _parse_float(end_match.group("end"))
            if end > current_start:
                segments.append(
                    SilenceSegment(
                        start=current_start,
                        end=end,
                        duration=end - current_start,
                    )
                )
            current_start = None

    if current_start is not None and audio_duration is not None and audio_duration > current_start:
        segments.append(
            SilenceSegment(
                start=current_start,
                end=float(audio_duration),
                duration=float(audio_duration) - current_start,
            )
        )

    return segments


def segments_to_jsonable(segments: Sequence[SilenceSegment]) -> list[dict[str, Any]]:
    return [segment.model_dump() for segment in segments]


def write_silence_segments(segments: Sequence[SilenceSegment], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(segments_to_jsonable(segments), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def detect_silence(
    input_path: str | Path,
    audio_duration: float | None = None,
    noise_db: int = -35,
    min_duration: float = 0.5,
    ffmpeg_bin: str = "ffmpeg",
) -> list[SilenceSegment]:
    command = build_silence_detect_command(
        input_path,
        noise_db=noise_db,
        min_duration=min_duration,
        ffmpeg_bin=ffmpeg_bin,
    )
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return parse_silence_detect_log(result.stderr, audio_duration=audio_duration)


def detect_silence_to_json(
    input_path: str | Path,
    output_dir: str | Path,
    audio_duration: float | None = None,
    noise_db: int = -35,
    min_duration: float = 0.5,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    segments = detect_silence(
        input_path,
        audio_duration=audio_duration,
        noise_db=noise_db,
        min_duration=min_duration,
        ffmpeg_bin=ffmpeg_bin,
    )
    return write_silence_segments(segments, silence_output_path(output_dir))
