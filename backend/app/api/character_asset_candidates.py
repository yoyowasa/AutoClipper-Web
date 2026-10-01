"""Candidate management; HTTP only queues harvesting and copies adopted PNGs."""

import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.character_assets import _require_preset
from app.character_asset_rules import CHARACTER_ASSET_MAX_SLOTS, CharacterEmotion, validate_character_asset_dimensions
from app.character_assets import CharacterAssetRead, asset_read
from app.db import get_db
from app.jobs.character_asset_harvest_state import request_harvest
from app.jobs.queue import get_enqueue_character_asset_harvest
from app.models import CharacterAsset, CharacterAssetCandidate, CharacterAssetHarvest, Job, Video
from app.storage.locking import storage_mutation_lock
from app.storage.character_asset_cleanup import preset_files, retire_files
from app.storage.paths import StoragePaths, get_storage_paths


router = APIRouter(prefix="/api", tags=["character-asset-candidates"])


def candidate_read(row: CharacterAssetCandidate) -> dict[str, Any]:
    return {
        "id": row.id, "presetId": row.preset_id, "videoId": row.video_id, "sourceSecond": row.source_second,
        "imageUrl": f"/api/character-asset-candidates/{row.id}/image", "faceBox": row.face_box,
        "suggestedEmotion": row.suggested_emotion, "usable": row.usable, "issues": row.issues,
        "score": row.score, "sameCharacter": row.same_character, "status": row.status,
        "warnings": row.warnings, "createdAt": row.created_at,
    }


def harvest_read(row: CharacterAssetHarvest) -> dict[str, Any]:
    return {
        "id": row.id, "videoId": row.video_id, "state": row.state, "candidateCount": row.candidate_count,
        "message": row.message, "updatedAt": row.updated_at,
    }


@router.get("/character-presets/{preset_id}/asset-candidates")
def list_candidates(preset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_preset(preset_id, db)
    rows = db.scalars(select(CharacterAssetCandidate).where(CharacterAssetCandidate.preset_id == preset_id).order_by(
        CharacterAssetCandidate.score.desc(), CharacterAssetCandidate.created_at.desc(), CharacterAssetCandidate.id,
    ))
    harvests = db.scalars(select(CharacterAssetHarvest).where(CharacterAssetHarvest.preset_id == preset_id).order_by(
        CharacterAssetHarvest.updated_at.desc(),
    ))
    return {"candidates": [candidate_read(row) for row in rows], "harvests": [harvest_read(row) for row in harvests]}


@router.get("/character-presets/{preset_id}/harvest-videos")
def list_processed_videos(
    preset_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> list[dict[str, Any]]:
    _require_preset(preset_id, db)
    rows = db.scalars(select(Video).where(Video.jobs.any(Job.status == "completed")).order_by(Video.created_at.desc()))
    return [{"id": row.id, "filename": row.original_filename, "duration": row.duration}
            for row in rows if paths.resolve_stored_file(row.stored_path).is_file()]


class HarvestRequest(BaseModel):
    video_id: str = Field(alias="videoId", pattern=r"^vid_[0-9a-f]{32}$")


@router.post("/character-presets/{preset_id}/asset-harvests", status_code=202)
def start_harvest(
    preset_id: str, request: HarvestRequest, db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths), enqueue: Any = Depends(get_enqueue_character_asset_harvest),
) -> dict[str, Any]:
    _require_preset(preset_id, db)
    try:
        return harvest_read(request_harvest(db, paths, preset_id, request.video_id, enqueue))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "素材収集のキュー登録に失敗しました。もう一度実行してください。") from exc


class AdoptRequest(BaseModel):
    emotion: CharacterEmotion
    replace_slot: int | None = Field(default=None, alias="replaceSlot", ge=1, le=CHARACTER_ASSET_MAX_SLOTS)


