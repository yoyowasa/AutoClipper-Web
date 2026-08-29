from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
from typing import BinaryIO


READ_CHUNK_SIZE = 1024 * 1024
INCOMING_DIRECTORY_NAME = ".incoming"
BLOB_DIRECTORY_NAME = ".blobs"


class UploadSizeLimitExceeded(ValueError):
    pass


class ContentStorageError(RuntimeError):
    pass


class ContentBlobConflictError(ContentStorageError):
    pass


@dataclass(frozen=True)
class StagedUpload:
    incoming_path: Path
    size_bytes: int
    sha256_hex: str
    media_suffix: str

    def discard(self) -> None:
        self.incoming_path.unlink(missing_ok=True)
        _remove_empty_directory(self.incoming_path.parent)


@dataclass(frozen=True)
class PublishedUpload:
    stored_path: Path
    blob_path: Path
    blob_created: bool


def _remove_empty_directory(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(READ_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_existing_blob(blob_path: Path, staged: StagedUpload) -> None:
    if (
        blob_path.stat().st_size != staged.size_bytes
        or _sha256_file(blob_path) != staged.sha256_hex
    ):
        raise ContentBlobConflictError(
            "existing content blob does not match its SHA-256 path"
        )


def _copy_blob_exclusive(staged: StagedUpload, blob_path: Path) -> bool:
    created = False
    try:
        with staged.incoming_path.open("rb") as source, blob_path.open("xb") as output:
            created = True
            shutil.copyfileobj(source, output, length=READ_CHUNK_SIZE)
            output.flush()
            os.fsync(output.fileno())
        return True
    except FileExistsError:
        _validate_existing_blob(blob_path, staged)
        return False
    except Exception:
        if created:
            blob_path.unlink(missing_ok=True)
        raise


def stage_upload(
    stream: BinaryIO,
    uploads_root: Path,
    upload_name: str,
    max_size_bytes: int,
) -> StagedUpload:
    incoming_directory = uploads_root / INCOMING_DIRECTORY_NAME
    incoming_directory.mkdir(parents=True, exist_ok=True)
    incoming_path = incoming_directory / f"{upload_name}.part"
    digest = sha256()
    total_size = 0

    try:
        with incoming_path.open("xb") as output_file:
            while chunk := stream.read(READ_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise UploadSizeLimitExceeded
                output_file.write(chunk)
                digest.update(chunk)
    except Exception:
        incoming_path.unlink(missing_ok=True)
        _remove_empty_directory(incoming_directory)
        raise

    return StagedUpload(
        incoming_path=incoming_path,
        size_bytes=total_size,
        sha256_hex=digest.hexdigest(),
        media_suffix=Path(upload_name).suffix.lower() or ".bin",
    )


def publish_upload(
    staged: StagedUpload,
    uploads_root: Path,
) -> PublishedUpload:
    blob_directory = uploads_root / BLOB_DIRECTORY_NAME
    blob_directory.mkdir(parents=True, exist_ok=True)
    blob_path = blob_directory / f"{staged.sha256_hex}{staged.media_suffix}"
    blob_created = False

    try:
        try:
            os.link(staged.incoming_path, blob_path)
            blob_created = True
        except FileExistsError:
            _validate_existing_blob(blob_path, staged)
        except OSError:
            blob_created = _copy_blob_exclusive(staged, blob_path)

        return PublishedUpload(
            stored_path=blob_path,
            blob_path=blob_path,
            blob_created=blob_created,
        )
    except Exception:
        if blob_created:
            try:
                if blob_path.stat().st_nlink <= 2:
                    blob_path.unlink(missing_ok=True)
            except OSError:
                pass
        _remove_empty_directory(blob_directory)
        raise
