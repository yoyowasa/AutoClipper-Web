"""One-time processing and API metadata for character emotion images."""

from dataclasses import dataclass
from datetime import datetime
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from app.character_asset_rules import (
    CHARACTER_ASSET_MAX_BYTES,
    CHARACTER_ASSET_MAX_SLOTS,
    CHARACTER_ASSET_MIN_SIDE_PIXELS,
    CharacterEmotion,
    validate_character_asset_dimensions,
)
from app.models import CharacterAsset
from app.render import anime_subject
from app.storage.paths import StoragePaths


class CharacterFaceBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class CharacterAssetRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    preset_id: str = Field(alias="presetId")
    emotion: CharacterEmotion
    slot: int = Field(ge=1, le=CHARACTER_ASSET_MAX_SLOTS)
    image_url: str = Field(alias="imageUrl")
    width: int
    height: int
    face_box: CharacterFaceBox | None = Field(alias="faceBox")
    has_alpha: bool = Field(alias="hasAlpha")
    warnings: list[str]
    created_at: datetime = Field(alias="createdAt")


class CharacterAssetList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    emotions: dict[CharacterEmotion, list[CharacterAssetRead]]
    min_side_pixels: int = Field(default=CHARACTER_ASSET_MIN_SIDE_PIXELS, alias="minSidePixels")
    max_image_bytes: int = Field(default=CHARACTER_ASSET_MAX_BYTES, alias="maxImageBytes")
    max_per_emotion: int = Field(default=CHARACTER_ASSET_MAX_SLOTS, alias="maxPerEmotion")


def asset_read(asset: CharacterAsset) -> CharacterAssetRead:
    return CharacterAssetRead(
        id=asset.id, presetId=asset.preset_id, emotion=asset.emotion, slot=asset.slot,
        imageUrl=f"/api/character-assets/{asset.id}/image", width=asset.width, height=asset.height,
        faceBox=asset.face_box, hasAlpha=asset.has_alpha, warnings=asset.warnings, createdAt=asset.created_at,
    )


@dataclass(frozen=True)
class ProcessedCharacterAsset:
    png: bytes
    width: int
    height: int
    face_box: dict[str, float] | None
    has_alpha: bool
    warnings: list[str]


def process_character_asset(
    data: bytes, paths: StoragePaths, *, known_face: tuple[float, float, float, float] | None = None,
) -> ProcessedCharacterAsset:
    if len(data) > CHARACTER_ASSET_MAX_BYTES:
        raise ValueError("画像は1枚20MBまでです。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("PNG・JPEG・WebPの画像を選んでください。")
                reason = validate_character_asset_dimensions(*source.size)
                if reason:
                    raise ValueError(reason)
                image = ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("画像を読み込めません。PNG・JPEG・WebPを選んでください。") from exc
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("画像の画素数が大きすぎます。縮小して登録してください。") from exc

    face = known_face if known_face is not None else anime_subject.detect_anime_face(image)
    face_box = None
    notices = []
    if face is not None:
        # detect_anime_face returns center coordinates; store top-left x/y.
        cx, cy, width, height = face
        left, top = max(0.0, cx - width / 2), max(0.0, cy - height / 2)
        face_box = {"x": left, "y": top, "w": min(width, 1 - left), "h": min(height, 1 - top)}
    else:
        notices.append("顔を検出できません（配置を手で調整してください）")

    has_alpha = image.getchannel("A").getextrema()[0] < 255
    if not has_alpha:
        model_path = paths.models / anime_subject.ANIME_MATTE_FILENAME
        if not model_path.is_file():
            notices.append("背景付き（切り抜きモデル未導入）")
        else:
            # With no detected face, select the largest foreground component.
            mask = anime_subject.anime_character_mask(image, face or (0.5, 0.5, 1.0, 1.0), model_path=model_path)
            if mask is not None:
                image.putalpha(mask)
                has_alpha = image.getchannel("A").getextrema()[0] < 255
            if not has_alpha:
                notices.append("背景付き（人物を切り抜けませんでした）")

    output = io.BytesIO()
    # Do not retain original files, EXIF, or other source metadata.
    Image.frombytes("RGBA", image.size, image.tobytes()).save(output, format="PNG")
    return ProcessedCharacterAsset(output.getvalue(), image.width, image.height, face_box, has_alpha, notices)
