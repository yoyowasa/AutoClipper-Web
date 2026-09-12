from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont

from app.thumbnail_style import NormalThumbnailStyle
from app.short_banners import banner_asset_path


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


def _select_primary_face(
    faces: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float] | None:
    usable = [
        face
        for face in faces
        if face[0] >= 0.46
        and 0.20 <= face[1] <= 0.72
        and face[2] >= 0.04
        and face[3] >= 0.07
    ]
    if not usable:
        return None
    return min(usable, key=lambda face: (face[1], -(face[2] * face[3])))


def _primary_face(image: Image.Image) -> tuple[float, float, float, float] | None:
    """Detect the upper-most usable face in the right half of one source frame."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    detector = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    if detector.empty():
        return None
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(36, 36),
    )
    height, width = gray.shape[:2]
    normalized_faces: list[tuple[float, float, float, float]] = []
    for x, y, face_width, face_height in faces:
        center_x = (float(x) + float(face_width) / 2) / width
        center_y = (float(y) + float(face_height) / 2) / height
        normalized_faces.append(
            (
                center_x,
                center_y,
                float(face_width) / width,
                float(face_height) / height,
            )
        )
    return _select_primary_face(normalized_faces)


def _portrait_frame(
    image: Image.Image,
    width: int,
    height: int,
    *,
    frame_config: dict[str, Any],
    anchor_x: float,
    face_height_ratio: float | None = None,
) -> Image.Image:
    source = image.convert("RGB")
    face = _primary_face(source)
    if face is None:
        crop_height = source.height * float(
            frame_config.get("fallback_crop_height_ratio", 0.67)
        )
        crop_width = crop_height * width / height
        if crop_width > source.width:
            crop_width = float(source.width)
            crop_height = crop_width * height / width
        target_x = min(0.9, max(0.1, float(frame_config.get("face_target_x", 0.68))))
        target_y = min(0.75, max(0.1, float(frame_config.get("face_target_y", 0.34))))
        fallback_center_x = float(frame_config.get("fallback_center_x", 0.82)) + (
            anchor_x - float(frame_config.get("anchor_x", 1.0))
        ) * 0.25
        fallback_center_x = min(0.95, max(0.05, fallback_center_x))
        fallback_center_y = float(frame_config.get("fallback_center_y", 0.68))
        left = fallback_center_x * source.width - crop_width * target_x
        top = fallback_center_y * source.height - crop_height * target_y
        left = min(max(0.0, left), max(0.0, source.width - crop_width))
        top = min(max(0.0, top), max(0.0, source.height - crop_height))
        crop = source.crop(
            (
                round(left),
                round(top),
                round(left + crop_width),
                round(top + crop_height),
            )
        )
        return crop.resize((width, height), Image.Resampling.LANCZOS)

    center_x, center_y, _face_width, face_height = face
    target_face_height = min(
        0.5,
        max(
            0.05,
            float(
                frame_config.get("face_height_ratio", 0.25)
                if face_height_ratio is None
                else face_height_ratio
            ),
        ),
    )
    crop_height = source.height * face_height / target_face_height
    crop_height = min(
        source.height * float(frame_config.get("max_crop_height_ratio", 0.72)),
        max(
            source.height * float(frame_config.get("min_crop_height_ratio", 0.44)),
            crop_height,
        ),
    )
    crop_width = crop_height * width / height
    if crop_width > source.width:
        crop_width = float(source.width)
        crop_height = crop_width * height / width

    target_x = min(0.9, max(0.1, float(frame_config.get("face_target_x", 0.68))))
    target_y = min(0.75, max(0.1, float(frame_config.get("face_target_y", 0.27))))
    left = center_x * source.width - crop_width * target_x
    top = center_y * source.height - crop_height * target_y
    left = min(max(0.0, left), max(0.0, source.width - crop_width))
    top = min(max(0.0, top), max(0.0, source.height - crop_height))
    crop = source.crop(
        (
            round(left),
            round(top),
            round(left + crop_width),
            round(top + crop_height),
        )
    )
    return crop.resize((width, height), Image.Resampling.LANCZOS)


def _feather_mask(width: int, height: int, frame_config: dict[str, Any]) -> Image.Image:
    mask = Image.new("L", (width, height), 255)
    pixels = mask.load()
    left_width = min(width, max(0, int(frame_config.get("feather_left", 0))))
    top_height = min(height, max(0, int(frame_config.get("feather_top", 0))))
    bottom_height = min(height, max(0, int(frame_config.get("feather_bottom", 0))))
    for x in range(left_width):
        alpha = round(255 * (x / max(1, left_width - 1)) ** 1.5)
        for y in range(height):
            pixels[x, y] = min(pixels[x, y], alpha)
    for y in range(top_height):
        alpha = round(255 * y / max(1, top_height - 1))
        for x in range(width):
            pixels[x, y] = min(pixels[x, y], alpha)
    for offset in range(bottom_height):
        y = height - 1 - offset
        alpha = round(255 * offset / max(1, bottom_height - 1))
        for x in range(width):
            pixels[x, y] = min(pixels[x, y], alpha)
    return mask


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
    first_max_size: int,
    first_min_size: int,
    second_max_size: int,
    second_min_size: int,
    line_gap: int,
    colors: dict[str, str],
    rotation_degrees: float,
) -> Image.Image:
    lines = [
        (
            first_line.strip(),
            colors["title_first"],
            first_max_size,
            first_min_size,
        ),
        (
            second_line.strip(),
            colors["title_second"],
            second_max_size,
            second_min_size,
        ),
    ]
    visible_lines = [line for line in lines if line[0]]
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
        for text, color, max_size, min_size in visible_lines
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
    subject_anchor_x: float | None,
    face_height_ratio: float | None = None,
    background_image: Image.Image | None = None,
) -> Image.Image:
    canvas_config = template["canvas"]
    frame_config = template["frame"]
    text_config = template["text"]
    colors = template["colors"]
    width = int(canvas_config["width"])
    height = int(canvas_config["height"])
    if background_image is not None:
        canvas = background_image.convert("RGBA").resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )
    else:
        canvas = Image.new("RGBA", (width, height), _hex_rgba(colors["background"]))
        _draw_asanoha_pattern(canvas, _hex_rgba(colors["pattern"], 132))

        draw = ImageDraw.Draw(canvas, "RGBA")
        accent = _hex_rgba(colors["accent"], 190)
        draw.line((22, 528, 744, 244), fill=accent, width=36)
        draw.line(
            (52, 578, 714, 316),
            fill=_hex_rgba(colors["accent"], 90),
            width=18,
        )

    frame_x = int(frame_config["x"])
    frame_y = int(frame_config["y"])
    frame_width = int(frame_config["width"])
    frame_height = int(frame_config["height"])
    anchor_x = (
        float(frame_config["anchor_x"])
        if subject_anchor_x is None
        else min(1.0, max(0.0, float(subject_anchor_x)))
    )
    fitted_frame = _portrait_frame(
        frame,
        frame_width,
        frame_height,
        frame_config=frame_config,
        anchor_x=anchor_x,
        face_height_ratio=face_height_ratio,
    ).convert("RGBA")
    fitted_frame.putalpha(_feather_mask(frame_width, frame_height, frame_config))
    canvas.alpha_composite(fitted_frame, (frame_x, frame_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    if eyebrow.strip():
        eyebrow_box = text_config.get("eyebrow_box", {})
        box_x = int(eyebrow_box.get("x", 32))
        box_y = int(eyebrow_box.get("y", 28))
        box_width = int(eyebrow_box.get("width", 500))
        box_height = int(eyebrow_box.get("height", 118))
        draw.rectangle(
            (box_x, box_y, box_x + box_width, box_y + box_height),
            fill=_hex_rgba(colors["eyebrow_background"], 230),
            outline=_hex_rgba(colors["gold"]),
            width=5,
        )
        eyebrow_fit = _fit_text(
            eyebrow,
            font_path,
            max_width=int(text_config["eyebrow_max_width"]),
            max_size=int(text_config["eyebrow_max_size"]),
            min_size=18,
        )
        eyebrow_y = box_y + max(0, (box_height - eyebrow_fit.height) // 2 - 5)
        draw.text(
            (int(text_config["eyebrow_x"]), eyebrow_y),
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
            first_max_size=int(
                text_config.get("title_first_max_size", text_config["title_max_size"])
            ),
            first_min_size=int(
                text_config.get("title_first_min_size", text_config["title_min_size"])
            ),
            second_max_size=int(
                text_config.get("title_second_max_size", text_config["title_max_size"])
            ),
            second_min_size=int(
                text_config.get("title_second_min_size", text_config["title_min_size"])
            ),
            line_gap=int(text_config["line_gap"]),
            colors=colors,
            rotation_degrees=float(text_config["rotation_degrees"]),
        )
        canvas.alpha_composite(
            title,
            (int(text_config["title_x"]), int(text_config["title_y"])),
        )
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle(
        (13, 13, width - 14, height - 14),
        outline=_hex_rgba(colors["gold"]),
        width=5,
    )
    draw.rectangle(
        (27, 27, width - 28, height - 28),
        outline=_hex_rgba(colors["gold_light"], 145),
        width=2,
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
    subject_anchor_x: float | None = None,
    face_height_ratio: float | None = None,
    character_style: dict[str, Any] | None = None,
) -> ThumbnailRenderResult:
    """Render a 1280x720 normal thumbnail.

    ``frame_time`` is relative to ``input_path``. When ``input_path`` is the
    original source video, callers must pass the absolute source-video second.
    """
    output = _validate_jpeg_path(output_path)
    timestamp = _validate_timestamp(frame_time)
    template = _load_template(template_path)
    background_image_path = (
        Path(template_path).parent / str(template["background_image"])
        if template.get("background_image")
        else None
    )
    if background_image_path is not None and not background_image_path.is_file():
        raise FileNotFoundError(
            f"normal thumbnail background image not found: {background_image_path}"
        )
    plain_background = None
    if character_style is not None:
        style = NormalThumbnailStyle.model_validate(character_style)
        template["colors"].update({
            "title_first": style.title_color,
            "title_second": style.second_title_color,
            "title_outer_stroke": style.outline_color,
        })
        if style.design == "custom":
            background_image_path = banner_asset_path(style.background_asset_id)
        elif style.design == "plain":
            background_image_path = None
            plain_background = Image.new("RGBA", (1280, 720), style.background_color)
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
            if background_image_path is not None:
                with Image.open(background_image_path) as source_background:
                    composed = _compose_normal_thumbnail(
                        source_frame,
                        eyebrow=eyebrow,
                        title_first_line=title_first_line,
                        title_second_line=title_second_line,
                        template=template,
                        font_path=selected_font,
                        subject_anchor_x=subject_anchor_x,
                        face_height_ratio=face_height_ratio,
                        background_image=source_background,
                    )
            else:
                composed = _compose_normal_thumbnail(
                    source_frame,
                    eyebrow=eyebrow,
                    title_first_line=title_first_line,
                    title_second_line=title_second_line,
                    template=template,
                    font_path=selected_font,
                    subject_anchor_x=subject_anchor_x,
                    face_height_ratio=face_height_ratio,
                    background_image=plain_background,
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
