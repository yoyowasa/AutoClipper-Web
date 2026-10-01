"""Queue reservation and completion hook, independent of video/Codex processing."""

from collections.abc import Callable
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.models import CharacterAssetHarvest, Job, Video
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths


def request_harvest(
    db: Session, paths: StoragePaths, preset_id: str, video_id: str, enqueue: Callable[[str], None],
) -> CharacterAssetHarvest:
    with storage_mutation_lock(paths.root):
        if not any(item.id == preset_id for item in get_presets(db).presets):
            raise ValueError("キャラ設定が見つかりません。")
        video = db.get(Video, video_id)
        processed = db.scalar(select(Job.id).where(Job.video_id == video_id, Job.status == "completed"))
        if video is None or processed is None:
            raise ValueError("処理済みの元動画を選んでください。")
        if not paths.resolve_stored_file(video.stored_path).is_file():
            raise ValueError("元動画が保存先にありません。")
        harvest = db.scalar(select(CharacterAssetHarvest).where(
            CharacterAssetHarvest.preset_id == preset_id, CharacterAssetHarvest.video_id == video_id,
        ))
        if harvest is not None and harvest.state in {"queued", "running"}:
            return harvest
        if harvest is None:
            harvest = CharacterAssetHarvest(id="harvest_" + uuid4().hex, preset_id=preset_id, video_id=video_id)
            db.add(harvest)
        else:
            # A late callback from the previous RQ attempt must not fail a new scan.
            harvest.id = "harvest_" + uuid4().hex
        harvest.state, harvest.candidate_count, harvest.message = "queued", 0, "素材候補の走査を待っています。"
        db.commit()
        try:
            enqueue(harvest.id)
        except Exception:
            harvest.state, harvest.message = "failed", "キューへの登録に失敗しました。もう一度実行してください。"
            db.commit()
            raise
        db.refresh(harvest)
        return harvest


def enqueue_completed_job_harvest(db: Session, job: Job, paths: StoragePaths) -> None:
    """An optional harvest failure must not undo a successful video export."""
    if job.status != "completed" or not job.settings_json.get("autoHarvestCharacterAssets", True):
        return
    try:
        presets = get_presets(db).presets
        preset_id = job.settings_json.get("characterPresetId")
        name = job.settings_json.get("characterPresetName")
        preset = next((item for item in presets if item.id == preset_id or (not preset_id and item.name == name)), None)
        if preset is None or not preset.settings.auto_harvest_character_assets:
            return
        from app.jobs.queue import enqueue_character_asset_harvest

        request_harvest(db, paths, preset.id, job.video_id, enqueue_character_asset_harvest)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).warning("Character asset harvest could not be queued for completed job %s", job.id)
