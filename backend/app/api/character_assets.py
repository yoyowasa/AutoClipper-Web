import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.character_asset_rules import CHARACTER_ASSET_MAX_BYTES, CHARACTER_ASSET_MAX_SLOTS, CHARACTER_EMOTIONS, CharacterEmotion
from app.character_assets import CharacterAssetList, CharacterAssetRead, asset_read, process_character_asset
from app.db import get_db
from app.models import CharacterAsset
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
