from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont


THUMBNAIL_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "thumbnail_templates"
    / "raden_normal_v1"
)
DEFAULT_NORMAL_TEMPLATE_PATH = THUMBNAIL_TEMPLATE_DIR / "template.json"
DEFAULT_NORMAL_FONT_PATH = THUMBNAIL_TEMPLATE_DIR / "NotoSansJP-Black.ttf"

ThumbnailKind = Literal["normal", "short"]
ThumbnailCommandRunner = Callable[[list[str]], None]


@dataclass(frozen=True)
class ThumbnailRenderResult:
    path: Path
    kind: ThumbnailKind
    source_timestamp: float
    width: int
    height: int


@dataclass(frozen=True)
class _TextFit:
    font: ImageFont.FreeTypeFont
    stroke_width: int
    width: int
    height: int


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _validate_jpeg_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.suffix.lower() not in {".jpg", ".jpeg"}:
        raise ValueError("thumbnail output must use a .jpg or .jpeg extension")
    return resolved


def _validate_timestamp(timestamp: float) -> float:
    value = float(timestamp)
    if value < 0:
        raise ValueError("frame timestamp must be non-negative")
    return value


def build_extract_thumbnail_frame_command(
    input_path: str | Path,
    output_path: str | Path,
    timestamp: float,
    *,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Build a single-frame JPEG extraction command without scaling."""
    output = _validate_jpeg_path(output_path)
    frame_timestamp = _validate_timestamp(timestamp)
    return [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{frame_timestamp:.3f}",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-c:v",
        "mjpeg",
        "-q:v",
        "2",
        "-update",
        "1",
        "-f",
        "image2",
        str(output),
    ]


def extract_thumbnail_frame(
    input_path: str | Path,
    output_path: str | Path,
    timestamp: float,
    *,
    ffmpeg_bin: str = "ffmpeg",
    command_runner: ThumbnailCommandRunner = _run_command,
) -> Path:
    """Extract one JPEG at ``timestamp`` seconds in the supplied input video."""
    output = _validate_jpeg_path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    command_runner(
        build_extract_thumbnail_frame_command(
            input_path,
            output,
            timestamp,
            ffmpeg_bin=ffmpeg_bin,
        )
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("thumbnail frame extraction produced no JPEG")
    return output


def _load_template(template_path: str | Path) -> dict[str, Any]:
    path = Path(template_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("version", 0)) != 1:
        raise ValueError("unsupported normal thumbnail template version")
    return data


def _hex_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    normalized = value.removeprefix("#")
    if len(normalized) != 6:
        raise ValueError(f"invalid template color: {value}")
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
        alpha,
    )


def _cover_frame(
    image: Image.Image,
    width: int,
    height: int,
    *,
    anchor_x: float,
) -> Image.Image:
    source = image.convert("RGB")
    target_ratio = width / height
    source_ratio = source.width / source.height
    if source_ratio > target_ratio:
        crop_width = max(1, round(source.height * target_ratio))
        available = source.width - crop_width
        left = round(available * min(1.0, max(0.0, anchor_x)))
        source = source.crop((left, 0, left + crop_width, source.height))
    elif source_ratio < target_ratio:
        crop_height = max(1, round(source.width / target_ratio))
        top = max(0, (source.height - crop_height) // 2)
        source = source.crop((0, top, source.width, top + crop_height))
    return source.resize((width, height), Image.Resampling.LANCZOS)


def _draw_asanoha_pattern(
    image: Image.Image,
    color: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    cell_width = 96
    cell_height = 84
    for row, y in enumerate(range(-cell_height, image.height + cell_height, cell_height)):
        offset = cell_width // 2 if row % 2 else 0
        for x in range(-cell_width + offset, image.width + cell_width, cell_width):
            center = (x, y)
            points = (
                (x - cell_width // 2, y),
                (x - cell_width // 4, y - cell_height // 2),
                (x + cell_width // 4, y - cell_height // 2),
                (x + cell_width // 2, y),
                (x + cell_width // 4, y + cell_height // 2),
                (x - cell_width // 4, y + cell_height // 2),
            )
            draw.line((*points, points[0]), fill=color, width=2, joint="curve")
            for point in points:
                draw.line((center, point), fill=color, width=1)


def _fit_text(
    text: str,
    font_path: Path,
    *,
    max_width: int,
    max_size: int,
    min_size: int,
) -> _TextFit:
    normalized = text.strip()
    if not normalized:
        raise ValueError("thumbnail text must not be empty")
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    smallest_fit: _TextFit | None = None
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size=size)
        stroke_width = max(2, round(size * 0.075))
        left, top, right, bottom = measure.textbbox(
            (0, 0),
            normalized,
            font=font,
            stroke_width=stroke_width * 2,
        )
        width = right - left
        current_fit = _TextFit(
            font=font,
            stroke_width=stroke_width,
            width=width,
            height=bottom - top,
        )
        smallest_fit = current_fit
        if width <= max_width:
            return current_fit
    if smallest_fit is None:
        raise ValueError("thumbnail font size range is invalid")
    return smallest_fit


def _draw_layered_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    fit: _TextFit,
    *,
    fill: tuple[int, int, int, int],
    inner_stroke: tuple[int, int, int, int],
    outer_stroke: tuple[int, int, int, int],
) -> None:
    outer_width = fit.stroke_width * 2
    draw.text(
        position,
        text,
        font=fit.font,
        fill=outer_stroke,
        stroke_width=outer_width,
        stroke_fill=outer_stroke,
    )
    draw.text(
        position,
        text,
        font=fit.font,
        fill=fill,
        stroke_width=fit.stroke_width,
        stroke_fill=inner_stroke,
    )


def _title_layer(
    first_line: str,
    second_line: str,
    *,
    font_path: Path,
    max_width: int,
    max_size: int,
    min_size: int,
    line_gap: int,
    colors: dict[str, str],
    rotation_degrees: float,
) -> Image.Image:
    lines = [
        (first_line.strip(), colors["title_first"]),
        (second_line.strip(), colors["title_second"]),
    ]
    visible_lines = [(text, color) for text, color in lines if text]
    if not visible_lines:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    fitted_lines = [
        (
            text,
            color,
            _fit_text(
                text,
                font_path,
                max_width=max_width,
                max_size=max_size,
                min_size=min_size,
            ),
        )
        for text, color in visible_lines
    ]
    padding = 24
    line_height = max(fit.height for _, _, fit in fitted_lines)
    natural_width = max(max_width, *(fit.width for _, _, fit in fitted_lines))
    layer = Image.new(
        "RGBA",
        (
            natural_width + padding * 2,
            line_height * len(fitted_lines)
            + line_gap * max(0, len(fitted_lines) - 1)
            + padding * 2,
        ),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(layer, "RGBA")
    inner = _hex_rgba(colors["title_inner_stroke"])
    outer = _hex_rgba(colors["title_outer_stroke"])
    for index, (text, color, fit) in enumerate(fitted_lines):
        _draw_layered_text(
            draw,
            (padding, padding + index * (line_height + line_gap)),
            text,
            fit,
            fill=_hex_rgba(color),
            inner_stroke=inner,
            outer_stroke=outer,
        )
    if natural_width > max_width:
        layer = layer.resize(
            (max_width + padding * 2, layer.height),
            Image.Resampling.LANCZOS,
        )
    return layer.rotate(rotation_degrees, resample=Image.Resampling.BICUBIC, expand=True)


def _compose_normal_thumbnail(
    frame: Image.Image,
    *,
    eyebrow: str,
    title_first_line: str,
    title_second_line: str,
    template: dict[str, Any],
    font_path: Path,
) -> Image.Image:
    canvas_config = template["canvas"]
    frame_config = template["frame"]
    text_config = template["text"]
    colors = template["colors"]
    width = int(canvas_config["width"])
    height = int(canvas_config["height"])
    canvas = Image.new("RGBA", (width, height), _hex_rgba(colors["background"]))
    _draw_asanoha_pattern(canvas, _hex_rgba(colors["pattern"], 132))

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        (13, 13, width - 14, height - 14),
        radius=24,
        outline=_hex_rgba(colors["gold"]),
        width=7,
    )
    draw.rounded_rectangle(
        (26, 26, width - 27, height - 27),
        radius=18,
        outline=_hex_rgba(colors["gold_light"], 145),
        width=2,
    )

    frame_x = int(frame_config["x"])
    frame_y = int(frame_config["y"])
    frame_width = int(frame_config["width"])
    frame_height = int(frame_config["height"])
    fitted_frame = _cover_frame(
        frame,
        frame_width,
        frame_height,
        anchor_x=float(frame_config["anchor_x"]),
    ).convert("RGBA")
    canvas.alpha_composite(fitted_frame, (frame_x, frame_y))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        (frame_x - 3, frame_y - 3, frame_x + frame_width + 2, frame_y + frame_height + 2),
        radius=12,
        outline=_hex_rgba(colors["gold"]),
        width=5,
    )

    blend_width = min(170, frame_width)
    blend = Image.new("RGBA", (blend_width, frame_height), (0, 0, 0, 0))
    blend_pixels = blend.load()
    background = _hex_rgba(colors["background"])
    for x in range(blend_width):
        alpha = round(255 * (1 - x / max(1, blend_width - 1)) ** 1.7)
        for y in range(frame_height):
            blend_pixels[x, y] = (*background[:3], alpha)
    canvas.alpha_composite(blend, (frame_x, frame_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    accent = _hex_rgba(colors["accent"], 190)
    draw.line((34, 532, 616, 278), fill=accent, width=28)
    draw.line((72, 562, 604, 330), fill=_hex_rgba(colors["accent"], 75), width=13)

    if eyebrow.strip():
        eyebrow_fit = _fit_text(
            eyebrow,
            font_path,
            max_width=int(text_config["eyebrow_max_width"]),
            max_size=int(text_config["eyebrow_max_size"]),
            min_size=18,
        )
        draw.text(
            (int(text_config["eyebrow_x"]), int(text_config["eyebrow_y"])),
            eyebrow.strip(),
            font=eyebrow_fit.font,
            fill=_hex_rgba(colors["eyebrow"]),
            stroke_width=max(1, eyebrow_fit.stroke_width // 2),
            stroke_fill=_hex_rgba(colors["background"]),
        )

    if title_first_line.strip() or title_second_line.strip():
        title = _title_layer(
            title_first_line,
            title_second_line,
            font_path=font_path,
            max_width=int(text_config["title_max_width"]),
            max_size=int(text_config["title_max_size"]),
            min_size=int(text_config["title_min_size"]),
            line_gap=int(text_config["line_gap"]),
            colors=colors,
            rotation_degrees=float(text_config["rotation_degrees"]),
        )
        canvas.alpha_composite(
            title,
            (int(text_config["title_x"]), int(text_config["title_y"])),
        )
    return canvas.convert("RGB")


def render_normal_thumbnail(
    input_path: str | Path,
    output_path: str | Path,
    *,
    frame_time: float,
    eyebrow: str,
    title_first_line: str,
    title_second_line: str,
    template_path: str | Path = DEFAULT_NORMAL_TEMPLATE_PATH,
    font_path: str | Path | None = None,
    ffmpeg_bin: str = "ffmpeg",
    command_runner: ThumbnailCommandRunner = _run_command,
) -> ThumbnailRenderResult:
    """Render a 1280x720 normal thumbnail.

    ``frame_time`` is relative to ``input_path``. When ``input_path`` is the
    original source video, callers must pass the absolute source-video second.
    """
    output = _validate_jpeg_path(output_path)
    timestamp = _validate_timestamp(frame_time)
    template = _load_template(template_path)
    selected_font = Path(font_path) if font_path is not None else Path(template_path).parent / template["font"]
    if not selected_font.is_file():
        raise FileNotFoundError(f"normal thumbnail font not found: {selected_font}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autoclipper-thumbnail-") as temp_dir:
        frame_path = Path(temp_dir) / "frame.jpg"
        extract_thumbnail_frame(
            input_path,
            frame_path,
            timestamp,
            ffmpeg_bin=ffmpeg_bin,
            command_runner=command_runner,
        )
        with Image.open(frame_path) as source_frame:
            composed = _compose_normal_thumbnail(
                source_frame,
                eyebrow=eyebrow,
                title_first_line=title_first_line,
                title_second_line=title_second_line,
                template=template,
                font_path=selected_font,
            )
            composed.save(output, format="JPEG", quality=94, optimize=True, subsampling=0)
    return ThumbnailRenderResult(
        path=output,
        kind="normal",
        source_timestamp=timestamp,
        width=int(template["canvas"]["width"]),
        height=int(template["canvas"]["height"]),
    )


def render_short_thumbnail(
    input_path: str | Path,
    output_path: str | Path,
    *,
    hook_start: float,
    hook_end: float,
    ffmpeg_bin: str = "ffmpeg",
    command_runner: ThumbnailCommandRunner = _run_command,
) -> ThumbnailRenderResult:
    """Extract the midpoint of a hook interval from a completed Short as JPEG.

    ``hook_start`` and ``hook_end`` are seconds in the supplied completed Short.
    The extracted JPEG keeps the video's original frame dimensions.
    """
    start = _validate_timestamp(hook_start)
    end = _validate_timestamp(hook_end)
    if end <= start:
        raise ValueError("hook_end must be greater than hook_start")
    timestamp = start + (end - start) / 2
    output = extract_thumbnail_frame(
        input_path,
        output_path,
        timestamp,
        ffmpeg_bin=ffmpeg_bin,
        command_runner=command_runner,
    )
    with Image.open(output) as thumbnail:
        if thumbnail.format != "JPEG":
            raise RuntimeError("short thumbnail extraction did not produce a JPEG")
        width, height = thumbnail.size
    return ThumbnailRenderResult(
        path=output,
        kind="short",
        source_timestamp=timestamp,
        width=width,
        height=height,
    )
