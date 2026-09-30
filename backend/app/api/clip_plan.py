from app.jobs.reselection_keep import target_count
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.audio.transcribe_faster_whisper import (
    TranscriptSegment,
)
from app.audio.transcript_postprocess import repair_known_transcript_artifact_segments
from app.candidates.select_candidates import (
    CandidateSelection,
    convert_selected_clip_to_normal,
    convert_selected_clip_to_short,
)
from app.db import get_db
from app.ids import make_id
from app.jobs.automation import (
    AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING,
)
from app.jobs.clip_plan import (
    ClipPlanClip,
    ClipPlanDocument,
    clip_plan_output_path,
    convert_clip_plan_clip_to_normal,
    convert_clip_plan_clip_to_short,
    load_clip_plan,
    mark_clip_plan_approved,
    update_clip_plan_boundary,
    update_clip_plan_hook_scene as update_clip_plan_hook_scene_document,
    write_clip_plan,
)
from app.jobs.hook_scene import hook_scene_newly_exceeds_short_limit
from app.jobs.manual_workflow import (
    is_manual_workflow,
    manual_plan_settings,
    touch_manual_document,
    validate_manual_clip_counts,
)
from app.jobs.queue import (
    ClipPlanBoundaryUpdateEnqueue,
    ClipPlanHookSceneUpdateEnqueue,
    ClipPlanReselectionEnqueue,
    JobEnqueue,
    SubtitleReviewPreviewEnqueue,
    get_enqueue_clip_plan_boundary_update,
    get_enqueue_clip_plan_hook_scene_update,
    get_enqueue_clip_plan_reselection,
    get_enqueue_job,
    get_enqueue_subtitle_review_preview,
)
from app.jobs.status import CURRENT_STEP_MAP, PROGRESS_MAP
from app.jobs.subtitle_review import (
    SubtitleReviewDocument,
    build_subtitle_review,
    retain_review_after_boundary_reedit,
    subtitle_review_preview_path,
)
from app.jobs.subtitle_review_preview import (
    subtitle_review_document_lock,
)
from app.models import Job, Video
from app.models import utc_now
from app.schemas import (
    ClipPlanActionResponse,
    ClipPlanBoundaryUpdateRequest,
    ClipPlanHookSceneUpdateRequest,
    ClipPlanReselectionRequest,
    ClipPlanTypeUpdateRequest,
    ManualClipCreateRequest,
    ManualClipUpdateRequest,
)
from app.storage.paths import StoragePaths, get_storage_paths

from app.api._job_common import (
    _claim_job_status,
    _enqueue_subtitle_review_previews,
    _get_job_or_404,
    _get_subtitle_review_or_404,
    _job_quality_gate_mode,
    _read_json_if_exists,
    _refresh_subtitle_review_previews_unlocked,
    _short_layout,
    _short_overlay_title_mode,
    _validated_persisted_job_settings,
    _write_content_quality_gate,
    _write_json_payload,
    _write_subtitle_review_unlocked,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_clip_plan_or_404(
    job_id: str,
    paths: StoragePaths,
) -> ClipPlanDocument:
    plan_path = clip_plan_output_path(paths.job_outputs(job_id))
    if not plan_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan not found",
        )
    try:
        return load_clip_plan(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="clip plan artifact is invalid",
        ) from exc

def _get_manual_edit_context(
    db: Session,
    job_id: str,
    paths: StoragePaths,
) -> tuple[Job, Video, ClipPlanDocument]:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_manual_edit" or not is_manual_workflow(
        dict(job.settings_json or {})
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manual clip plan is not editable",
        )
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="video not found",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.state != "manual_editing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manual clip plan is not editable",
        )
    return job, video, document

def _validate_manual_clip_range(
    video: Video,
    document: ClipPlanDocument,
    *,
    start: float,
    end: float,
) -> None:
    if end <= start or end - start < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="manual clip duration must be at least 1 second",
        )
    source_duration = float(video.duration or document.source_duration or 0)
    if source_duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video duration is unavailable",
        )
    if end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )

def _persist_subtitle_review(document: SubtitleReviewDocument, paths: StoragePaths) -> None:
    output_dir = paths.job_outputs(document.job_id)
    with subtitle_review_document_lock(output_dir):
        _write_subtitle_review_unlocked(document, paths)

