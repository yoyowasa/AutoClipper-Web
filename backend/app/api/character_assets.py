import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.character_asset_rules import CHARACTER_ASSET_MAX_BYTES, CHARACTER_ASSET_MAX_SLOTS, CHARACTER_EMOTIONS, CharacterEmotion
from app.character_assets import CharacterAssetList, CharacterAssetRead, asset_read, process_character_asset
from app.db import get_db
from app.models import CharacterAsset
from app.storage.character_asset_cleanup import preset_files, retire_files
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api", tags=["character-assets"])


def _require_preset(preset_id: str, db: Session) -> None:
    if not any(preset.id == preset_id for preset in get_presets(db).presets):
        raise HTTPException(404, "キャラ設定が見つかりません。")


@router.get("/character-presets/{preset_id}/assets", response_model=CharacterAssetList)
def list_assets(preset_id: str, db: Session = Depends(get_db)) -> CharacterAssetList:
    _require_preset(preset_id, db)
    assets = db.scalars(select(CharacterAsset).where(CharacterAsset.preset_id == preset_id).order_by(CharacterAsset.slot))
    groups = {emotion: [] for emotion in CHARACTER_EMOTIONS}
    for asset in assets:
        groups[asset.emotion].append(asset_read(asset))
    return CharacterAssetList(emotions=groups)


@router.post("/character-presets/{preset_id}/assets", response_model=CharacterAssetRead, status_code=201)
def upload_asset(
    preset_id: str,
    emotion: Annotated[CharacterEmotion, Form()],
    file: UploadFile,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> CharacterAssetRead:
    try:
        data = file.file.read(CHARACTER_ASSET_MAX_BYTES + 1)
    finally:
        file.file.close()
    with storage_mutation_lock(paths.root):
        _require_preset(preset_id, db)
        occupied = set(db.scalars(select(CharacterAsset.slot).where(
            CharacterAsset.preset_id == preset_id, CharacterAsset.emotion == emotion,
        )))
        slot = next((number for number in range(1, CHARACTER_ASSET_MAX_SLOTS + 1) if number not in occupied), None)
        if slot is None:
            raise HTTPException(422, "同じキャラ・同じ表情は5枚までです。素材を削除してから登録してください。")
        try:
            processed = process_character_asset(data, paths)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        asset_id = "asset_" + uuid4().hex
        path = paths.character_asset(preset_id, emotion, asset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(processed.png)
            os.replace(temporary, path)
            asset = CharacterAsset(
                id=asset_id, preset_id=preset_id, emotion=emotion, slot=slot,
                file_path=path.relative_to(paths.root).as_posix(), width=processed.width, height=processed.height,
                face_box=processed.face_box, has_alpha=processed.has_alpha, warnings=processed.warnings,
            )
            db.add(asset)
            db.flush()
            result = asset_read(asset)
            db.commit()
        except Exception as exc:
            db.rollback()
            path.unlink(missing_ok=True)
            if isinstance(exc, IntegrityError):
                raise HTTPException(422, "登録枠が更新されました。一覧を読み直してください。") from exc
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return result


@router.delete("/character-presets/{preset_id}/assets/{asset_id}", status_code=204)
def delete_asset(
    preset_id: str, asset_id: str,
    db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> Response:
    with storage_mutation_lock(paths.root):
        asset = db.get(CharacterAsset, asset_id)
        if asset is None or asset.preset_id != preset_id:
            raise HTTPException(404, "素材が見つかりません。")
        path = paths.character_asset(asset.preset_id, asset.emotion, asset.id)
        temporary = path.with_name(f".{uuid4().hex}.deleted")
        moved = path.is_file()
        if moved:
            os.replace(path, temporary)
        try:
            db.delete(asset)
            db.commit()
        except Exception:
            db.rollback()
            if moved:
                os.replace(temporary, path)
            raise
        temporary.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/character-assets/{asset_id}/image")
def get_image(
    asset_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    asset = db.get(CharacterAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "素材が見つかりません。")
    path = paths.character_asset(asset.preset_id, asset.emotion, asset.id)
    if not path.is_file():
        raise HTTPException(404, "素材の画像が見つかりません。")
    return FileResponse(path, media_type="image/png")


@router.get("/character-presets/{preset_id}/asset-counts")
def preset_asset_counts(preset_id: str, db: Session = Depends(get_db)) -> dict[str, int]:
    _require_preset(preset_id, db)
    return {
        "assets": db.scalar(select(func.count(CharacterAsset.id)).where(CharacterAsset.preset_id == preset_id)) or 0,
    }


class DeletePresetRequest(BaseModel):
    assets: int = Field(ge=0)


@router.delete("/character-presets/{preset_id}", status_code=204)
def delete_preset_with_assets(
    preset_id: str, confirmation: DeletePresetRequest, db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> Response:
    from app.api.character_presets import PRESETS_KEY, get_presets
    from app.models import AppPreference

    with storage_mutation_lock(paths.root):
        counts = preset_asset_counts(preset_id, db)
        if counts != confirmation.model_dump():
            raise HTTPException(409, "素材の件数が変わりました。確認をやり直してください。")
        document = get_presets(db)
        removed = next(item for item in document.presets if item.id == preset_id)
        document.presets = [item for item in document.presets if item.id != preset_id]
        if document.selected_name == removed.name:
            document.selected_name = ""
        document.legacy_import = False
        with retire_files(db, paths, preset_files(paths, preset_id)):
            for row in db.scalars(select(CharacterAsset).where(CharacterAsset.preset_id == preset_id)):
                db.delete(row)
            preference = db.get(AppPreference, PRESETS_KEY)
            payload = document.model_dump(by_alias=True, mode="json", exclude_none=True)
            if preference is None:
                db.add(AppPreference(key=PRESETS_KEY, value_json=payload))
            else:
                preference.value_json = payload
    return Response(status_code=204)
