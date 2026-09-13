from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.short_banners import BannerAssetId


ThumbnailFontPreset = Literal[
    "noto_black",
    "heavy",
    "mplus_extrabold",
    "mplus_rounded_extrabold",
    "chikara",
    "chikara_yowaku",
    "keifont",
    "mushin",
    "ankoku_zonji",
    "tanuki_magic",
    "dela_gothic",
    "corporate_logo",
]


class ThumbnailTextStyle(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    font_preset: ThumbnailFontPreset = Field(default="noto_black", alias="fontPreset")
    font_size: int = Field(ge=12, le=180, alias="fontSize")
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    auto_fit: bool = Field(default=True, alias="autoFit")


class ThumbnailTextStyles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: ThumbnailTextStyle = Field(default_factory=lambda: ThumbnailTextStyle(fontSize=46, color="#E0C57B"))
    upper: ThumbnailTextStyle = Field(default_factory=lambda: ThumbnailTextStyle(fontSize=155, color="#FFFFFF"))
    lower: ThumbnailTextStyle = Field(default_factory=lambda: ThumbnailTextStyle(fontSize=112, color="#FFD84A"))

    @model_validator(mode="after")
    def heading_size_limit(self) -> "ThumbnailTextStyles":
        if self.heading.font_size > 96:
            raise ValueError("見出しの文字サイズは96以下にしてください。")
        return self


class NormalThumbnailStyle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    design: Literal["raden", "plain", "custom"] = "plain"
    background_asset_id: BannerAssetId | None = Field(default=None, alias="backgroundAssetId")
    background_color: str = Field(default="#20242B", pattern=r"^#[0-9A-Fa-f]{6}$", alias="backgroundColor")
    title_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$", alias="titleColor")
    second_title_color: str = Field(default="#FFD84A", pattern=r"^#[0-9A-Fa-f]{6}$", alias="secondTitleColor")
    outline_color: str = Field(default="#111111", pattern=r"^#[0-9A-Fa-f]{6}$", alias="outlineColor")
    text_styles: ThumbnailTextStyles | None = Field(default=None, alias="textStyles")

    @model_validator(mode="after")
    def require_custom_background(self) -> "NormalThumbnailStyle":
        if self.design == "custom" and not self.background_asset_id:
            raise ValueError("サムネイル背景画像を選択してください。")
        return self


def resolve_thumbnail_text_styles(character_style: dict | None, override: dict | None = None) -> ThumbnailTextStyles:
    if override is not None:
        return ThumbnailTextStyles.model_validate(override)
    style = NormalThumbnailStyle.model_validate(character_style) if character_style is not None else None
    if style and style.text_styles:
        return style.text_styles
    result = ThumbnailTextStyles()
    if style:
        result.upper.color = style.title_color
        result.lower.color = style.second_title_color
    return result
