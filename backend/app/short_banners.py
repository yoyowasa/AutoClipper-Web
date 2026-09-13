"""Named banner snapshots and immutable uploaded image assets."""

import hashlib
import io
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from app.storage.paths import StoragePaths, get_storage_paths

BannerAssetId = Annotated[str, Field(pattern=r"^(raden-top|raden-bottom|[a-f0-9]{64})$")]
BUILTIN_DIR = Path(__file__).resolve().parent / "render" / "assets"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ShortBannerPreset(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    top_asset_id: BannerAssetId = Field(default="raden-top", alias="topAssetId")
    bottom_asset_id: BannerAssetId = Field(default="raden-bottom", alias="bottomAssetId")
    top_enabled: bool = Field(default=True, alias="topEnabled")
    bottom_enabled: bool = Field(default=True, alias="bottomEnabled")


class ShortBannerPresetDocument(BaseModel):
    presets: list[ShortBannerPreset] = Field(default_factory=list, max_length=10)


class BannerAssetResponse(BaseModel):
    assetId: BannerAssetId


def banner_asset_path(asset_id: str, paths: StoragePaths | None = None) -> Path:
    if asset_id in {"raden-top", "raden-bottom"}:
        position = asset_id.removeprefix("raden-")
        return BUILTIN_DIR / f"short_{position}_banner.png"
    if not re.fullmatch(r"[a-f0-9]{64}", asset_id):
        raise ValueError("帯画像のIDが不正です。")
    return (paths or get_storage_paths()).banner_assets / f"{asset_id}.png"


def resolve_banner_path(
    settings: Mapping[str, Any] | None,
    position: str,
    default_path: Path,
    paths: StoragePaths | None = None,
) -> Path:
    asset_id = (settings or {}).get(f"short{position.title()}BannerAssetId")
    if asset_id is None or asset_id == f"raden-{position}":
        return default_path
    return banner_asset_path(str(asset_id), paths)


def store_banner_image(data: bytes, paths: StoragePaths) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("帯画像は10MB以下にしてください。")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("PNG・JPEG・WebP画像を選択してください。")
            if source.width * source.height > 16_000_000:
                raise ValueError("帯画像は1600万画素以下にしてください。")
            source.load()
            output = io.BytesIO()
            source.convert("RGBA").save(output, format="PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("帯画像を読み込めません。") from exc
    normalized = output.getvalue()
    asset_id = hashlib.sha256(normalized).hexdigest()
    path = banner_asset_path(asset_id, paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Content-addressed assets are never overwritten or removed with a preset.
    try:
        with path.open("xb") as target:
            target.write(normalized)
    except FileExistsError:
        pass
    return asset_id