@router.get("/{job_id}/clip-plan", response_model=ClipPlanDocument)
def get_clip_plan(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    _get_job_or_404(db, job_id)
    return _get_clip_plan_or_404(job_id, paths)

@router.post(
    "/{job_id}/clip-plan/clips",
    response_model=ClipPlanDocument,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_clip(
    job_id: str,
    request: ManualClipCreateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job, video, document = _get_manual_edit_context(db, job_id, paths)
    _validate_manual_clip_range(
        video,
        document,
        start=request.start,
        end=request.end,
    )
    type_index = sum(clip.type == request.type for clip in document.clips) + 1
    default_title = "通常切り抜き" if request.type == "normal" else "ショート"
    clip = ClipPlanClip(
        id=make_id("clip"),
        type=request.type,
        title=request.title.strip() or f"{default_title} {type_index:02d}",
        start=round(request.start, 3),
        end=round(request.end, 3),
        duration=round(request.end - request.start, 3),
        selectionReason="manual_edit",
        recommendedStart=round(request.start, 3),
        recommendedEnd=round(request.end, 3),
        manuallyAdjusted=True,
    )
    document.clips.append(clip)
    try:
        validate_manual_clip_counts(document.clips)
    except ValueError as exc:
        document.clips.pop()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document

@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}",
    response_model=ClipPlanDocument,
)
def update_manual_clip(
    job_id: str,
    clip_id: str,
    request: ManualClipUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job, video, document = _get_manual_edit_context(db, job_id, paths)
    clip_index = next(
        (index for index, clip in enumerate(document.clips) if clip.id == clip_id),
        None,
    )
    if clip_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    current = document.clips[clip_index]
    start = current.start if request.start is None else request.start
    end = current.end if request.end is None else request.end
    clip_type = request.type or current.type
    _validate_manual_clip_range(video, document, start=start, end=end)
    payload = current.model_dump()
    payload.update(
        {
            "type": clip_type,
            "title": current.title if request.title is None else request.title.strip(),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "manually_adjusted": True,
        }
    )
    try:
        updated = ClipPlanClip.model_validate(payload)
        proposed = list(document.clips)
        proposed[clip_index] = updated
        validate_manual_clip_counts(proposed)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    document.clips = proposed
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document

@router.delete(
    "/{job_id}/clip-plan/clips/{clip_id}",
    response_model=ClipPlanDocument,
)
def delete_manual_clip(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    _job, _video, document = _get_manual_edit_context(db, job_id, paths)
    original_count = len(document.clips)
    document.clips = [clip for clip in document.clips if clip.id != clip_id]
    if len(document.clips) == original_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    touch_manual_document(document)
    write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    return document

@router.get(
    "/{job_id}/clip-plan/clips/{clip_id}/transcript-segments",
    response_model=list[TranscriptSegment],
)
def get_clip_plan_transcript_segments(
    job_id: str,
    clip_id: str,
    start: float,
    end: float,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> list[TranscriptSegment]:
    job = _get_job_or_404(db, job_id)
    document = _get_clip_plan_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in document.clips):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    if start < 0 or end <= start or end - start < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid clip transcript range",
        )
    video = db.get(Video, job.video_id)
    source_duration = float((video.duration if video is not None else None) or document.source_duration or 0)
    if source_duration > 0 and end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )

    transcript_payload = _read_json_if_exists(paths.job_outputs(job_id) / "transcript_segments.json")
    if not isinstance(transcript_payload, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="transcript segments are unavailable",
        )
    transcript_segments = [TranscriptSegment.model_validate(item) for item in transcript_payload]
    transcript_segments = repair_known_transcript_artifact_segments(transcript_segments)
    return [segment for segment in transcript_segments if segment.end > start and segment.start < end]

@router.get("/{job_id}/clip-plan/clips/{clip_id}/preview-video")
def get_clip_plan_preview_video(
    job_id: str,
    clip_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    _get_job_or_404(db, job_id)
    document = _get_clip_plan_or_404(job_id, paths)
    if not any(clip.id == clip_id for clip in document.clips):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    preview_path = subtitle_review_preview_path(
        paths.job_outputs(job_id),
        clip_id,
    )
    if not preview_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan preview not found",
        )
    return FileResponse(preview_path, media_type="video/mp4")

@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/type",
    response_model=ClipPlanDocument,
)
def update_clip_plan_clip_type(
    job_id: str,
    clip_id: str,
    request: ClipPlanTypeUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanDocument:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting type adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.boundary_reedit:
        raise HTTPException(status.HTTP_409_CONFLICT, "字幕編集から戻った場合は尺だけ変更できます。")
    if document.state != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting type adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    output_dir = paths.job_outputs(job_id)
    selected_path = output_dir / "selected_clips.json"
    selected_payload = _read_json_if_exists(selected_path)
    if not isinstance(selected_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="selected clip data is unavailable",
        )
    try:
        selection = CandidateSelection.model_validate(selected_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="selected clip data is invalid",
        ) from exc
    if request.type == "normal" and planned_clip.type == "short" and len(selection.normal_clips) >= 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="normal clip count cannot exceed 12",
        )
    if request.type == "short" and planned_clip.type == "normal":
        if len(selection.shorts) >= 24:
            raise HTTPException(status_code=422, detail="short clip count cannot exceed 24")
        limit = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
        if planned_clip.duration > limit + 0.001:
            raise HTTPException(
                status_code=422,
                detail=f"ショートの上限は{limit:g}秒です。開始・終了を調整し、プレビュー更新後に変更してください。",
            )
    try:
        if request.type == "normal":
            converted_selection = convert_selected_clip_to_normal(selection, clip_id)
            convert_clip_plan_clip_to_normal(document, clip_id)
        else:
            converted_selection = convert_selected_clip_to_short(selection, clip_id)
            convert_clip_plan_clip_to_short(document, clip_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    next_settings = {
        **dict(job.settings_json or {}),
        "normalClipCount": len(converted_selection.normal_clips),
        "shortCount": len(converted_selection.shorts),
    }
    document.settings = {
        **document.settings,
        "normalClipCount": len(converted_selection.normal_clips),
        "shortCount": len(converted_selection.shorts),
    }
    plan_path = clip_plan_output_path(output_dir)
    artifact_snapshot = {
        selected_path: selected_path.read_bytes(),
        plan_path: plan_path.read_bytes(),
    }
    previous_settings = dict(job.settings_json or {})
    _claim_job_status(
        db,
        job,
        expected="awaiting_clip_review",
        new_status="preparing_clip_review",
        current_step="切り抜きの種類を変更中",
    )
    try:
        _write_json_payload(
            selected_path,
            converted_selection.model_dump(by_alias=True, mode="json"),
        )
        _write_json_payload(
            plan_path,
            document.model_dump(by_alias=True, mode="json"),
        )
        job.settings_json = next_settings
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        job.settings_json = previous_settings
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        for path, payload in artifact_snapshot.items():
            temporary_path = path.with_suffix(f"{path.suffix}.rollback")
            temporary_path.write_bytes(payload)
            temporary_path.replace(path)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="could not update clip type",
        ) from exc
    return document

