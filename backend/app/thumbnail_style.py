from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.short_banners import BannerAssetId


class NormalThumbnailStyle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    design: Literal["raden", "plain", "custom"] = "plain"
    background_asset_id: BannerAssetId | None = Field(default=None, alias="backgroundAssetId")
    background_color: str = Field(default="#20242B", pattern=r"^#[0-9A-Fa-f]{6}$", alias="backgroundColor")
    title_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$", alias="titleColor")
    second_title_color: str = Field(default="#FFD84A", pattern=r"^#[0-9A-Fa-f]{6}$", alias="secondTitleColor")
    outline_color: str = Field(default="#111111", pattern=r"^#[0-9A-Fa-f]{6}$", alias="outlineColor")

    @model_validator(mode="after")
    def require_custom_background(self) -> "NormalThumbnailStyle":
        if self.design == "custom" and not self.background_asset_id:
            raise ValueError("サムネイル背景画像を選択してください。")
        return self
