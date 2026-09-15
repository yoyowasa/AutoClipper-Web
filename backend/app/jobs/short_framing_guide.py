"""Cache composition analysis once; browser crop adjustments need no encoding."""

import json
import time
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.db import SessionLocal
from app.jobs.subtitle_review import load_subtitle_review, subtitle_review_output_path
from app.jobs.subtitle_review_preview import load_subtitle_review_preview_inputs, subtitle_review_document_lock
from app.models import Job, Video
from app.render.render_short import resolve_short_crop_plan
from app.storage.paths import get_storage_paths
from app.video.face_detect import best_face_center
from app.video.speaker_detect import dialogue_windows_for_clip


class ShortFramingGuide(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    state: Literal["queued", "ready", "failed"]
    key: str
    width: int
    height: int
    content_height: int = Field(alias="contentHeight")
    content_y: int = Field(alias="contentY")
    strategy: str = "center_crop"
    center: tuple[float, float] = (0.5, 0.5)
    error: str | None = None


def guide_context(db, paths, job_id, clip_id, layout=None):
    job = db.get(Job, job_id)
    if job is None:
        raise FileNotFoundError("job not found")
    video = db.get(Video, job.video_id)
    document = load_subtitle_review(subtitle_review_output_path(paths.job_outputs(job.id)))
    clip = next((c for c in document.clips if c.id == clip_id), None)
    if video is None or clip is None or clip.type != "short":
        raise ValueError("short clip not found")
    inputs = load_subtitle_review_preview_inputs(job=job, video=video, document=document, paths=paths, clip_id=clip_id)
    source = paths.resolve_stored_file(video.stored_path)
    stat = source.stat()
    if not video.width or not video.height:
        raise ValueError("source dimensions unavailable")
    top = 360 if document.short_top_banner_enabled else 0
    content_height = 1920 - top - (360 if document.short_bottom_banner_enabled else 0)
    candidate = inputs.candidate
    layout = layout or clip.short_layout or document.short_layout
    windows = dialogue_windows_for_clip(candidate.start, candidate.end, inputs.transcript_segments)
    key = sha256(json.dumps([
        str(source), stat.st_size, stat.st_mtime_ns, candidate.start, candidate.end,
        layout, content_height, top, [(w.start, w.end) for w in windows],
    ]).encode()).hexdigest()
    return {
        "key": key, "source": source, "start": candidate.start, "end": candidate.end,
        "layout": layout, "width": video.width, "height": video.height,
        "contentHeight": content_height, "contentY": top, "windows": windows,
    }


def guide_dir(paths, job_id, clip_id):
    return paths.temp / "short-framing-guide" / sha256(f"{job_id}:{clip_id}".encode()).hexdigest()[:24]


def read_state(directory):
    file = directory / "state.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else {}


def write_state(directory, state):
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"{uuid4().hex}.tmp"
    temp.write_text(json.dumps(state), encoding="utf-8")
    temp.replace(directory / "state.json")


def prepare_framing_guide(db, paths, job_id, clip_id, enqueue, *, force=False, layout=None):
    ctx = guide_context(db, paths, job_id, clip_id, layout)
    directory = guide_dir(paths, job_id, clip_id)
    with subtitle_review_document_lock(directory):
        cached = directory / f"ready-{ctx['key']}.json"
        if cached.is_file() and not force:
            return ShortFramingGuide.model_validate_json(cached.read_text(encoding="utf-8"))
        # These layouts depend only on dimensions; do not wait behind video encoding.
        if ctx["layout"] in {"center_crop", "blur_background"}:
            return ShortFramingGuide.model_validate({
                **ctx, "state": "ready", "strategy": ctx["layout"], "center": (0.5, 0.5),
            })
        old = read_state(directory)
        if old.get("key") == ctx["key"]:
            if old.get("state") == "ready" or (old.get("state") == "failed" and not force):
                return ShortFramingGuide.model_validate(old)
            if old.get("state") == "queued" and time.time() - old.get("created", 0) < 180:
                return ShortFramingGuide.model_validate(old)
        state = {k: ctx[k] for k in ("key", "width", "height", "contentHeight", "contentY")}
        state.update(state="queued", requestId=uuid4().hex, created=time.time())
        write_state(directory, state)
        try:
            if layout is None:
                enqueue(job_id, clip_id, state["requestId"])
            else:
                enqueue(job_id, clip_id, state["requestId"], layout)
        except Exception:
            write_state(directory, old)
            raise
    return ShortFramingGuide.model_validate(state)


def run_short_framing_guide(
    job_id, clip_id, request_id, layout=None, *, session_factory=SessionLocal, paths=None, resolver=resolve_short_crop_plan,
):
    storage = paths or get_storage_paths()
    directory = guide_dir(storage, job_id, clip_id)
    with session_factory() as db:
        try:
            state = read_state(directory)
            if state.get("requestId") != request_id or state.get("state") != "queued":
                return
            ctx = guide_context(db, storage, job_id, clip_id, layout)
            if ctx["key"] != state["key"]:
                raise ValueError("context changed")
            plan, faces = resolver(
                ctx["source"], ctx["start"], ctx["end"], layout=ctx["layout"],
                width=ctx["width"], height=ctx["height"], target_height=ctx["contentHeight"], dialogue_windows=ctx["windows"],
            )
            strategy = plan.strategy_order[0]
            center = {
                "face_tracking_crop": plan.face_center or best_face_center(faces),
                "speaker_tracking_crop": plan.speaker_center, "person_tracking_crop": plan.person_center,
                "subject_tracking_crop": plan.subject_center,
            }.get(strategy) or (0.5, 0.5)
            with subtitle_review_document_lock(directory):
                if read_state(directory).get("requestId") != request_id:
                    return
                if guide_context(db, storage, job_id, clip_id, layout)["key"] != ctx["key"]:
                    raise ValueError("context changed")
                ready = {**state, "state": "ready", "strategy": strategy, "center": center}
                write_state(directory, ready)
                (directory / f"ready-{ctx['key']}.json").write_text(json.dumps(ready), encoding="utf-8")
        except Exception:
            with subtitle_review_document_lock(directory):
                current = read_state(directory)
                if current.get("requestId") == request_id:
                    write_state(directory, {**current, "state": "failed", "error": "画角の基準を読み込めませんでした。"})
