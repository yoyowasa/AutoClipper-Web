import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.extract import build_extract_audio_command, extract_mono_wav
from app.render.render_normal import build_render_normal_command, render_normal_clip
from app.render.render_short import (
    build_center_crop_filter,
    build_render_short_command,
    render_short_center_crop,
)
from app.video.probe import (
    VideoMetadata,
    build_ffprobe_command,
    parse_ffprobe_output,
    probe_metadata,
)


def test_build_ffprobe_command() -> None:
    assert build_ffprobe_command("input.mp4") == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "input.mp4",
    ]


def test_parse_ffprobe_output() -> None:
    output = json.dumps(
        {
            "format": {"duration": "12.345"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                },
                {"codec_type": "audio"},
            ],
        }
    )

    metadata = parse_ffprobe_output(output)

    assert metadata == VideoMetadata(
        duration=12.345,
        width=1920,
        height=1080,
        fps=pytest.approx(29.97002997),
        has_audio=True,
    )


def test_build_extract_audio_command() -> None:
    assert build_extract_audio_command("input.mp4", "audio.wav") == [
        "ffmpeg",
        "-y",
        "-i",
        "input.mp4",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "audio.wav",
    ]


def test_build_render_normal_command_with_subtitles_and_loudnorm() -> None:
    command = build_render_normal_command(
        "input.mp4",
        "normal.mp4",
        start=1.25,
        end=4.5,
        subtitle_path="subtitles.ass",
        normalize_audio=True,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-ss",
        "1.250",
        "-i",
        "input.mp4",
        "-t",
        "3.250",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        "ass='subtitles.ass'",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "normal.mp4",
    ]


def test_build_render_short_command_center_crop() -> None:
    command = build_render_short_command(
        "input.mp4",
        "short.mp4",
        start=0,
        end=30,
        subtitle_path="subtitles.ass",
        normalize_audio=True,
    )

    assert "-vf" in command
    video_filter = command[command.index("-vf") + 1]
    assert video_filter == (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "ass='subtitles.ass'"
    )
    assert "-af" in command
    assert command[command.index("-af") + 1] == "loudnorm=I=-16:TP=-1.5:LRA=11"
    assert command[-1] == "short.mp4"


def test_build_center_crop_filter_without_subtitles() -> None:
    assert build_center_crop_filter() == (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    )


def test_render_commands_reject_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="end must be greater than start"):
        build_render_normal_command("input.mp4", "out.mp4", start=10, end=10)

    with pytest.raises(ValueError, match="end must be greater than start"):
        build_render_short_command("input.mp4", "out.mp4", start=10, end=9)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for the tiny fixture integration test",
)
def test_tiny_fixture_video_probe_extract_and_render(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.mp4"
    audio_path = tmp_path / "audio.wav"
    normal_path = tmp_path / "normal.mp4"
    short_path = tmp_path / "short.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=16000",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(input_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    metadata = probe_metadata(input_path)
    assert metadata.width == 160
    assert metadata.height == 90
    assert metadata.has_audio is True
    assert metadata.duration is not None
    assert metadata.duration > 0

    extract_mono_wav(input_path, audio_path)
    render_normal_clip(input_path, normal_path, start=0, end=0.5)
    render_short_center_crop(input_path, short_path, start=0, end=0.5)

    assert audio_path.is_file()
    assert audio_path.stat().st_size > 0
    assert normal_path.is_file()
    assert normal_path.stat().st_size > 0
    assert short_path.is_file()
    assert short_path.stat().st_size > 0
