"""RQ budgets for long clips; no media processing is performed while enqueueing."""

import json
import math

from sqlalchemy import inspect

from app.clip_allocation import is_ai_allocation
from app.db import SessionLocal
from app.duration_rules import NORMAL_LONGFORM_MAX_SECONDS, effective_short_max
from app.models import ExportItem, Job, Video
from app.storage.paths import get_storage_paths


def media_timeout(duration: float, *, minimum: int = 3600, factor: float = 6.0) -> int:
    # Allow 6x media time plus ten minutes for setup/I/O. This is a budget,
    # not a measured throughput guarantee on every CPU/GPU.
    return max(minimum, math.ceil(max(0.0, duration) * factor + 600))


def job_media_timeout(
    job_id: str, *, clip_id: str | None = None, proposed_duration: float | None = None, selection: bool = False,
) -> int:
    if proposed_duration is not None:
        return media_timeout(proposed_duration)
    output = get_storage_paths().job_outputs(job_id)
    for name in (() if selection else ("subtitle_review.json", "clip_plan.json", "selected_clips.json")):
        path = output / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        clips = payload.get("clips", payload.get("normalClips", []) + payload.get("shorts", []))
        durations = [float(clip["end"]) - float(clip["start"]) +
                     (float(clip.get("hookSceneEnd") or 0) - float(clip.get("hookSceneStart") or 0)
                      if clip["type"] == "short" else 0)
                     for clip in clips if clip_id is None or clip["id"] == clip_id]
        if durations:
            return media_timeout(sum(durations))
    # Initial selection has no clip plan yet: reserve enough time for the
    # requested clips, including content-based longform candidates.
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("jobs"):
            return 3600
        job = db.get(Job, job_id)
        if job is None:
            return 3600
        settings = job.settings_json or {}
        video = db.get(Video, job.video_id)
        maximum = min(NORMAL_LONGFORM_MAX_SECONDS, video.duration) if video and video.duration else NORMAL_LONGFORM_MAX_SECONDS
        if is_ai_allocation(settings):
            duration = maximum * int(settings["totalClipCount"])
        else:
            duration = (maximum * int(settings.get("normalClipCount", 2))
                        + effective_short_max(settings) * int(settings.get("shortCount", 3)))
        return media_timeout(maximum if clip_id is not None else duration)


def thumbnail_candidates_timeout(export_id: str) -> int:
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("export_items"):
            return 600
        export = db.get(ExportItem, export_id)
        if export is None:
            return 600
        # 2 frames/sec: reserve up to one second per frame, plus video decoding
        # at realtime and ten minutes for the twelve full-resolution stills.
        return media_timeout(export.duration, minimum=600, factor=3)