@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/boundary",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_clip_plan_clip_boundary(
    job_id: str,
    clip_id: str,
    request: ClipPlanBoundaryUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_boundary_update: ClipPlanBoundaryUpdateEnqueue = Depends(get_enqueue_clip_plan_boundary_update),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    manual_edit = job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    )
    if job.status != "awaiting_clip_review" and not manual_edit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    expected_state = "manual_editing" if manual_edit else "awaiting_review"
    if document.state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting boundary adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="video not found",
        )
    source_duration = float(video.duration or document.source_duration or 0)
    if source_duration <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video duration is unavailable",
        )
    if request.end > source_duration + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip end exceeds source video duration",
        )
    if (
        planned_clip.hook_scene_start is not None
        and planned_clip.hook_scene_end is not None
        and (request.start > planned_clip.hook_scene_start + 0.001 or request.end < planned_clip.hook_scene_end - 0.001)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="clip boundary must continue to contain the hook scene",
        )

    if manual_edit:
        update_clip_plan_boundary(
            document,
            clip_id,
            start=request.start,
            end=request.end,
            transcript_excerpt=planned_clip.transcript_excerpt,
        )
        touch_manual_document(document)
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        return ClipPlanActionResponse(jobId=job.id, status=job.status)

    _claim_job_status(
        db,
        job,
        expected="awaiting_clip_review",
        new_status="preparing_clip_review",
        current_step="調整した範囲の確認動画を準備中",
    )
    document.state = "preparing"
    document.source_duration = source_duration
    try:
        write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    except Exception:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        db.commit()
        raise
    try:
        enqueue_boundary_update(
            job.id,
            clip_id,
            request.start,
            request.end,
        )
    except Exception as exc:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue clip plan boundary adjustment",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)