@router.post("/character-presets/{preset_id}/asset-candidates/{candidate_id}/adopt", response_model=CharacterAssetRead)
def adopt_candidate(
    preset_id: str, candidate_id: str, request: AdoptRequest,
    db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> CharacterAssetRead:
    with storage_mutation_lock(paths.root):
        _require_preset(preset_id, db)
        row = db.get(CharacterAssetCandidate, candidate_id)
        if row is None or row.preset_id != preset_id:
            raise HTTPException(404, "素材候補が見つかりません。")
        if row.status == "adopted":
            raise HTTPException(409, "この素材候補は採用済みです。")
        reason = validate_character_asset_dimensions(row.width, row.height)
        if reason:
            raise HTTPException(422, reason)
        occupied = {item.slot: item for item in db.scalars(select(CharacterAsset).where(
            CharacterAsset.preset_id == preset_id, CharacterAsset.emotion == request.emotion,
        ))}
        slot = request.replace_slot or next((n for n in range(1, CHARACTER_ASSET_MAX_SLOTS + 1) if n not in occupied), None)
        if slot is None:
            raise HTTPException(422, "表情の枠が5枚埋まっています。入れ替える枠を選んでください。")
        old = occupied.get(slot)
        if request.replace_slot is not None and old is None:
            raise HTTPException(409, "入れ替える枠が変更されました。一覧を読み直してください。")
        source = paths.character_candidate(preset_id, row.video_id, row.id)
        if not source.is_file():
            raise HTTPException(404, "素材候補の画像が見つかりません。")
        asset_id = "asset_" + uuid4().hex
        destination = paths.character_asset(preset_id, request.emotion, asset_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{uuid4().hex}.tmp")
        old_path = paths.character_asset(preset_id, request.emotion, old.id) if old else None
        tombstone = old_path.with_name(f".{uuid4().hex}.deleted") if old_path else None
        moved = False
        try:
            temporary.write_bytes(source.read_bytes())
            os.replace(temporary, destination)
            if old is not None:
                if old_path.is_file():
                    os.replace(old_path, tombstone)
                    moved = True
                db.delete(old)
                db.flush()
            asset = CharacterAsset(
                id=asset_id, preset_id=preset_id, emotion=request.emotion, slot=slot,
                file_path=destination.relative_to(paths.root).as_posix(), width=row.width, height=row.height,
                face_box=row.face_box, has_alpha=row.has_alpha, warnings=row.warnings,
            )
            db.add(asset)
            row.status = "adopted"
            db.flush()
            result = asset_read(asset)
            db.commit()
        except Exception:
            db.rollback()
            destination.unlink(missing_ok=True)
            if moved:
                os.replace(tombstone, old_path)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        if moved:
            tombstone.unlink(missing_ok=True)
        return result


@router.post("/character-presets/{preset_id}/asset-candidates/{candidate_id}/reject", status_code=204)
def reject_candidate(
    preset_id: str, candidate_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> Response:
    with storage_mutation_lock(paths.root):
        _require_preset(preset_id, db)
        row = db.get(CharacterAssetCandidate, candidate_id)
        if row is None or row.preset_id != preset_id:
            raise HTTPException(404, "素材候補が見つかりません。")
        if row.status == "adopted":
            raise HTTPException(409, "採用済みの素材は表情枠から削除してください。")
        row.status = "rejected"
        db.commit()
    return Response(status_code=204)


@router.get("/character-asset-candidates/{candidate_id}/image")
def candidate_image(
    candidate_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    row = db.get(CharacterAssetCandidate, candidate_id)
    if row is None:
        raise HTTPException(404, "素材候補が見つかりません。")
    path = paths.character_candidate(row.preset_id, row.video_id, row.id)
    if not path.is_file():
        raise HTTPException(404, "素材候補の画像が見つかりません。")
    return FileResponse(path, media_type="image/png")


@router.get("/character-presets/{preset_id}/asset-counts")
def preset_asset_counts(preset_id: str, db: Session = Depends(get_db)) -> dict[str, int]:
    _require_preset(preset_id, db)
    return {
        "assets": db.scalar(select(func.count(CharacterAsset.id)).where(CharacterAsset.preset_id == preset_id)) or 0,
        "candidates": db.scalar(select(func.count(CharacterAssetCandidate.id)).where(
            CharacterAssetCandidate.preset_id == preset_id,
        )) or 0,
    }


class DeletePresetRequest(BaseModel):
    assets: int = Field(ge=0)
    candidates: int = Field(ge=0)


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
            for model in (CharacterAsset, CharacterAssetCandidate, CharacterAssetHarvest):
                for row in db.scalars(select(model).where(model.preset_id == preset_id)):
                    db.delete(row)
            preference = db.get(AppPreference, PRESETS_KEY)
            payload = document.model_dump(by_alias=True, mode="json", exclude_none=True)
            if preference is None:
                db.add(AppPreference(key=PRESETS_KEY, value_json=payload))
            else:
                preference.value_json = payload
    return Response(status_code=204)
