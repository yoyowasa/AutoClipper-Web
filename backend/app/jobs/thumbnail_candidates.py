"""One sequential scan per normal export; all subsequent selection uses cached stills."""

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryFile
from uuid import uuid4
from typing import Literal

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.db import SessionLocal
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.models import ExportItem, Job, Video
from app.render.anime_subject import detect_anime_face
from app.render.render_thumbnail import extract_thumbnail_frame
from app.render.video_subject_layout import video_subject_layout
from app.storage.json_io import write_json_atomic
from app.storage.paths import get_storage_paths
from app.video.probe import probe_metadata


SCAN_WIDTH = 960
SCAN_FPS = 2
MAX_CANDIDATES = 12
NEAR_SECONDS = 3.0
MIN_SHARPNESS = 40.0
EMPTY_REASON = "顔が小さい、胸元が画面外、またはブレが大きく半身にできる場面がありません。"
PERSON_FRAME = {"width": 692, "height": 720, "face_target_x": 0.68}


class ThumbnailFrameRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    second: float
    score: float
    close_available: bool = Field(alias="closeAvailable")
    image_url: str = Field(alias="imageUrl")


class ThumbnailCandidatesState(BaseModel):
    state: Literal["idle", "queued", "ready", "failed"]
    candidates: list[ThumbnailFrameRead] = Field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True)
class ThumbnailFrameCandidate:
    second: float
    face: tuple[float, float, float, float]
    score: float
    face_hash: int


def candidate_directory(output_dir: Path, export_id: str) -> Path:
    # Hashing also permits older export identifiers without trusting path components.
    from hashlib import sha256
    return output_dir / "thumbnails" / "frames" / sha256(export_id.encode()).hexdigest()[:24]


