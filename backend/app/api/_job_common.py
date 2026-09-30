import json
from pathlib import Path
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.jobs.automation import (
    automation_manifest_path,
    load_automation_manifest,
)
from app.jobs.quality_gate import (
    QualityGateDecision,
    QualityGateMode,
    evaluate_content_quality_gate,
    invalidate_quality_gate_decisions,
    quality_gate_decision_path,
    unknown_quality_gate_decision,
    write_quality_gate_decision,
)
from app.jobs.queue import (
    SubtitleReviewPreviewEnqueue,
)
from app.jobs.status import PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    load_subtitle_review,
    subtitle_review_output_path,
    subtitle_review_summary_path,
    write_subtitle_review,
    write_subtitle_review_summary,
)
from app.jobs.subtitle_review_preview import (
    refresh_subtitle_review_preview_states,
    subtitle_review_document_lock,
)
from app.jobs.title_hook_suggestions import (
    TitleHookSuggestionsDocument,
    load_title_hook_suggestions,
    title_hook_suggestions_path,
)
from app.models import Job, Video
from app.models import utc_now
from app.schemas import (
    JobSettings,
    ShortLayout,
    ShortOverlayTitleMode,
)
from app.storage.paths import StoragePaths

def _validated_persisted_job_settings(
    settings: dict[str, Any] | None,
) -> JobSettings:
    payload = dict(settings or {})
    payload.setdefault("shortTopBannerEnabled", False)
    payload.setdefault("shortBottomBannerEnabled", False)
    payload.setdefault("shortSubtitleYPercent", None)
    return JobSettings.model_validate(payload, context={"persisted_job": True})

def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job

def _get_subtitle_review_or_404(job_id: str, paths: StoragePaths) -> SubtitleReviewDocument:
    review_path = subtitle_review_output_path(paths.job_outputs(job_id))
    if not review_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subtitle review not found")
    try:
        return load_subtitle_review(review_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="subtitle review artifact is invalid",
        ) from exc

def _claim_job_status(
    db: Session,
    job: Job,
    *,
    expected: str,
    new_status: str,
    current_step: str,
) -> None:
    result = db.execute(
        update(Job)
        .where(Job.id == job.id, Job.status == expected)
        .values(
            status=new_status,
            progress=PROGRESS_MAP[new_status],
            current_step=current_step,
            error_code=None,
            error_message=None,
            updated_at=utc_now(),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "job state changed; reload")
    db.commit()
    db.refresh(job)

def _write_subtitle_review_unlocked(
    document: SubtitleReviewDocument,
    paths: StoragePaths,
) -> None:
    output_dir = paths.job_outputs(document.job_id)
    invalidate_quality_gate_decisions(output_dir, ("content", "post_render"))
    write_subtitle_review(document, subtitle_review_output_path(output_dir))
    write_subtitle_review_summary(document, subtitle_review_summary_path(output_dir))

def _refresh_subtitle_review_previews_unlocked(
    *,
    job: Job,
    video: Video,
    document: SubtitleReviewDocument,
    paths: StoragePaths,
    clip_ids: set[str] | None = None,
) -> tuple[SubtitleReviewDocument, list[tuple[str, str]]]:
    document, queued, changed = refresh_subtitle_review_preview_states(
        job=job,
        video=video,
        document=document,
        paths=paths,
        clip_ids=clip_ids,
    )
    if changed:
        _write_subtitle_review_unlocked(document, paths)
    return document, queued

def _enqueue_subtitle_review_previews(
    *,
    job_id: str,
    document: SubtitleReviewDocument,
    queued: list[tuple[str, str]],
    paths: StoragePaths,
    enqueue_preview: SubtitleReviewPreviewEnqueue,
) -> SubtitleReviewDocument:
    enqueue_failures: list[tuple[str, str]] = []
    for clip_id, spec_hash in queued:
        try:
            enqueue_preview(job_id, clip_id, spec_hash)
        except Exception:
            enqueue_failures.append((clip_id, spec_hash))
    if not enqueue_failures:
        return document

    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        latest = _get_subtitle_review_or_404(job_id, paths)
        changed = False
        for clip_id, spec_hash in enqueue_failures:
            clip = next((item for item in latest.clips if item.id == clip_id), None)
            if clip is None or clip.preview_spec_hash != spec_hash:
                continue
            clip.preview_state = "failed"
            clip.preview_video_url = None
            clip.preview_error = "could not queue preview rendering"
            clip.confirmed = False
            changed = True
        if changed:
            latest.confirmed_clip_count = sum(1 for clip in latest.clips if clip.confirmed)
            _write_subtitle_review_unlocked(latest, paths)
        return latest

def _short_overlay_title_mode(settings: dict[str, Any]) -> ShortOverlayTitleMode:
    value = settings.get("shortOverlayTitleMode", "auto")
    if value == "auto":
        return "auto"
    if value == "always":
        return "always"
    if value == "high_quality_only":
        return "high_quality_only"
    if value == "never":
        return "never"
    return "auto"

def _short_layout(settings: dict[str, Any]) -> ShortLayout:
    value = settings.get("shortLayout", "auto")
    if value == "face_tracking_crop":
        return "face_tracking_crop"
    if value == "center_crop":
        return "center_crop"
    if value == "blur_background":
        return "blur_background"
    return "auto"

def _read_json_if_exists(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

def _write_json_payload(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path

def _job_quality_gate_mode(
    job: Job,
    output_dir: Path,
) -> QualityGateMode | None:
    manifest_path = automation_manifest_path(output_dir)
    if manifest_path.is_file():
        try:
            effective_mode = load_automation_manifest(manifest_path).effective_mode
        except (OSError, ValueError):
            pass
        else:
            return (
                effective_mode
                if effective_mode in {"shadow", "guarded", "auto"}
                else None
            )
    requested_mode = str(
        (job.settings_json or {}).get("automationMode") or "manual"
    ).strip()
    return (
        requested_mode
        if requested_mode in {"shadow", "guarded", "auto"}
        else None
    )

def _evaluate_and_write_content_quality_gate(
    *,
    job: Job,
    document: SubtitleReviewDocument,
    output_dir: Path,
) -> QualityGateDecision | None:
    mode = _job_quality_gate_mode(job, output_dir)
    if mode is None:
        return None
    title_hook_evidence: dict[str, TitleHookSuggestionsDocument] = {}
    if mode == "auto":
        for clip in document.clips:
            artifact_path = title_hook_suggestions_path(output_dir, clip.id)
            if not artifact_path.is_file():
                continue
            try:
                artifact = load_title_hook_suggestions(artifact_path)
            except (OSError, ValueError):
                continue
            if artifact.clip_id == clip.id:
                title_hook_evidence[clip.id] = artifact
    try:
        content_gate = evaluate_content_quality_gate(
            job_id=job.id,
            document=document,
            settings=dict(job.settings_json or {}),
            mode=mode,
            title_hook_evidence=title_hook_evidence,
        )
    except Exception as exc:
        content_gate = unknown_quality_gate_decision(
            job_id=job.id,
            stage="content",
            reason_code="content_gate_evaluation_failed",
            evidence={"errorType": exc.__class__.__name__},
            mode=mode,
        )
    try:
        write_quality_gate_decision(
            content_gate,
            quality_gate_decision_path(output_dir, "content"),
        )
    except OSError:
        return None
    return content_gate

def _write_content_quality_gate(
    *,
    job: Job,
    document: SubtitleReviewDocument,
    output_dir: Path,
) -> bool:
    return (
        _evaluate_and_write_content_quality_gate(
            job=job,
            document=document,
            output_dir=output_dir,
        )
        is not None
    )
