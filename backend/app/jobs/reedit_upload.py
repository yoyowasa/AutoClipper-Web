from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExportItem
from app.storage.paths import StoragePaths


READ_CHUNK_SIZE = 1024 * 1024


class UploadSizeLimitExceeded(ValueError):
    pass


@dataclass(frozen=True)
class FileFingerprint:
    size_bytes: int
    sha256_hex: str


def fingerprint_stream(stream: BinaryIO, max_size_bytes: int) -> FileFingerprint:
    digest = sha256()
    total_size = 0
    while chunk := stream.read(READ_CHUNK_SIZE):
        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise UploadSizeLimitExceeded
        digest.update(chunk)
    return FileFingerprint(size_bytes=total_size, sha256_hex=digest.hexdigest())


def fingerprint_file(path: Path) -> FileFingerprint:
    digest = sha256()
    total_size = 0
    with path.open("rb") as input_file:
        while chunk := input_file.read(READ_CHUNK_SIZE):
            total_size += len(chunk)
            digest.update(chunk)
    return FileFingerprint(size_bytes=total_size, sha256_hex=digest.hexdigest())


def matching_exports(
    db: Session,
    paths: StoragePaths,
    fingerprint: FileFingerprint,
) -> list[ExportItem]:
    exports = db.scalars(
        select(ExportItem).order_by(ExportItem.created_at.desc())
    ).all()
    matches: list[ExportItem] = []
    for export in exports:
        video_path = paths.resolve_stored_file(export.video_path)
        try:
            if not video_path.is_file() or video_path.stat().st_size != fingerprint.size_bytes:
                continue
            if fingerprint_file(video_path).sha256_hex == fingerprint.sha256_hex:
                matches.append(export)
        except OSError:
            continue
    return matches
