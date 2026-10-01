"""File/DB retirement under the caller's storage mutation lock."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CharacterAssetCandidate, CharacterAssetHarvest
from app.storage.paths import StoragePaths


CANDIDATE_RETENTION_DAYS = 30


@contextmanager
def retire_files(db: Session, paths: StoragePaths, files: list[Path]) -> Iterator[None]:
    moved: list[tuple[Path, Path]] = []
    try:
        for path in dict.fromkeys(files):
            path.resolve().relative_to(paths.root.resolve())
            if path.is_file():
                tombstone = path.with_name(f".{uuid4().hex}.deleted")
                os.replace(path, tombstone)
                moved.append((path, tombstone))
        yield
        db.commit()
    except Exception:
        db.rollback()
        for original, tombstone in reversed(moved):
            os.replace(tombstone, original)
        raise
    for _original, tombstone in moved:
        tombstone.unlink(missing_ok=True)


def preset_files(paths: StoragePaths, preset_id: str) -> list[Path]:
    # The preset ID was checked against the saved preset document by the caller.
    roots = [paths.character_assets / preset_id, paths.character_asset_candidates / preset_id]
    files: list[Path] = []
    for root in roots:
        root.resolve().relative_to(paths.root.resolve())
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return files


def expire_candidates(db: Session, paths: StoragePaths, now: datetime) -> int:
    active = select(CharacterAssetHarvest.preset_id).where(CharacterAssetHarvest.state.in_(["queued", "running"]))
    rows = list(db.scalars(select(CharacterAssetCandidate).where(
        CharacterAssetCandidate.created_at <= now - timedelta(days=CANDIDATE_RETENTION_DAYS),
        CharacterAssetCandidate.preset_id.not_in(active),
    )))
    files = [paths.character_candidate(row.preset_id, row.video_id, row.id) for row in rows]
    count = sum(path.is_file() for path in files)
    with retire_files(db, paths, files):
        for row in rows:
            db.delete(row)
    return count
