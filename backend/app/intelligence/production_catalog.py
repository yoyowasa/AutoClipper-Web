"""Read permanent records without depending on disposable ExportItem rows."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import unicodedata

from app.production_records import ProductionRecord
from app.storage.paths import StoragePaths


def normalize_title(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Record timestamps require a timezone")
    return value.astimezone(UTC).replace(tzinfo=None)


@dataclass
class RecordFamily:
    id: str
    latest: ProductionRecord
    created_at: datetime
    ambiguous: bool = False
    titles: tuple[str, ...] = ()


def read_families(paths: StoragePaths) -> tuple[dict[str, RecordFamily], list[dict[str, str]]]:
    records, issues = {}, []
    for path in sorted(paths.production_records.glob("*.json")):
        try:
            if path.stat().st_size > 1_000_000 or path.is_symlink():
                raise ValueError("Invalid record file")
            path.resolve().relative_to(paths.root.resolve())
            record = ProductionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if path.stem != record.recordId or utc_naive(record.updatedAt) < utc_naive(record.createdAt):
                raise ValueError("Invalid record identity/time")
            if not normalize_title(record.publicationTitle):
                raise ValueError("Empty title")
            records[record.recordId] = record
        except (OSError, ValueError):
            issues.append({"recordId": path.stem, "reason": "INVALID_RECORD"})
    grouped = {}
    for record in records.values():
        cursor, seen = record, set()
        valid = True
        while cursor.previousRecordId:
            if cursor.recordId in seen:
                valid = False
                break
            seen.add(cursor.recordId)
            previous = records.get(cursor.previousRecordId)
            if previous is None or previous.jobId != record.jobId or previous.revision >= cursor.revision:
                valid = False
                break
            cursor = previous
        if not valid:
            issues.append({"recordId": record.recordId, "reason": "INVALID_LINEAGE"})
            continue
        grouped.setdefault(cursor.recordId, []).append(record)
    families = {}
    for root, members in grouped.items():
        highest = max(record.revision for record in members)
        latest = [record for record in members if record.revision == highest]
        # Branches are ambiguous even when their revisions differ.
        children = {}
        for record in members:
            if record.previousRecordId:
                children[record.previousRecordId] = children.get(record.previousRecordId, 0) + 1
        ambiguous = len(latest) != 1 or any(count > 1 for count in children.values())
        chosen = sorted(latest, key=lambda record: record.recordId)[0]
        families[root] = RecordFamily(root, chosen, utc_naive(records[root].createdAt), ambiguous,
                                      tuple(normalize_title(record.publicationTitle) for record in members))
        if ambiguous:
            issues.append({"recordId": root, "reason": "AMBIGUOUS_LINEAGE"})
    return families, issues
