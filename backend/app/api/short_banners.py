from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppPreference
from app.short_banners import (
    MAX_IMAGE_BYTES,
    BannerAssetResponse,
    ShortBannerPresetDocument,
    banner_asset_path,
    store_banner_image,
)
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/preferences", tags=["preferences"])
PRESETS_KEY = "short_banner_presets"


@router.get("/short-banner-presets", response_model=ShortBannerPresetDocument)
def get_presets(db: Session = Depends(get_db)) -> ShortBannerPresetDocument:
    row = db.get(AppPreference, PRESETS_KEY)
    return ShortBannerPresetDocument.model_validate(row.value_json) if row else ShortBannerPresetDocument()


@router.put("/short-banner-presets", response_model=ShortBannerPresetDocument)
def save_presets(
    document: ShortBannerPresetDocument,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ShortBannerPresetDocument:
    names = [preset.name.strip() for preset in document.presets]
    if len(set(names)) != len(names):
        raise HTTPException(422, "帯の保存名が重複しています。")
    for preset in document.presets:
        for asset_id in (preset.top_asset_id, preset.bottom_asset_id):
            if not banner_asset_path(asset_id, paths).is_file():
                raise HTTPException(422, "帯画像が見つかりません。画像を選び直してください。")
    payload = document.model_dump(mode="json", by_alias=True)
    row = db.get(AppPreference, PRESETS_KEY)
    if row is None:
        db.add(AppPreference(key=PRESETS_KEY, value_json=payload))
    else:
        row.value_json = payload
    db.commit()
    return document


@router.post("/short-banner-assets", response_model=BannerAssetResponse)
async def upload_asset(
    file: UploadFile,
    paths: StoragePaths = Depends(get_storage_paths),
) -> BannerAssetResponse:
    try:
        data = await file.read(MAX_IMAGE_BYTES + 1)
        return BannerAssetResponse(assetId=store_banner_image(data, paths))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()


@router.get("/short-banner-assets/{asset_id}")
def get_asset(asset_id: str, paths: StoragePaths = Depends(get_storage_paths)) -> FileResponse:
    try:
        path = banner_asset_path(asset_id, paths)
    except ValueError as exc:
        raise HTTPException(404, "帯画像が見つかりません。") from exc
    if not path.is_file():
        raise HTTPException(404, "帯画像が見つかりません。")
    return FileResponse(path, media_type="image/png")
