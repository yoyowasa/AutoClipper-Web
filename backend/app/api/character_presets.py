from hashlib import sha256
from uuid import uuid4
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models import AppPreference, CharacterAsset
from app.posting_metadata import NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX, YouTubePostingProfile
from app.legacy_settings import without_retired_harvest_settings
from app.schemas import SubtitleStyleSnapshot
from app.short_banners import BannerAssetId, banner_asset_path
from app.storage.paths import StoragePaths, get_storage_paths
from app.storage.locking import storage_mutation_lock
from app.thumbnail_style import NormalThumbnailStyle

router = APIRouter(prefix="/api/preferences", tags=["preferences"])
PRESETS_KEY = "character_presets"


class CharacterSettings(SubtitleStyleSnapshot):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    audience_familiarity: Literal["known", "unknown"] = Field(default="known", alias="audienceFamiliarity")
    channel_name: str = Field(default="", max_length=120, alias="channelName")
    youtube_posting_profile: YouTubePostingProfile = Field(default_factory=YouTubePostingProfile, alias="youtubePostingProfile")
    normal_title_suffix: str = Field(default="", max_length=80, alias="normalTitleSuffix")
    normal_thumbnail_style: NormalThumbnailStyle = Field(default_factory=NormalThumbnailStyle, alias="normalThumbnailStyle")
    short_top_banner_asset_id: BannerAssetId = Field(default="raden-top", alias="shortTopBannerAssetId")
    short_bottom_banner_asset_id: BannerAssetId = Field(default="raden-bottom", alias="shortBottomBannerAssetId")
    short_top_banner_enabled: bool = Field(default=False, alias="shortTopBannerEnabled")
    short_bottom_banner_enabled: bool = Field(default=False, alias="shortBottomBannerEnabled")
    short_banner_preset_name: str = Field(default="", max_length=80, alias="shortBannerPresetName")
    normal_clip_count: int = Field(default=0, ge=0, le=12, alias="normalClipCount")
    short_count: int = Field(default=3, ge=0, le=24, alias="shortCount")

    @model_validator(mode="before")
    @classmethod
    def ignore_retired_harvest_setting(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return without_retired_harvest_settings(value)
        return value

    @model_validator(mode="after")
    def require_output(self) -> "CharacterSettings":
        if self.normal_clip_count + self.short_count == 0:
            raise ValueError("作成する動画を選択してください。")
        return self


class CharacterPreset(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str | None = Field(default=None, pattern=r"^character_[0-9a-f]{32}$")
    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    settings: CharacterSettings


class CharacterPresetDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    legacy_import: bool = Field(default=False, alias="legacyImport")
    presets: list[CharacterPreset] = Field(default_factory=list, max_length=50)
    selected_name: str = Field(default="", max_length=80, alias="selectedName")

    @model_validator(mode="after")
    def validate_names(self) -> "CharacterPresetDocument":
        names = [preset.name for preset in self.presets]
        if len(names) != len(set(names)):
            raise ValueError("保存名が重複しています。")
        ids = [preset.id for preset in self.presets if preset.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("キャラ設定のIDが重複しています。")
        if self.selected_name and self.selected_name not in names:
            raise ValueError("選択したキャラ設定が見つかりません。")
        return self


@router.get("/character-presets", response_model=CharacterPresetDocument, response_model_exclude_none=True)
def get_presets(db: Session = Depends(get_db)) -> CharacterPresetDocument:
    row = db.get(AppPreference, PRESETS_KEY)
    if row:
        document = CharacterPresetDocument.model_validate(row.value_json)
        return _with_legacy_ids(document)
    old = db.get(AppPreference, "youtube_posting_profile")
    if old is None:
        return CharacterPresetDocument()
    profile = YouTubePostingProfile.model_validate(old.value_json.get("profile", {}))
    name = profile.performer_name or "これまでの設定"
    is_raden = "らでん" in profile.performer_name
    snapshot = CharacterSettings(
        youtubePostingProfile=profile,
        normalTitleSuffix=NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX if is_raden else "",
        normalThumbnailStyle=NormalThumbnailStyle(
            design="raden" if is_raden else "plain", outlineColor="#0A665D" if is_raden else "#111111"
        ),
        shortTopBannerEnabled=is_raden,
        shortBottomBannerEnabled=is_raden,
        shortBannerPresetName="らでん用" if is_raden else "",
    )
    return _with_legacy_ids(
        CharacterPresetDocument(presets=[CharacterPreset(name=name, settings=snapshot)], selectedName=name, legacyImport=True)
    )


def _with_legacy_ids(document: CharacterPresetDocument) -> CharacterPresetDocument:
    # Stable on repeated GETs; do not rewrite old stored preferences while reading.
    for preset in document.presets:
        if preset.id is None:
            preset.id = "character_" + sha256(preset.name.encode("utf-8")).hexdigest()[:32]
    return document


@router.put("/character-presets", response_model=CharacterPresetDocument, response_model_exclude_none=True)
def save_presets(
    document: CharacterPresetDocument,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> CharacterPresetDocument:
    with storage_mutation_lock(paths.root):
        return _save_presets(document, db, paths)


def _save_presets(document: CharacterPresetDocument, db: Session, paths: StoragePaths) -> CharacterPresetDocument:
    existing = {preset.name: preset.id for preset in get_presets(db).presets}
    for preset in document.presets:
        # Old clients omit IDs when overwriting a name. Keep its asset association.
        if preset.name in existing:
            if preset.id is not None and preset.id != existing[preset.name]:
                raise HTTPException(422, "保存済みキャラ設定のIDは変更できません。")
            preset.id = existing[preset.name]
        elif preset.id is None:
            preset.id = "character_" + uuid4().hex
    ids = [preset.id for preset in document.presets]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "キャラ設定のIDが重複しています。")
    removed_ids = set(existing.values()) - set(ids)
    if removed_ids and db.scalar(select(CharacterAsset.id).where(CharacterAsset.preset_id.in_(removed_ids)).limit(1)):
        raise HTTPException(409, "素材も削除します。画面のキャラ設定削除で件数を確認してください。")
    for preset in document.presets:
        snapshot = preset.settings
        ids = [snapshot.short_top_banner_asset_id, snapshot.short_bottom_banner_asset_id]
        if snapshot.normal_thumbnail_style.background_asset_id:
            ids.append(snapshot.normal_thumbnail_style.background_asset_id)
        if any(not banner_asset_path(asset_id, paths).is_file() for asset_id in ids):
            raise HTTPException(422, "保存対象の画像が見つかりません。画像を選び直してください。")
    payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
    row = db.get(AppPreference, PRESETS_KEY)
    if row is None:
        db.add(AppPreference(key=PRESETS_KEY, value_json=payload))
    else:
        row.value_json = payload
    db.commit()
    return document
