"""RQ task to harvest and classify full-video character asset candidates."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update

from app.api.character_presets import get_presets
from app.db import SessionLocal
from app.jobs.character_asset_frames import extract_candidate, scan_candidates
from app.models import CharacterAsset, CharacterAssetCandidate, CharacterAssetHarvest, Video, utc_now
from app.scoring.character_asset_classify import CodexCharacterAssetClassifier, contact_sheet
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths, get_storage_paths


def harvest_failure_callback(job: Any, connection: Any, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    # RQ also calls this on timeout, where a killed work horse cannot update progress.
    with SessionLocal() as db:
        db.execute(update(CharacterAssetHarvest).where(
            CharacterAssetHarvest.id == job.args[0], CharacterAssetHarvest.state.in_(["queued", "running"]),
        ).values(state="failed", message="素材収集が中断されました。もう一度実行してください。", updated_at=utc_now()))
        db.commit()


def _active(db: Any, harvest_id: str) -> CharacterAssetHarvest | None:
    db.expire_all()
    row = db.get(CharacterAssetHarvest, harvest_id)
    if row is None or row.state != "running" or not any(item.id == row.preset_id for item in get_presets(db).presets):
        return None
    return row


def run_character_asset_harvest(
    harvest_id: str, *, session_factory: Any = SessionLocal, paths: StoragePaths | None = None,
    classifier: Any = None,
) -> None:
    storage = paths or get_storage_paths()
    with session_factory() as db:
        with storage_mutation_lock(storage.root):
            result = db.execute(update(CharacterAssetHarvest).where(
                CharacterAssetHarvest.id == harvest_id, CharacterAssetHarvest.state == "queued",
            ).values(state="running", message="元動画全体から素材候補を探しています。", updated_at=utc_now()))
            db.commit()
            if result.rowcount != 1:
                return
            harvest = _active(db, harvest_id)
            if harvest is None:
                return
            preset_id, video_id = harvest.preset_id, harvest.video_id
            video = db.get(Video, video_id)
            if video is None:
                harvest.state, harvest.message = "failed", "元動画が見つかりません。"
                db.commit()
                return
            video_path = storage.resolve_stored_file(video.stored_path)
            known = set(db.scalars(select(CharacterAssetCandidate.source_second).where(
                CharacterAssetCandidate.preset_id == preset_id, CharacterAssetCandidate.video_id == video_id,
            )))
            reference_asset = db.scalar(select(CharacterAsset).where(CharacterAsset.preset_id == preset_id).order_by(
                CharacterAsset.created_at, CharacterAsset.id,
            ))
            reference_source = (
                storage.character_asset(preset_id, reference_asset.emotion, reference_asset.id) if reference_asset else None
            )
        try:
            work_root = storage.temp / harvest_id
            work_root.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=work_root) as directory:
                work = Path(directory)
                reference = None
                # Copy the optional reference under the same lock used for deletion.
                with storage_mutation_lock(storage.root):
                    if reference_source is not None and reference_source.is_file():
                        reference = work / "reference.png"
                        reference.write_bytes(reference_source.read_bytes())
                frames = scan_candidates(video_path)
                new_ids: list[str] = []
                for frame in frames:
                    if frame.second in known:
                        continue
                    with storage_mutation_lock(storage.root):
                        if _active(db, harvest_id) is None:
                            return
                    try:
                        processed = extract_candidate(video_path, frame, work / "original.jpg", storage)
                    except ValueError:
                        continue
                    with storage_mutation_lock(storage.root):
                        if _active(db, harvest_id) is None:
                            return
                        # Another task cannot create a duplicate timestamp after a rescan.
                        existing = db.scalar(select(CharacterAssetCandidate.id).where(
                            CharacterAssetCandidate.preset_id == preset_id,
                            CharacterAssetCandidate.video_id == video_id,
                            CharacterAssetCandidate.source_second == frame.second,
                        ))
                        if existing:
                            continue
                        candidate_id = "candidate_" + uuid4().hex
                        path = storage.character_candidate(preset_id, video_id, candidate_id)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            path.write_bytes(processed.png)
                            db.add(CharacterAssetCandidate(
                                id=candidate_id, preset_id=preset_id, video_id=video_id, source_second=frame.second,
                                file_path=path.relative_to(storage.root).as_posix(), face_box=processed.face_box,
                                width=processed.width, height=processed.height, has_alpha=processed.has_alpha,
                                warnings=processed.warnings,
                            ))
                            db.commit()
                        except Exception:
                            db.rollback()
                            path.unlink(missing_ok=True)
                            raise
                        new_ids.append(candidate_id)

                classification_failed = False
                active_classifier = classifier or CodexCharacterAssetClassifier(
                    storage_root=storage.root, job_id=harvest_id, clip_id="character_assets",
                )
                for start in range(0, len(new_ids), 8):
                    batch = new_ids[start:start + 8]
                    with storage_mutation_lock(storage.root):
                        if _active(db, harvest_id) is None:
                            return
                        sheet = contact_sheet(
                            [storage.character_candidate(preset_id, video_id, identifier) for identifier in batch],
                            work / "sheet.jpg",
                        )
                    try:
                        classified = active_classifier.classify(sheet, count=len(batch), reference=reference)
                    except Exception:
                        classification_failed = True
                        continue  # PNGs are already persisted with emotion/usable/same_character unset.
                    with storage_mutation_lock(storage.root):
                        if _active(db, harvest_id) is None:
                            return
                        for item in classified.candidates:
                            row = db.get(CharacterAssetCandidate, batch[item.candidate_id])
                            if row is not None and row.status == "pending":
                                row.suggested_emotion, row.usable = item.emotion, item.usable
                                row.issues, row.score, row.same_character = item.issues, item.score, item.same_character
                        db.commit()
                with storage_mutation_lock(storage.root):
                    harvest = _active(db, harvest_id)
                    if harvest is None:
                        return
                    total = db.scalar(select(func.count(CharacterAssetCandidate.id)).where(
                        CharacterAssetCandidate.preset_id == preset_id, CharacterAssetCandidate.video_id == video_id,
                    )) or 0
                    harvest.state, harvest.candidate_count = "completed", total
                    harvest.message = (
                        "キャラが大きく映る場面がありませんでした（画質・余白の条件を含む）。" if not total
                        else "Codexの判定に失敗した候補があります。表情を選んで採用できます。" if classification_failed
                        else f"素材候補{total}枚。人が採用した素材だけを表情枠へ保存します。"
                    )
                    db.commit()
        except Exception:
            db.rollback()
            with storage_mutation_lock(storage.root):
                harvest = _active(db, harvest_id)
                if harvest is not None:
                    harvest.state, harvest.message = "failed", "動画からの素材収集に失敗しました。元動画を確認してください。"
                    db.commit()
            raise
