import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.extract import AudioExtractionError, build_extract_audio_command, extract_mono_wav
from app.render.filters import ass_filter
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
                    "duration": "12.300",
                    "avg_frame_rate": "30000/1001",
                },
                {"codec_type": "audio", "duration": "12.320"},
            ],
        }
    )

    metadata = parse_ffprobe_output(output)

    assert metadata == VideoMetadata(
        duration=12.3,
        width=1920,
        height=1080,
        fps=pytest.approx(29.97002997),
        has_audio=True,
        video_stream_duration=12.3,
        audio_stream_duration=12.32,
        container_duration=12.345,
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


def test_extract_audio_reports_corrupt_media_without_raw_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "partial.wav"
    output_path.write_bytes(b"partial")

    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(
            234,
            ["ffmpeg", "-i", "secret-local-path.mp4"],
            stderr="Error submitting packet to decoder: Invalid data found when processing input",
        )

    monkeypatch.setattr(subprocess, "run", fail_run)

    with pytest.raises(AudioExtractionError, match="破損または不完全"):
        extract_mono_wav("input.mp4", output_path)

    assert not output_path.exists()


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


def test_build_render_normal_command_prepends_hook_scene() -> None:
    command = build_render_normal_command(
        "input.mp4",
        "normal.mp4",
        start=10.0,
        end=20.0,
        subtitle_path="subtitles.ass",
        normalize_audio=True,
        hook_scene_start=14.0,
        hook_scene_end=16.0,
    )

    assert command.count("input.mp4") == 2
    assert command[command.index("-filter_complex") + 1] == (
        "[0:v:0]setpts=PTS-STARTPTS[hook_v];"
        "[1:v:0]setpts=PTS-STARTPTS[main_v];"
        "[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[hook_a];"
        "[1:a:0]aresample=48000,asetpts=PTS-STARTPTS[main_a];"
        "[hook_v][hook_a][main_v][main_a]concat=n=2:v=1:a=1[concat_v][concat_a];"
        "[concat_v]ass='subtitles.ass'[video_out];"
        "[concat_a]loudnorm=I=-16:TP=-1.5:LRA=11[audio_out]"
    )
    assert command[command.index("-map") + 1] == "[video_out]"
    assert "[audio_out]" in command


def test_ass_filter_uses_configured_fonts_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASS_FONTS_DIR", "/app/fonts")

    assert ass_filter("subtitles.ass") == "ass='subtitles.ass':fontsdir='/app/fonts'"


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
