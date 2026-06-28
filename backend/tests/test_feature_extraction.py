import json
import struct
import wave
from pathlib import Path

import pytest

from app.audio.silence_detect import (
    SilenceSegment,
    build_silence_detect_command,
    parse_silence_detect_log,
    silence_output_path,
    write_silence_segments,
)
from app.audio.volume_features import (
    build_audio_features,
    compute_audio_features,
    silence_seconds,
    write_audio_features,
)
from app.video.black_screen import (
    BlackScreenSegment,
    build_blackdetect_command,
    build_visual_quality,
    parse_blackdetect_log,
    write_visual_quality,
)
from app.video.scene_detect import (
    SceneSegment,
    scene_output_path,
    scene_segments_from_boundaries,
    write_scene_segments,
)


def test_scene_segments_from_boundaries_sorts_deduplicates_and_clamps() -> None:
    segments = scene_segments_from_boundaries([4.0, -1.0, 2.0, 2.0, 12.0], duration=6.0)

    assert segments == [
        SceneSegment(start=0.0, end=2.0),
        SceneSegment(start=2.0, end=4.0),
        SceneSegment(start=4.0, end=6.0),
    ]


def test_scene_segments_empty_for_missing_or_zero_duration() -> None:
    assert scene_segments_from_boundaries([1.0], duration=None) == []
    assert scene_segments_from_boundaries([1.0], duration=0.0) == []


def test_write_scene_segments_json(tmp_path: Path) -> None:
    path = write_scene_segments(
        [SceneSegment(start=0.0, end=1.5)],
        scene_output_path(tmp_path),
    )

    assert path.name == "scene_segments.json"
    assert json.loads(path.read_text(encoding="utf-8")) == [{"start": 0.0, "end": 1.5}]


def test_build_silence_detect_command() -> None:
    assert build_silence_detect_command("audio.wav", noise_db=-40, min_duration=0.25) == [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        "audio.wav",
        "-af",
        "silencedetect=noise=-40dB:d=0.25",
        "-f",
        "null",
        "-",
    ]


def test_parse_silence_detect_log_with_open_ended_interval() -> None:
    log_text = "\n".join(
        [
            "[silencedetect] silence_start: 0.5",
            "[silencedetect] silence_end: 1.5 | silence_duration: 1.0",
            "[silencedetect] silence_start: 2.0",
        ]
    )

    segments = parse_silence_detect_log(log_text, audio_duration=3.0)

    assert segments == [
        SilenceSegment(start=0.5, end=1.5, duration=1.0),
        SilenceSegment(start=2.0, end=3.0, duration=1.0),
    ]


def test_parse_silence_detect_log_ignores_end_without_start() -> None:
    log_text = "[silencedetect] silence_end: 1.5 | silence_duration: 1.0"

    assert parse_silence_detect_log(log_text, audio_duration=3.0) == []


def test_write_silence_segments_json(tmp_path: Path) -> None:
    path = write_silence_segments(
        [SilenceSegment(start=0.5, end=1.5, duration=1.0)],
        silence_output_path(tmp_path),
    )

    assert path.name == "silence_segments.json"
    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"start": 0.5, "end": 1.5, "duration": 1.0}
    ]


def test_audio_features_merge_overlapping_silence_and_clamp_to_duration() -> None:
    segments = [
        SilenceSegment(start=0.0, end=3.0, duration=3.0),
        SilenceSegment(start=2.0, end=5.0, duration=3.0),
        SilenceSegment(start=8.0, end=12.0, duration=4.0),
    ]

    features = build_audio_features(duration=10.0, silence_segments=segments, volume_peak=1.2)

    assert silence_seconds(10.0, segments) == 7.0
    assert features.silence_ratio == pytest.approx(0.7)
    assert features.speech_density == pytest.approx(0.3)
    assert features.volume_peak == 1.0
    assert features.silent_seconds == 7.0
    assert features.speech_seconds == 3.0


def test_audio_features_zero_duration_returns_zero_ratios() -> None:
    features = build_audio_features(
        duration=0.0,
        silence_segments=[SilenceSegment(start=0.0, end=1.0, duration=1.0)],
        volume_peak=-1.0,
    )

    assert features.silence_ratio == 0.0
    assert features.speech_density == 0.0
    assert features.volume_peak == 0.0


def test_compute_audio_features_reads_wav_peak(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(struct.pack("<hhh", 0, 8192, -8192))

    features = compute_audio_features(wav_path, duration=1.0, silence_segments=[])

    assert features.volume_peak == pytest.approx(0.25)
    assert features.silence_ratio == 0.0
    assert features.speech_density == 1.0


def test_write_audio_features_json(tmp_path: Path) -> None:
    features = build_audio_features(duration=2.0, silence_segments=[], volume_peak=0.5)
    path = write_audio_features(features, tmp_path / "audio_features.json")

    assert path.name == "audio_features.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "duration": 2.0,
        "silence_ratio": 0.0,
        "speech_density": 1.0,
        "volume_peak": 0.5,
        "silent_seconds": 0.0,
        "speech_seconds": 2.0,
    }


def test_build_blackdetect_command() -> None:
    assert build_blackdetect_command("input.mp4", min_duration=0.25, pixel_threshold=0.2) == [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        "input.mp4",
        "-vf",
        "blackdetect=d=0.25:pix_th=0.2",
        "-an",
        "-f",
        "null",
        "-",
    ]


def test_parse_blackdetect_log() -> None:
    log_text = "\n".join(
        [
            "[blackdetect] black_start:0 black_end:1.5 black_duration:1.5",
            "[blackdetect] black_start:3.25 black_end:4 black_duration:0.75",
        ]
    )

    segments = parse_blackdetect_log(log_text)

    assert segments == [
        BlackScreenSegment(start=0.0, end=1.5, duration=1.5),
        BlackScreenSegment(start=3.25, end=4.0, duration=0.75),
    ]


def test_visual_quality_merges_overlapping_black_segments() -> None:
    visual_quality = build_visual_quality(
        duration=10.0,
        black_segments=[
            BlackScreenSegment(start=0.0, end=2.0, duration=2.0),
            BlackScreenSegment(start=1.0, end=4.0, duration=3.0),
            BlackScreenSegment(start=9.0, end=12.0, duration=3.0),
        ],
    )

    assert visual_quality.black_seconds == 5.0
    assert visual_quality.black_screen_ratio == pytest.approx(0.5)
    assert visual_quality.usable_ratio == pytest.approx(0.5)


def test_visual_quality_zero_duration() -> None:
    visual_quality = build_visual_quality(
        duration=0.0,
        black_segments=[BlackScreenSegment(start=0.0, end=1.0, duration=1.0)],
    )

    assert visual_quality.black_screen_ratio == 0.0
    assert visual_quality.usable_ratio == 0.0
    assert visual_quality.black_seconds == 0.0


def test_write_visual_quality_json(tmp_path: Path) -> None:
    visual_quality = build_visual_quality(
        duration=2.0,
        black_segments=[BlackScreenSegment(start=0.0, end=0.5, duration=0.5)],
    )
    path = write_visual_quality(visual_quality, tmp_path / "visual_quality.json")

    assert path.name == "visual_quality.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["black_screen_ratio"] == 0.25
    assert payload["usable_ratio"] == 0.75
    assert payload["black_segments"] == [{"start": 0.0, "end": 0.5, "duration": 0.5}]
