from dataclasses import dataclass
import os
from pathlib import Path
import shutil


@dataclass(frozen=True)
class StorageUsage:
    storage_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int
    disk_free_percent: float
    scan_error_count: int = 0


def _is_reparse_point(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _physical_file_bytes(roots: tuple[Path, ...]) -> tuple[int, int]:
    total = 0
    scan_error_count = 0
    seen_files: set[tuple[int, int] | tuple[str, str]] = set()
    pending = [root for root in roots if root.exists()]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                try:
                    for entry in entries:
                        try:
                            # DirEntry.stat() can return zero file IDs for Windows hardlinks.
                            stat_result = os.stat(entry.path, follow_symlinks=False)
                            if entry.is_symlink() or _is_reparse_point(stat_result):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                        except FileNotFoundError:
                            continue
                        except OSError:
                            scan_error_count += 1
                            continue
                        if stat_result.st_ino:
                            identity: tuple[int, int] | tuple[str, str] = (
                                stat_result.st_dev,
                                stat_result.st_ino,
                            )
                        else:
                            identity = ("path", str(Path(entry.path).resolve()))
                        if identity in seen_files:
                            continue
                        seen_files.add(identity)
                        total += stat_result.st_size
                except OSError:
                    scan_error_count += 1
        except OSError:
            scan_error_count += 1
    return total, scan_error_count


def measure_storage_usage(
    root: Path,
    *,
    additional_roots: tuple[Path, ...] = (),
) -> StorageUsage:
    root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(root)
    free_percent = (disk.free / disk.total * 100.0) if disk.total else 0.0
    storage_bytes, scan_error_count = _physical_file_bytes((root, *additional_roots))
    return StorageUsage(
        storage_bytes=storage_bytes,
        disk_total_bytes=disk.total,
        disk_free_bytes=disk.free,
        disk_free_percent=free_percent,
        scan_error_count=scan_error_count,
    )


def storage_warning_reasons(
    usage: StorageUsage,
    *,
    storage_limit_bytes: int,
    minimum_free_percent: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if usage.storage_bytes > storage_limit_bytes:
        reasons.append("作業データが保存上限を超えています。期限切れデータを整理してください。")
    if usage.disk_free_percent < minimum_free_percent:
        reasons.append("SSDの空き容量が少なくなっています。")
    if usage.scan_error_count:
        reasons.append("一部の保存先を読み取れないため、使用量は参考値です。")
    return tuple(reasons)
