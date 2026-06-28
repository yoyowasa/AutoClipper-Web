import json
import struct
import wave
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from app.audio.silence_detect import SilenceSegment


AUDIO_FEATURES_FILENAME = "audio_features.json"


class AudioFeatures(BaseModel):
    duration: float = Field(ge=0)
    silence_ratio: float = Field(ge=0, le=1)
    speech_density: float = Field(ge=0, le=1)
    volume_peak: float = Field(ge=0, le=1)
    silent_seconds: float = Field(ge=0)
    speech_seconds: float = Field(ge=0)


def audio_features_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / AUDIO_FEATURES_FILENAME


def _intervals_from_segments(segments: Sequence[SilenceSegment]) -> list[tuple[float, float]]:
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


def silence_seconds(duration: float, segments: Sequence[SilenceSegment]) -> float:
    if duration <= 0:
        return 0.0

    total = 0.0
    for start, end in _intervals_from_segments(segments):
        clamped_start = min(max(start, 0.0), duration)
        clamped_end = min(max(end, 0.0), duration)
        if clamped_end > clamped_start:
            total += clamped_end - clamped_start
    return min(total, duration)


def _sample_peak(sample_width: int, raw: bytes) -> float:
    if not raw:
        return 0.0

    if sample_width == 1:
        values = (abs(byte - 128) for byte in raw)
        return max(values, default=0) / 128

    if sample_width == 2:
        count = len(raw) // 2
        values = struct.unpack(f"<{count}h", raw[: count * 2])
        return max((abs(value) for value in values), default=0) / 32768

    if sample_width == 3:
        max_value = 0
        for index in range(0, len(raw) - 2, 3):
            chunk = raw[index : index + 3]
            signed = int.from_bytes(chunk, byteorder="little", signed=True)
            max_value = max(max_value, abs(signed))
        return max_value / 8388608

    if sample_width == 4:
        count = len(raw) // 4
        values = struct.unpack(f"<{count}i", raw[: count * 4])
        return max((abs(value) for value in values), default=0) / 2147483648

    raise ValueError(f"unsupported sample width: {sample_width}")


def wav_volume_peak(wav_path: str | Path) -> float:
    with wave.open(str(wav_path), "rb") as wav_file:
        raw = wav_file.readframes(wav_file.getnframes())
        peak = _sample_peak(wav_file.getsampwidth(), raw)
    return min(max(peak, 0.0), 1.0)


def build_audio_features(
    duration: float,
    silence_segments: Sequence[SilenceSegment],
    volume_peak: float,
) -> AudioFeatures:
    clean_duration = max(0.0, duration)
    silent = silence_seconds(clean_duration, silence_segments)
    speech = max(0.0, clean_duration - silent)
    silence_ratio = silent / clean_duration if clean_duration > 0 else 0.0
    speech_density = speech / clean_duration if clean_duration > 0 else 0.0

    return AudioFeatures(
        duration=clean_duration,
        silence_ratio=silence_ratio,
        speech_density=speech_density,
        volume_peak=min(max(volume_peak, 0.0), 1.0),
        silent_seconds=silent,
        speech_seconds=speech,
    )


def compute_audio_features(
    wav_path: str | Path,
    duration: float,
    silence_segments: Sequence[SilenceSegment],
) -> AudioFeatures:
    return build_audio_features(
        duration=duration,
        silence_segments=silence_segments,
        volume_peak=wav_volume_peak(wav_path),
    )


def write_audio_features(features: AudioFeatures, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(features.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def compute_audio_features_to_json(
    wav_path: str | Path,
    output_dir: str | Path,
    duration: float,
    silence_segments: Sequence[SilenceSegment],
) -> Path:
    features = compute_audio_features(wav_path, duration, silence_segments)
    return write_audio_features(features, audio_features_output_path(output_dir))