@router.patch(
    "/{job_id}/clip-plan/clips/{clip_id}/hook-scene",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_clip_plan_hook_scene(
    job_id: str,
    clip_id: str,
    request: ClipPlanHookSceneUpdateRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_hook_scene_update: ClipPlanHookSceneUpdateEnqueue = Depends(get_enqueue_clip_plan_hook_scene_update),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    manual_edit = job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    )
    if job.status != "awaiting_clip_review" and not manual_edit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting hook scene adjustment",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.boundary_reedit:
        raise HTTPException(status.HTTP_409_CONFLICT, "字幕編集から戻った場合は尺だけ変更できます。")
    expected_state = "manual_editing" if manual_edit else "awaiting_review"
    if document.state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting hook scene adjustment",
        )
    planned_clip = next(
        (clip for clip in document.clips if clip.id == clip_id),
        None,
    )
    if planned_clip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clip plan item not found",
        )
    if request.start is not None and request.end is not None:
        video = db.get(Video, job.video_id)
        if video is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="source video record is unavailable",
            )
        if video.has_audio is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="hook scene is unavailable for a source video without audio",
            )
        if request.start < planned_clip.start - 0.001 or request.end > planned_clip.end + 0.001:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="hook scene must stay within the selected clip",
            )
        short_max_duration = float((job.settings_json or {}).get("shortMaxDuration", 75.0))
        if planned_clip.type == "short" and hook_scene_newly_exceeds_short_limit(
            clip_duration=planned_clip.duration,
            hook_duration=request.end - request.start,
            short_max_duration=short_max_duration,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=("hook scene would exceed the configured short maximum duration"),
            )

    if manual_edit:
        try:
            update_clip_plan_hook_scene_document(
                document,
                clip_id,
                start=request.start,
                end=request.end,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        touch_manual_document(document)
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        return ClipPlanActionResponse(jobId=job.id, status=job.status)

    _claim_job_status(
        db,
        job,
        expected="awaiting_clip_review",
        new_status="preparing_clip_review",
        current_step="冒頭フック映像の確認動画を準備中",
    )
    document.state = "preparing"
    try:
        write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    except Exception:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        db.commit()
        raise
    try:
        enqueue_hook_scene_update(
            job.id,
            clip_id,
            request.start,
            request.end,
        )
    except Exception as exc:
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue hook scene adjustment",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)

@router.post(
    "/{job_id}/clip-plan/reselect",
    response_model=ClipPlanActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reselect_clip_plan(
    job_id: str,
    request: ClipPlanReselectionRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_reselection: ClipPlanReselectionEnqueue = Depends(get_enqueue_clip_plan_reselection),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting reselection",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    if document.boundary_reedit:
        raise HTTPException(status.HTTP_409_CONFLICT, "字幕編集から戻った場合は再選定できません。")
    previous_settings = dict(job.settings_json or {})
    keep_ids = set(request.kept_clip_ids)
    if not keep_ids.issubset({clip.id for clip in document.clips}):
        raise HTTPException(422, "キープ対象の候補が見つかりません。画面を確認してください。")
    if keep_ids and len(keep_ids) >= sum(target_count(previous_settings, document, kind) for kind in ("normal", "short")):
        raise HTTPException(422, "全候補がキープされています。再選定する候補のキープを外してください。")
    settings_payload = dict(previous_settings)
    settings_payload.update(
        request.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
    )
    try:
        validated_settings = _validated_persisted_job_settings(settings_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="再選定の尺・設定を確認してください。",
        ) from exc
    _claim_job_status(
        db,
        job,
        expected="awaiting_clip_review",
        new_status="reselecting_clips",
        current_step=CURRENT_STEP_MAP["reselecting_clips"],
    )
    job.settings_json = validated_settings.model_dump(by_alias=True, mode="json")
    document.state = "reselecting"
    try:
        write_clip_plan(document, clip_plan_output_path(paths.job_outputs(job_id)))
    except Exception:
        db.rollback()
        db.refresh(job)
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        db.commit()
        raise
    db.commit()
    try:
        enqueue_reselection(job.id)
    except Exception as exc:
        job.settings_json = previous_settings
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = CURRENT_STEP_MAP["awaiting_clip_review"]
        job.updated_at = utc_now()
        document.state = "awaiting_review"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue clip plan reselection",
        ) from exc

    return ClipPlanActionResponse(jobId=job.id, status=job.status)

@router.post(
    "/{job_id}/subtitle-review/reopen-clip-plan",
    response_model=ClipPlanActionResponse,
)
def reopen_clip_plan_for_boundary_reedit(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    output_dir = paths.job_outputs(job_id)
    with subtitle_review_document_lock(output_dir):
        db.refresh(job)
        if job.status != "awaiting_subtitle_review" or is_manual_workflow(dict(job.settings_json or {})):
            raise HTTPException(status.HTTP_409_CONFLICT, "字幕確認中の自動選定ジョブだけ尺を再調整できます。")
        review = _get_subtitle_review_or_404(job_id, paths)
        plan = _get_clip_plan_or_404(job_id, paths)
        if review.state != "awaiting_review" or plan.state != "approved":
            raise HTTPException(status.HTTP_409_CONFLICT, "字幕または切り抜き予定が編集中ではありません。")
        review_clips = {clip.id: clip for clip in review.clips}
        if {clip.id for clip in plan.clips} != set(review_clips) or any(
            clip.type != review_clips[clip.id].type for clip in plan.clips
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "切り抜き予定と字幕の対象が一致しません。")
        original_plan = plan.model_copy(deep=True)
        for clip in plan.clips:
            reviewed = review_clips[clip.id]
            clip.hook_scene_start = reviewed.hook_scene_start
            clip.hook_scene_end = reviewed.hook_scene_end
        plan.state = "awaiting_review"
        plan.boundary_reedit = True
        write_clip_plan(plan, clip_plan_output_path(output_dir))
        job.status = "awaiting_clip_review"
        job.progress = PROGRESS_MAP["awaiting_clip_review"]
        job.current_step = "尺を再調整してください。保存済み字幕は保持しています"
        job.updated_at = utc_now()
        try:
            db.commit()
        except Exception:
            db.rollback()
            write_clip_plan(original_plan, clip_plan_output_path(output_dir))
            raise
    return ClipPlanActionResponse(jobId=job.id, status=job.status)

@router.post(
    "/{job_id}/clip-plan/approve",
    response_model=ClipPlanActionResponse,
)
def approve_clip_plan(
    job_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_job: JobEnqueue = Depends(get_enqueue_job),
    enqueue_preview: SubtitleReviewPreviewEnqueue = Depends(get_enqueue_subtitle_review_preview),
) -> ClipPlanActionResponse:
    job = _get_job_or_404(db, job_id)
    video = db.get(Video, job.video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source video record is unavailable",
        )
    if job.status == "awaiting_manual_edit" and is_manual_workflow(
        dict(job.settings_json or {})
    ):
        document = _get_clip_plan_or_404(job_id, paths)
        if document.state != "manual_editing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="manual clip plan is not editable",
            )
        if not document.clips:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="manual clip plan must contain at least one clip",
            )
        for clip in document.clips:
            _validate_manual_clip_range(
                video,
                document,
                start=clip.start,
                end=clip.end,
            )
        previous_settings = dict(job.settings_json or {})
        try:
            next_settings = _validated_persisted_job_settings(
                manual_plan_settings(document, previous_settings)
            ).model_dump(by_alias=True, mode="json")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        job.settings_json = next_settings
        job.status = "queued"
        job.progress = PROGRESS_MAP["queued"]
        job.current_step = CURRENT_STEP_MAP["queued"]
        job.error_code = None
        job.error_message = None
        job.updated_at = utc_now()
        document.state = "preparing"
        write_clip_plan(
            document,
            clip_plan_output_path(paths.job_outputs(job_id)),
        )
        db.commit()
        db.refresh(job)
        try:
            enqueue_job(job.id)
        except Exception as exc:
            job.settings_json = previous_settings
            job.status = "awaiting_manual_edit"
            job.progress = PROGRESS_MAP["awaiting_manual_edit"]
            job.current_step = CURRENT_STEP_MAP["awaiting_manual_edit"]
            job.updated_at = utc_now()
            document.state = "manual_editing"
            write_clip_plan(
                document,
                clip_plan_output_path(paths.job_outputs(job_id)),
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="could not queue manual clip plan",
            ) from exc
        return ClipPlanActionResponse(jobId=job.id, status=job.status)
    if job.status != "awaiting_clip_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clip plan is not awaiting approval",
        )
    document = _get_clip_plan_or_404(job_id, paths)
    output_dir = paths.job_outputs(job_id)
    selected_payload = _read_json_if_exists(output_dir / "selected_clips.json")
    transcript_payload = _read_json_if_exists(output_dir / "transcript_segments.json")
    if not isinstance(selected_payload, dict) or not isinstance(
        transcript_payload,
        list,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="clip plan source artifacts are unavailable",
        )
    selection = CandidateSelection.model_validate(selected_payload)
    transcript_segments = [TranscriptSegment.model_validate(item) for item in transcript_payload]
    transcript_segments = repair_known_transcript_artifact_segments(transcript_segments)
    review_document = build_subtitle_review(
        job.id,
        selection,
        transcript_segments,
        short_max_duration=float((job.settings_json or {}).get("shortMaxDuration", 75.0)),
        render_mode=str((job.settings_json or {}).get("mode", "high_quality")),
        short_overlay_title_mode=_short_overlay_title_mode(dict(job.settings_json or {})),
        short_layout=_short_layout(dict(job.settings_json or {})),
        short_top_banner_enabled=bool((job.settings_json or {}).get("shortTopBannerEnabled", False)),
        short_bottom_banner_enabled=bool((job.settings_json or {}).get("shortBottomBannerEnabled", False)),
        render_settings=dict(job.settings_json or {}),
        source_width=video.width,
        source_height=video.height,
    )
    if document.boundary_reedit:
        previous_review = _get_subtitle_review_or_404(job.id, paths)
        if previous_review.state != "awaiting_review":
            raise HTTPException(status.HTTP_409_CONFLICT, "保存済み字幕が編集可能な状態ではありません。")
        try:
            review_document = retain_review_after_boundary_reedit(previous_review, review_document)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    planned_titles = {clip.id: clip.title for clip in document.clips}
    if not document.boundary_reedit:
        for clip in review_document.clips:
            if clip.id in planned_titles:
                clip.title = planned_titles[clip.id]
                clip.original_title = planned_titles[clip.id]
    _persist_subtitle_review(review_document, paths)
    write_clip_plan(
        mark_clip_plan_approved(document),
        clip_plan_output_path(output_dir),
    )
    if _job_quality_gate_mode(job, output_dir) == "auto":
        previous_settings = dict(job.settings_json or {})
        claimed_settings = {
            **previous_settings,
            AUTO_RESUME_AFTER_CLIP_REVIEW_SETTING: True,
        }
        claim = db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == "awaiting_clip_review",
            )
            .values(
                settings_json=claimed_settings,
                status="queued",
                progress=PROGRESS_MAP["queued"],
                current_step=CURRENT_STEP_MAP["queued"],
                error_code=None,
                error_message=None,
                updated_at=utc_now(),
            )
        )
        if claim.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="clip plan approval is already being processed",
            )
        db.commit()
        db.refresh(job)
        try:
            enqueue_job(job.id)
        except Exception:
            job.settings_json = previous_settings
            job.status = "awaiting_subtitle_review"
            job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
            job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
            job.updated_at = utc_now()
            db.commit()
            db.refresh(job)
        else:
            return ClipPlanActionResponse(jobId=job.id, status=job.status)
    job.status = "awaiting_subtitle_review"
    job.progress = PROGRESS_MAP["awaiting_subtitle_review"]
    job.current_step = CURRENT_STEP_MAP["awaiting_subtitle_review"]
    job.error_code = None
    job.error_message = None
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)
    with subtitle_review_document_lock(output_dir):
        review_document = _get_subtitle_review_or_404(job.id, paths)
        review_document, queued_previews = _refresh_subtitle_review_previews_unlocked(
            job=job,
            video=video,
            document=review_document,
            paths=paths,
        )
    review_document = _enqueue_subtitle_review_previews(
        job_id=job.id,
        document=review_document,
        queued=queued_previews,
        paths=paths,
        enqueue_preview=enqueue_preview,
    )
    _write_content_quality_gate(
        job=job,
        document=review_document,
        output_dir=output_dir,
    )
    return ClipPlanActionResponse(jobId=job.id, status=job.status)
