"""File/DB retirement under the caller's storage mutation lock."""

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy.orm import Session

from app.storage.paths import StoragePaths


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
    roots = [paths.character_assets / preset_id]
    files: list[Path] = []
    for root in roots:
        root.resolve().relative_to(paths.root.resolve())
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return files
