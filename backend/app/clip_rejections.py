"""Permanent rejection ledger; writes are committed by the successful enqueue route."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClipRejection


def job_rejections(db: Session, job_id: str) -> list[ClipRejection]:
    return list(
        db.scalars(select(ClipRejection).where(ClipRejection.job_id == job_id).order_by(ClipRejection.created_at, ClipRejection.id))
    )


def rejection_ranges(rows: list[ClipRejection]) -> list[dict[str, Any]]:
    return [{"start": row.start, "end": row.end, "type": row.clip_type, "reason": row.reason, "note": row.note} for row in rows]
