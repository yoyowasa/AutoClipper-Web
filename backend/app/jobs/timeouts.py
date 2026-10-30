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
            repair_duration = 0.0
            if name == "subtitle_review.json" and payload.get("subtitleOnlyAuto") and clip_id is None:
                from app.jobs.automatic_framing_repair import FRAMING_REPAIR_MAX_ATTEMPTS
                repair_duration = FRAMING_REPAIR_MAX_ATTEMPTS * sum(
                    duration for clip, duration in zip(clips, durations, strict=True)
                    if clip["type"] == "short" and "framing" not in clip.get("manualDecisionFields", [])
                )
            return media_timeout(sum(durations) + repair_duration)
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
        timeout = media_timeout(maximum if clip_id is not None else duration)
        if clip_id is None and not selection:
            # Reserve realtime for each of primary ASR and repair, in addition to the
            # rendering budget. Uploads may not have probed duration at enqueue time:
            # use three hours then, matching the long inputs measured in task-186.
            source_duration = video.duration if video and video.duration else 3 * 3600
            timeout += math.ceil(2 * source_duration)
        return timeout


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


def automatic_thumbnail_copy_timeout(job_id: str) -> int:
    """Additional bounded Codex waits only for the new human-review auto policy."""
    from app.jobs.automation import requires_human_subtitle_review
    from app.scoring.codex_title_hook_suggestions import DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS
    from app.scoring.thumbnail_copy import THUMBNAIL_COPY_MAX_ATTEMPTS
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("jobs"):
            return 0
        job = db.get(Job, job_id)
        if job is None or not requires_human_subtitle_review(job.settings_json or {}):
            return 0
    path = get_storage_paths().job_outputs(job_id) / "subtitle_review.json"
    if not path.is_file():
        return 0
    count = sum(clip["type"] == "normal" for clip in json.loads(path.read_text(encoding="utf-8"))["clips"])
    return math.ceil(count * THUMBNAIL_COPY_MAX_ATTEMPTS * DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS)


def final_output_inspection_timeout(job_id: str) -> int:
    """Reserve scans for three passes, two renders, and one content regeneration."""
    from app.inspection.models import MAX_REPAIRS, SEMANTIC_TIMEOUT_SECONDS
    path = get_storage_paths().job_outputs(job_id) / "subtitle_review.json"
    if path.is_file():
        document = json.loads(path.read_text(encoding="utf-8"))
        targets = document.get("renderClipIds")
        clips = [c for c in document.get("clips", []) if targets is None or c["id"] in targets]
        count = len(clips)
        duration = sum(max(0, float(c["end"]) - float(c["start"])) + max(
            0, float(c.get("hookSceneEnd") or 0) - float(c.get("hookSceneStart") or 0)) for c in clips)
    else:
        with SessionLocal() as db:
            if not inspect(db.get_bind()).has_table("jobs"):
                return 0
            job = db.get(Job, job_id)
            if job is None:
                return 0
            settings = job.settings_json or {}
            count = int(settings["totalClipCount"]) if is_ai_allocation(settings) else (
                int(settings.get("normalClipCount", 2)) + int(settings.get("shortCount", 3)))
            duration = NORMAL_LONGFORM_MAX_SECONDS * count
    from app.scoring.codex_title_hook_suggestions import DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS
    from app.scoring.thumbnail_copy import THUMBNAIL_COPY_MAX_ATTEMPTS
    # Each pass decodes output/source and two subtitle rasters. Regeneration is
    # permitted once and uses the existing bounded title/copy retry policies.
    local_factor = MAX_REPAIRS * 6 + (MAX_REPAIRS + 1) * 4
    waits = (MAX_REPAIRS + 1) * (SEMANTIC_TIMEOUT_SECONDS + 15) + (
        2 + THUMBNAIL_COPY_MAX_ATTEMPTS) * DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS
    return media_timeout(duration, minimum=300, factor=local_factor) + math.ceil(count * waits) if count else 0
