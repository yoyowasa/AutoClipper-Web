"""Place a processed PNG by its saved face; never re-detect or re-matte it."""

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
    bottom: int
    face_center: tuple[float, float]


def character_asset_layout(size: tuple[int, int], frame: dict[str, Any], face_box: dict[str, float] | None,
                           *, scale: float = 1, offset_x: int = 0, offset_y: int = 0) -> CharacterAssetLayout:
    width, height = size
    if face_box:
        cx = (face_box["x"] + face_box["w"] / 2) * width
        cy = (face_box["y"] + face_box["h"] / 2) * height
        face_height = face_box["h"] * height
    else:
        cx, cy, face_height = width * .5, height * .35, height * .3
    bottom = min(height, round(cy + 2.75 * face_height))
    fit = frame["height"] * .7 / max(1, bottom - cy) * scale
    x = round(frame["width"] * float(frame.get("face_target_x", .5)) - cx * fit + offset_x)
    y = round(frame["height"] * .3 - cy * fit + offset_y)
    return CharacterAssetLayout(fit, x, y, bottom, (cx, cy))


def place_character_asset(image: Image.Image, frame: dict[str, Any], face_box: dict[str, float] | None,
                          *, scale: float, offset_x: int, offset_y: int, info: dict[str, Any] | None) -> Image.Image:
    layout = character_asset_layout(image.size, frame, face_box, scale=scale, offset_x=offset_x, offset_y=offset_y)
    portrait = image.convert("RGBA").crop((0, 0, image.width, layout.bottom))
    portrait = portrait.resize((max(1, round(portrait.width * layout.scale)), max(1, round(portrait.height * layout.scale))),
                               Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (frame["width"], frame["height"]))
    layer.alpha_composite(portrait, (layout.x, layout.y))
    if info is not None:
        info.update(upscale=layout.scale, warnings=[ASSET_ROUGH_WARNING] if layout.scale > ASSET_MAX_CLEAR_SCALE else [])
    return layer
