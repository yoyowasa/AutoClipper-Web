"""Shared persisted subtitle-review states for route and pipeline tests."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Job
from app.storage.paths import StoragePaths


def seed_legacy_reopened_review(storage: StoragePaths, db: Session, job_id: str) -> dict[str, Any]:
    """Persist the state left by the retired full-job reopen route."""
    review_path = storage.job_outputs(job_id) / "subtitle_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review.update(
        state="awaiting_review",
        renderRevision=int(review["renderRevision"]) + 1,
        reopenedAt="2026-01-01T00:00:00+00:00",
        confirmedClipCount=0,
    )
    for clip in review["clips"]:
        clip["confirmed"] = False
    review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    job = db.get(Job, job_id)
    assert job is not None
    job.status = "awaiting_subtitle_review"
    db.commit()
    return review