def sequential_clip_frames(video: Path, start: float, end: float, size: tuple[int, int]):
    height = round(size[1] * SCAN_WIDTH / size[0])
    command = ["ffmpeg", "-v", "error", "-nostdin", "-ss", str(start), "-i", str(video), "-t", str(end - start),
               "-an", "-sn", "-dn", "-vf", f"fps={SCAN_FPS}:start_time=0:round=near,scale={SCAN_WIDTH}:{height},setsar=1",
               "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    with TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        assert process.stdout is not None
        frame_bytes = SCAN_WIDTH * height * 3
        index = 0
        try:
            while True:
                data = bytearray()
                while len(data) < frame_bytes:
                    part = process.stdout.read(frame_bytes - len(data))
                    if not part:
                        break
                    data.extend(part)
                if not data:
                    break
                if len(data) != frame_bytes:
                    raise RuntimeError("サムネ候補の走査中にフレームが途切れました。")
                if index / SCAN_FPS >= end - start:
                    continue
                yield index / SCAN_FPS, Image.frombytes("RGB", (SCAN_WIDTH, height), bytes(data))
                index += 1
            if process.wait() != 0:
                raise RuntimeError("サムネ候補の走査に失敗しました。")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def evaluate_thumbnail_frame(image, second, original_size, *, detector=detect_anime_face):
    face = detector(image)
    if face is None:
        return None
    cx, cy, fw, fh = face
    layout = video_subject_layout(original_size, face, PERSON_FRAME)
    if not layout.fits or min(fw, fh) <= 0:
        return None
    box = (max(0, round((cx - fw / 2) * image.width)), max(0, round((cy - fh / 2) * image.height)),
           min(image.width, round((cx + fw / 2) * image.width)), min(image.height, round((cy + fh / 2) * image.height)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    gray = np.asarray(image.crop(box).convert("L"))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharpness < MIN_SHARPNESS:
        return None
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    face_hash = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
    top_margin = min(1.0, (cy - fh / 2) / fh)
    chest_margin = min(1.0, (1 - cy - fh / 2) / (2 * fh))
    score = fh * 4 + chest_margin + top_margin * 0.4 + min(sharpness / 1000, 1) + (1 - abs(cx - .5) * 2) * .4
    return ThumbnailFrameCandidate(second, face, score, face_hash)


def thin_thumbnail_candidates(pool):
    selected = []
    for candidate in sorted(pool, key=lambda c: (-c.score, c.second)):
        if any(abs(candidate.second - other.second) <= NEAR_SECONDS
               and (candidate.face_hash ^ other.face_hash).bit_count() <= 12 for other in selected):
            continue
        selected.append(candidate)
        if len(selected) == MAX_CANDIDATES:
            break
    return selected


def extract_thumbnail_candidates(source, *, clip_start, clip_end, directory, scanner=sequential_clip_frames,
                                 extractor=extract_thumbnail_frame, detector=detect_anime_face):
    metadata = probe_metadata(source)
    if not metadata.width or not metadata.height or clip_end <= clip_start:
        raise ValueError("サムネ候補の動画範囲・解像度を確認できません。")
    size = (metadata.width, metadata.height)
    pool = []
    for second, image in scanner(Path(source), clip_start, clip_end, size):
        candidate = evaluate_thumbnail_frame(image, second, size, detector=detector)
        if candidate:
            pool.append(candidate)
    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    for candidate in thin_thumbnail_candidates(pool):
        candidate_id = f"frame_{len(saved):02d}"
        frame_path = directory / f"{candidate_id}.jpg"
        extractor(source, frame_path, clip_start + candidate.second)
        with Image.open(frame_path) as frame:
            face = detector(frame)
            if face is None or not video_subject_layout(frame.size, face, PERSON_FRAME).fits:
                frame_path.unlink(missing_ok=True)
                continue
            small = frame.convert("RGB")
            small.thumbnail((240, 135))
            small.save(directory / f"{candidate_id}.small.jpg", "JPEG", quality=85)
            saved.append({"id": candidate_id, "second": candidate.second, "face": list(face), "score": round(candidate.score, 4),
                          "width": frame.width, "height": frame.height,
                          "close_available": video_subject_layout(frame.size, face, PERSON_FRAME, mode="close").fits})
    return saved


def ensure_thumbnail_candidates(export, source, output_dir, *, extractor=None):
    from app.jobs.thumbnails import read_export_metadata, write_export_metadata
    directory = candidate_directory(Path(output_dir), export.id)
    # Polling HTTP requests lock only the short state transition, never the scan.
    with subtitle_review_document_lock(directory / "scan", timeout_seconds=600, stale_seconds=900):
        payload = read_export_metadata(export)
        if payload.get("thumbnail_candidates_version") == 1:
            return payload.get("thumbnail_frame_candidates", [])
        start = float(payload.get("start", 0))
        candidates = (extractor or extract_thumbnail_candidates)(
            source, clip_start=start, clip_end=float(payload.get("end", start + export.duration)), directory=directory)
        with subtitle_review_document_lock(directory):
            latest = read_export_metadata(export)
            write_export_metadata(export.metadata_path, {**latest, "thumbnail_candidates_version": 1,
                                  "thumbnail_frame_candidates": candidates,
                                  "thumbnail_candidates_reason": None if candidates else EMPTY_REASON})
        return candidates


def selected_frame(payload, *, candidate_id=None):
    candidates = payload.get("thumbnail_frame_candidates", [])
    requested = candidate_id or payload.get("thumbnail_frame_candidate_id")
    if requested:
        return next((c for c in candidates if c["id"] == requested), None)
    second = float(payload.get("thumbnail_frame_seconds", -1))
    return next((c for c in candidates if abs(c["second"] - second) < .001), None)


def video_candidate_kwargs(payload, output_dir, export_id, *, candidate_id=None, mode="standard"):
    candidate = selected_frame(payload, candidate_id=candidate_id)
    if not candidate:
        return {}
    if mode == "close" and not candidate["close_available"]:
        raise ValueError("この候補は2倍以内の拡大で顔のアップにできません。")
    return {"source_frame_path": candidate_directory(Path(output_dir), export_id) / f'{candidate["id"]}.jpg',
            "video_face": tuple(candidate["face"]), "video_crop_mode": mode}


def candidate_state(export, output_dir):
    from app.jobs.thumbnails import read_export_metadata
    payload = read_export_metadata(export)
    if payload.get("thumbnail_candidates_version") == 1:
        return {"state": "ready", "candidates": [
            {"id": c["id"], "second": c["second"], "score": c["score"], "closeAvailable": c["close_available"],
             "imageUrl": f'/api/exports/{export.id}/thumbnail/candidates/{c["id"]}/image'}
            for c in payload.get("thumbnail_frame_candidates", [])], "reason": payload.get("thumbnail_candidates_reason")}
    path = candidate_directory(Path(output_dir), export.id) / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"state": "idle", "candidates": []}


def prepare_candidates(db, paths, export, enqueue, *, force=False):
    directory = candidate_directory(paths.job_outputs(export.job_id), export.id)
    with subtitle_review_document_lock(directory):
        state = candidate_state(export, paths.job_outputs(export.job_id))
        if state["state"] != "idle" and not (force and state["state"] == "failed"):
            return state
        job = db.get(Job, export.job_id)
        if export.type != "normal" or not job or job.status != "completed":
            raise ValueError("完成した通常動画だけが対象です。")
        state = {"state": "queued", "requestId": uuid4().hex, "candidates": []}
        write_json_atomic(directory / "state.json", state)
        try:
            enqueue(export.id, state["requestId"])
        except Exception:
            (directory / "state.json").unlink(missing_ok=True)
            raise
        return state


def run_thumbnail_candidate_extraction(export_id, request_id, *, session_factory=SessionLocal, paths=None):
    storage = paths or get_storage_paths()
    with session_factory() as db:
        export = db.get(ExportItem, export_id)
        if export is None:
            return
        directory = candidate_directory(storage.job_outputs(export.job_id), export.id)
        with subtitle_review_document_lock(directory):
            state = candidate_state(export, storage.job_outputs(export.job_id))
            if state.get("requestId") != request_id or state["state"] != "queued":
                return
        try:
            video = db.get(Video, export.video_id)
            if video is None:
                raise ValueError("元動画がありません。")
            ensure_thumbnail_candidates(export, storage.resolve_stored_file(video.stored_path), storage.job_outputs(export.job_id))
        except Exception:
            write_json_atomic(directory / "state.json", {**state, "state": "failed", "reason": "候補を抽出できませんでした。"})
