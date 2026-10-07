"""Worker heartbeat policy shared by API fallback and worker maintenance."""

from typing import Any

from app.jobs.status import PROGRESS_MAP

DEFAULT_STALE_WORKER_SECONDS = 1800
NON_RUNNING_STATUSES = {
    "uploaded", "queued", "awaiting_manual_edit", "awaiting_clip_review", "awaiting_subtitle_review", "completed", "failed",
}
RUNNING_STATUSES = frozenset(PROGRESS_MAP) - NON_RUNNING_STATUSES


def stale_worker_timeout_seconds(settings: dict[str, Any]) -> int:
    try:
        parsed = int(settings.get("workerHeartbeatTimeoutSeconds", DEFAULT_STALE_WORKER_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_STALE_WORKER_SECONDS
    return max(60, parsed)
