"""Fit the complete processed PNG in the character frame without using faces."""

from dataclasses import dataclass
from typing import Any

from PIL import Image


ASSET_ROUGH_WARNING = "素材の解像度が足りず粗くなります"
ASSET_MAX_CLEAR_SCALE = 2.0


@dataclass(frozen=True)
class CharacterAssetLayout:
    scale: float
    x: int
    y: int
    width: int
    height: int


def character_asset_layout(size: tuple[int, int], frame: dict[str, Any], face_box: dict[str, float] | None,
                           *, scale: float = 1, offset_x: int = 0, offset_y: int = 0) -> CharacterAssetLayout:
    width, height = size
    target_x = frame["width"] * float(frame.get("face_target_x", .5))
    # Keep the configured center while fitting both edges at the default scale.
    available_width = 2 * min(target_x, frame["width"] - target_x)
    fit = min(frame["height"] / height, available_width / width) * scale
    rendered_width, rendered_height = max(1, round(width * fit)), max(1, round(height * fit))
    x = round(target_x - rendered_width / 2 + offset_x)
    y = frame["height"] - rendered_height + offset_y
    # face_box remains accepted for saved data/caller compatibility; it is unused.
    return CharacterAssetLayout(fit, x, y, rendered_width, rendered_height)


def place_character_asset(image: Image.Image, frame: dict[str, Any], face_box: dict[str, float] | None,
                          *, scale: float, offset_x: int, offset_y: int, info: dict[str, Any] | None) -> Image.Image:
    layout = character_asset_layout(image.size, frame, face_box, scale=scale, offset_x=offset_x, offset_y=offset_y)
    portrait = image.convert("RGBA").resize((layout.width, layout.height), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (frame["width"], frame["height"]))
    layer.alpha_composite(portrait, (layout.x, layout.y))
    if info is not None:
        info.update(upscale=layout.scale, warnings=[ASSET_ROUGH_WARNING] if layout.scale > ASSET_MAX_CLEAR_SCALE else [])
    return layer
