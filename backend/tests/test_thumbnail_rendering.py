from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

import app.render.render_thumbnail as thumbnail_renderer
from app.render.render_thumbnail import (
    DEFAULT_NORMAL_FONT_PATH,
    DEFAULT_NORMAL_TEMPLATE_PATH,
    _select_primary_face,
    build_extract_thumbnail_frame_command,
    render_normal_thumbnail,
    render_short_thumbnail,
)


def _synthetic_frame(path: Path, *, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, (42, 62, 76))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (size[0] // 2, 0, size[0] - 1, size[1] - 1),
        fill=(196, 128, 84),
    )
    image.save(path, format="JPEG", quality=95)


def test_primary_face_prefers_head_over_larger_lower_false_positive() -> None:
    selected = _select_primary_face(
        [
            (0.67, 0.29, 0.08, 0.15),
            (0.66, 0.51, 0.13, 0.24),
            (0.64, 0.75, 0.08, 0.15),
        ]
    )

    assert selected == (0.67, 0.29, 0.08, 0.15)


def test_portrait_frame_supports_a_closer_face_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Image.new("RGB", (320, 180))
    pixels = source.load()
    for y in range(source.height):
        for x in range(source.width):
            pixels[x, y] = (x % 256, y, (x + y) % 256)
    monkeypatch.setattr(
        thumbnail_renderer,
        "_primary_face",
        lambda _image: (0.68, 0.32, 0.08, 0.15),
    )
    frame_config = {
        "face_height_ratio": 0.25,
        "min_crop_height_ratio": 0.30,
        "max_crop_height_ratio": 0.90,
        "face_target_x": 0.68,
        "face_target_y": 0.34,
        "anchor_x": 1.0,
    }

    standard = thumbnail_renderer._portrait_frame(
        source,
        160,
        180,
        frame_config=frame_config,
        anchor_x=1.0,
        face_height_ratio=0.25,
    )
    close = thumbnail_renderer._portrait_frame(
        source,
        160,
        180,
        frame_config=frame_config,
        anchor_x=1.0,
        face_height_ratio=0.34,
    )

    assert ImageChops.difference(standard, close).getbbox() is not None


def test_build_extract_thumbnail_frame_command_does_not_resize() -> None:
    command = build_extract_thumbnail_frame_command(
        "input.mp4",
        "thumbnail.jpg",
        12.3456,
        ffmpeg_bin="ffmpeg-test",
    )

    assert command[0] == "ffmpeg-test"
    assert command[command.index("-ss") + 1] == "12.346"
    assert command[command.index("-c:v") + 1] == "mjpeg"
    assert "-vf" not in command
    assert "scale" not in " ".join(command)


def test_render_normal_thumbnail_uses_template_and_fits_long_japanese_text(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def command_runner(command: list[str]) -> None:
        commands.append(command)
        _synthetic_frame(Path(command[-1]), size=(1920, 1080))

    output = tmp_path / "normal.jpg"
    result = render_normal_thumbnail(
        "source.mp4",
        output,
        frame_time=18.25,
        eyebrow="儒烏風亭らでん切り抜き",
        title_first_line="高校で美術を学ぶ意味を",
        title_second_line="らでんが本気で語った結果",
        command_runner=command_runner,
    )

    assert DEFAULT_NORMAL_FONT_PATH.is_file()
    assert len(commands) == 1
    assert commands[0][commands[0].index("-ss") + 1] == "18.250"
    assert result.path == output
    assert result.kind == "normal"
    assert result.source_timestamp == 18.25
    assert (result.width, result.height) == (1280, 720)
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert thumbnail.size == (1280, 720)
        pixels = thumbnail.convert("RGB")
        yellow_pixels = sum(
            1
            for red, green, blue in pixels.crop((0, 180, 650, 620)).getdata()
            if red > 190 and green > 150 and blue < 130
        )
        with Image.open(DEFAULT_NORMAL_TEMPLATE_PATH.parent / "background.png") as base:
            reference_background = base.convert("RGB").resize(
                (1280, 720),
                Image.Resampling.LANCZOS,
            ).crop((900, 100, 1200, 650))
        subject_difference = ImageStat.Stat(
            ImageChops.difference(
                pixels.crop((900, 100, 1200, 650)),
                reference_background,
            )
        ).mean
    assert yellow_pixels > 300
    assert max(subject_difference) > 8


@pytest.mark.parametrize(
    ("eyebrow", "first_line", "second_line"),
    [
        ("", "", ""),
        ("見" * 40, "美" * 60, "学" * 60),
        ("", "", "二行目だけ表示"),
    ],
)
def test_render_normal_thumbnail_keeps_empty_semantics_and_never_fails_on_allowed_text(
    tmp_path: Path,
    eyebrow: str,
    first_line: str,
    second_line: str,
) -> None:
    def command_runner(command: list[str]) -> None:
        _synthetic_frame(Path(command[-1]), size=(1920, 1080))

    output = tmp_path / f"normal-{len(eyebrow)}-{len(first_line)}-{len(second_line)}.jpg"
    result = render_normal_thumbnail(
        "source.mp4",
        output,
        frame_time=3.5,
        eyebrow=eyebrow,
        title_first_line=first_line,
        title_second_line=second_line,
        command_runner=command_runner,
    )

    assert result.path == output
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert thumbnail.size == (1280, 720)


def test_render_short_thumbnail_extracts_hook_midpoint_at_source_resolution(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def command_runner(command: list[str]) -> None:
        commands.append(command)
        _synthetic_frame(Path(command[-1]), size=(1080, 1920))

    output = tmp_path / "short.jpg"
    result = render_short_thumbnail(
        "short.mp4",
        output,
        hook_start=0.4,
        hook_end=2.0,
        command_runner=command_runner,
    )

    assert commands[0][commands[0].index("-ss") + 1] == "1.200"
    assert result.kind == "short"
    assert result.source_timestamp == pytest.approx(1.2)
    assert (result.width, result.height) == (1080, 1920)
    with Image.open(output) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert thumbnail.size == (1080, 1920)


@pytest.mark.parametrize(
    ("start", "end"),
    [(-0.1, 1.0), (1.0, 1.0), (2.0, 1.0)],
)
def test_render_short_thumbnail_rejects_invalid_hook_range(
    tmp_path: Path,
    start: float,
    end: float,
) -> None:
    with pytest.raises(ValueError):
        render_short_thumbnail(
            "short.mp4",
            tmp_path / "short.jpg",
            hook_start=start,
            hook_end=end,
        )
