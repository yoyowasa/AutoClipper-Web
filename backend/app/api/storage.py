from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import StorageCleanupResponse, StorageStatusResponse
from app.storage.lifecycle import (
    cleanup_expired_storage,
    count_cleanup_eligible_jobs,
    count_cleanup_eligible_videos,
)
from app.storage.paths import StoragePaths, get_storage_paths
from app.storage.usage import measure_storage_usage, storage_warning_reasons


router = APIRouter(prefix="/api/storage", tags=["storage"])
CLEANUP_ACTION_HEADER = "storage-cleanup"


def _measure_configured_storage(paths: StoragePaths, settings: Settings):
    source_library = Path(settings.source_library_root).resolve()
    additional_roots = () if source_library == paths.root.resolve() else (source_library,)
    return measure_storage_usage(paths.root, additional_roots=additional_roots)


def _status_response(
    db: Session,
    paths: StoragePaths,
    settings: Settings,
) -> StorageStatusResponse:
    usage = _measure_configured_storage(paths, settings)
    reasons = storage_warning_reasons(
        usage,
        storage_limit_bytes=settings.storage_limit_bytes,
        minimum_free_percent=settings.storage_min_free_percent,
    )
    return StorageStatusResponse(
        storageBytes=usage.storage_bytes,
        storageLimitBytes=settings.storage_limit_bytes,
        diskFreeBytes=usage.disk_free_bytes,
        diskTotalBytes=usage.disk_total_bytes,
        diskFreePercent=usage.disk_free_percent,
        warning=bool(reasons),
        reasons=list(reasons),
        cleanupEligibleJobs=count_cleanup_eligible_jobs(
            db,
            settings.storage_terminal_retention_days,
        ),
        cleanupEligibleVideos=count_cleanup_eligible_videos(
            db,
            settings.storage_terminal_retention_days,
            settings.storage_orphan_retention_hours,
        ),
    )


@router.get("/status", response_model=StorageStatusResponse)
def get_storage_status(
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    settings: Settings = Depends(get_settings),
) -> StorageStatusResponse:
    return _status_response(db, paths, settings)


@router.post("/cleanup", response_model=StorageCleanupResponse)
def cleanup_storage(
    cleanup_action: str | None = Header(default=None, alias="X-AutoClipper-Action"),
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    settings: Settings = Depends(get_settings),
) -> StorageCleanupResponse:
    if cleanup_action != CLEANUP_ACTION_HEADER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "storage_cleanup_forbidden",
                "message": "storage cleanup requires an AutoClipper action header",
            },
        )
    before = _measure_configured_storage(paths, settings)
    result = cleanup_expired_storage(
        db,
        paths,
        terminal_retention_days=settings.storage_terminal_retention_days,
        orphan_retention_hours=settings.storage_orphan_retention_hours,
    )
    after = _measure_configured_storage(paths, settings)
    return StorageCleanupResponse(
        removedJobs=result.removed_jobs,
        removedVideos=result.removed_videos,
        removedFiles=result.removed_files,
        reclaimedBytes=max(0, before.storage_bytes - after.storage_bytes),
        errors=list(result.errors),
    )
