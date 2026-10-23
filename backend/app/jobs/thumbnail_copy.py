import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.audio.transcribe_faster_whisper import transcript_output_path
from app.db import SessionLocal
from app.jobs.subtitle_review import load_subtitle_review, reviewed_transcript_output_path, subtitle_review_output_path
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.jobs.thumbnails import read_export_metadata
from app.models import ExportItem, Job
from app.scoring.thumbnail_copy import (
    THUMBNAIL_COPY_PROMPT_VERSION,
    THUMBNAIL_COPY_MAX_ATTEMPTS,
    CodexThumbnailCopyGenerator,
    ThumbnailCopyResult,
    ThumbnailCopySubjectError,
    ThumbnailCopySuggestion,
    validate_copy_evidence,
    validate_copy_subject,
)
from app.storage.paths import get_storage_paths


class ThumbnailCopyState(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    state: Literal["idle", "queued", "generating", "ready", "failed"] = "idle"
    request_id: str | None = Field(default=None, alias="requestId")
    suggestions: list[ThumbnailCopySuggestion] = Field(default_factory=list)
    recommended_id: str | None = Field(default=None, alias="recommendedId")
    subject_name: str = Field(default="", alias="subjectName")
    error: str | None = None


def copy_state_path(paths, export: ExportItem) -> Path:
    digest = sha256(export.id.encode()).hexdigest()[:24]
    return paths.job_outputs(export.job_id) / "thumbnail_copy_suggestions" / f"{digest}.json"


def confirmed_copy_state_path(paths, job_id: str, clip_id: str, content_hash: str) -> Path:
    digest = sha256(f"confirmed:{clip_id}:{content_hash}".encode()).hexdigest()[:24]
    return paths.job_outputs(job_id) / "thumbnail_copy_suggestions" / f"{digest}.json"


def read_copy_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"state": "idle"}


def write_copy_state(path: Path, state: dict) -> None:
    from app.production_choice_capture import capture_proposals
    state = capture_proposals(state, path, kind="thumbnail", policy_version=state.get("promptVersion"), clip_id=state.get("clipId"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{uuid4().hex}.tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def build_copy_input(db, paths, export: ExportItem) -> dict:
    job = db.get(Job, export.job_id)
    if not job or job.status != "completed" or export.type != "normal":
        raise ValueError("通常動画の書き出し完了後に生成できます。")
    video_path = paths.resolve_stored_file(export.video_path)
    job_dir = paths.job_outputs(export.job_id)
    video_path.resolve().relative_to(job_dir.resolve())
    video_stat = video_path.stat()
    metadata = read_export_metadata(export)
    start = float(metadata["start"])
    end = float(metadata.get("end", start + export.duration))
    if not 0 <= start < end:
        raise ValueError("完成動画の切り抜き範囲を確認できません。")
    review_path = subtitle_review_output_path(job_dir)
    if review_path.is_file():
        review = load_subtitle_review(review_path)
        clip = next((item for item in review.clips if item.id == export.candidate_id), None)
        if review.state != "completed" or clip is None or abs(clip.start - start) > 0.05 or abs(clip.end - end) > 0.05:
            raise ValueError("完成動画と保存済み字幕の範囲が一致しません。書き出し状態を確認してください。")
        ids = set(clip.segment_ids)
        source = [{"id": s.id, "start": s.start, "end": s.end, "text": s.text} for s in review.segments if s.id in ids]
    else:
        transcript_path = reviewed_transcript_output_path(job_dir)
        if not transcript_path.is_file():
            transcript_path = transcript_output_path(job_dir)
        if not transcript_path.is_file():
            raise ValueError("確定字幕が見つかりません。文言を手動で入力してください。")
        source = json.loads(transcript_path.read_text(encoding="utf-8"))
        source = [s for s in source if s.get("clip_id") in (None, export.candidate_id)]
    payload = build_copy_payload(source, start=start, end=end, publication_title=export.title)
    return copy_request(payload, start=start, end=end, video_stat=video_stat)


def build_copy_payload(source: list[dict], *, start: float, end: float, publication_title: str) -> dict:
    """Shared confirmed-subtitle input; callers enforce their own publication state."""
    segments = []
    for index, item in enumerate(source):
        if float(item["end"]) <= start or float(item["start"]) >= end or not str(item["text"]).strip():
            continue
        segments.append(
            {
                "segmentId": str(item.get("id") or f"segment_{index}"),
                "start": round(max(start, float(item["start"])) - start, 3),
                "end": round(min(end, float(item["end"])) - start, 3),
                "text": str(item["text"]).strip(),
            }
        )
    if not segments:
        raise ValueError("この完成動画の範囲に字幕がありません。文言を手動で入力してください。")
    payload = {"publicationTitle": publication_title, "clipDurationSeconds": end - start, "segments": segments}
    return payload


def copy_request(payload: dict, *, start: float, end: float, video_stat) -> dict:
    encoded = json.dumps(
        {
            "payload": payload,
            "start": start,
            "end": end,
            "videoSize": video_stat.st_size,
            "videoModified": video_stat.st_mtime_ns,
            "version": THUMBNAIL_COPY_PROMPT_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {"inputHash": sha256(encoded.encode()).hexdigest(), "payload": payload}


def queue_copy_generation(db, paths, export, enqueue, *, force: bool) -> ThumbnailCopyState:
    path = copy_state_path(paths, export)
    with subtitle_review_document_lock(paths.job_outputs(export.job_id)):
        request = build_copy_input(db, paths, export)
        previous = read_copy_state(path)
        if previous.get("inputHash") == request["inputHash"]:
            if previous.get("state") in {"queued", "generating"} or (previous.get("state") == "ready" and not force):
                return ThumbnailCopyState.model_validate(previous)
        next_state = {**request, "clipId": export.candidate_id, "requestId": uuid4().hex, "state": "queued",
                      "suggestions": [], "recommendedId": None, "error": None}
        write_copy_state(path, next_state)
        try:
            enqueue(export.id, next_state["requestId"])
        except Exception:
            write_copy_state(path, previous)
            raise
    return ThumbnailCopyState.model_validate(next_state)


def run_thumbnail_copy_generation(export_id: str, request_id: str, *, session_factory=SessionLocal, paths=None, generator=None):
    storage = paths or get_storage_paths()
    with session_factory() as db:
        export = db.get(ExportItem, export_id)
        if export is None:
            return
        path = copy_state_path(storage, export)
        job_dir = storage.job_outputs(export.job_id)
        try:
            with subtitle_review_document_lock(job_dir):
                state = read_copy_state(path)
                if state.get("requestId") != request_id or state.get("state") != "queued":
                    return
                request = build_copy_input(db, storage, export)
                if request["inputHash"] != state["inputHash"]:
                    raise ValueError("確定動画が更新されました。文言を再生成してください。")
                state["state"] = "generating"
                write_copy_state(path, state)
            active = generator or CodexThumbnailCopyGenerator(
                storage_root=storage.root,
                job_id=export.job_id,
                clip_id=f"thumb_{export.id}",
                model=os.environ.get("CODEX_TITLE_HOOK_MODEL", "codex-default"),
            )
            result = generate_validated_copy(active, request["payload"])
            with subtitle_review_document_lock(job_dir):
                latest = read_copy_state(path)
                if latest.get("requestId") != request_id:
                    return
                db.expire_all()
                if build_copy_input(db, storage, export)["inputHash"] != request["inputHash"]:
                    raise ValueError("確定動画が更新されました。文言を再生成してください。")
                write_copy_state(path, {**latest, **result.model_dump(by_alias=True), "state": "ready", "error": None,
                                        "promptVersion": THUMBNAIL_COPY_PROMPT_VERSION})
        except Exception as exc:
            with subtitle_review_document_lock(job_dir):
                latest = read_copy_state(path)
                if latest.get("requestId") != request_id:
                    return
                error = (
                    str(exc) if type(exc) is ValueError or isinstance(exc, ThumbnailCopySubjectError)
                    else "サムネ文言を生成できませんでした。Codexの接続を確認して再生成してください。"
                )
                write_copy_state(path, {**latest, "state": "failed", "error": error, "suggestions": []})


def generate_validated_copy(active, original_payload: dict) -> ThumbnailCopyResult:
    payload = original_payload
    for attempt in range(THUMBNAIL_COPY_MAX_ATTEMPTS):
        result = ThumbnailCopyResult.model_validate(active.generate(payload, []).model_dump(by_alias=True))
        try:
            if attempt and not result.subject_name:
                raise ThumbnailCopySubjectError("作り直した候補にも、話の中心の人物名がありません。")
            validate_copy_subject(result, payload["segments"], payload["publicationTitle"] or "")
        except ThumbnailCopySubjectError as exc:
            if attempt:
                raise ThumbnailCopySubjectError(f"サムネ文言を1回作り直しましたが、{exc}") from exc
            payload = {
                **original_payload,
                "correction": {
                    "reason": str(exc),
                    "previousResponse": result.model_dump(by_alias=True),
                    "instruction": (
                        "字幕・公開タイトルに実在する中心人物名をsubjectNameと全3案のupperかlowerに入れてください。"
                        "headingだけでは不可。"
                    ),
                },
            }
            continue
        validate_copy_evidence(result, payload["segments"])
        break
    return result
