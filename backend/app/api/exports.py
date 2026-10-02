import json
from pathlib import Path
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.queue import (
    ThumbnailRegenerationEnqueue,
    get_enqueue_thumbnail_regeneration,
    get_enqueue_thumbnail_copy,
    get_enqueue_thumbnail_preview,
    get_enqueue_thumbnail_candidates,
)
from app.jobs.thumbnail_preview import (
    ThumbnailPreviewRequest, ThumbnailPreviewState, prepare_thumbnail_preview, render_thumbnail_preview,
)
from app.jobs.thumbnail_copy import ThumbnailCopyState, copy_state_path, read_copy_state, queue_copy_generation
from app.jobs.thumbnails import read_export_metadata, write_export_metadata
from app.models import ExportItem, Job
from app.schemas import ThumbnailRegenerationRequest, ThumbnailRegenerationResponse
from app.storage.paths import StoragePaths, get_storage_paths
from app.jobs.thumbnail_character_assets import available_character_assets, explicit_character_asset
from app.character_assets import CharacterAssetList, asset_read
from app.character_asset_rules import CHARACTER_EMOTIONS
from app.jobs.thumbnail_candidates import (
    ThumbnailCandidatesState, candidate_directory, candidate_state, prepare_candidates, selected_frame,
)


router = APIRouter(prefix="/api/exports", tags=["exports"])

_UNSTABLE_EXPORT_STATUSES = {
    "rendering_normal_clips",
    "rendering_shorts",
    "packaging_zip",
}
_UNSTABLE_EXPORT_ERROR_CODES = {
    "subtitle_rerender_rollback_failed",
    "worker_terminated_unexpectedly",
}


def _get_export_or_404(
    db: Session,
    export_id: str,
    paths: StoragePaths,
) -> ExportItem:
    export = db.get(ExportItem, export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export not found")
    job = db.get(Job, export.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export job not found")
    if (
        job.status in _UNSTABLE_EXPORT_STATUSES
        or job.error_code in _UNSTABLE_EXPORT_ERROR_CODES
        or rerender_publication_is_unresolved(paths.job_outputs(job.id))
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="export is unavailable while re-render publication is unresolved",
        )
    try:
        paths.resolve_stored_file(export.video_path).resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="export is not published",
        ) from None
    return export


def _stored_file_or_404(paths: StoragePaths, value: str | None, *, detail: str, media_type: str) -> FileResponse:
    if not value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    path = paths.resolve_stored_file(value)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return FileResponse(path, media_type=media_type, filename=path.name)


def _thumbnail_file_or_404(export: ExportItem, paths: StoragePaths) -> Path:
    metadata = read_export_metadata(export)
    value = metadata.get("thumbnail_path")
    if metadata.get("thumbnail_status") not in {"ready", "generating"} or not isinstance(
        value,
        str,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail file not found",
        )
    thumbnail_path = paths.resolve_stored_file(value)
    try:
        thumbnail_path.resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail is not published",
        ) from None
    if not thumbnail_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="thumbnail file not found",
        )
    return thumbnail_path


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    video_path = paths.resolve_stored_file(export.video_path)
    if not video_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export file not found")

    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)


@router.get("/{export_id}/thumbnail/copy", response_model=ThumbnailCopyState)
def get_thumbnail_copy(export_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths)):
    export = _get_export_or_404(db, export_id, paths)
    if export.type != "normal":
        raise HTTPException(422, "通常動画のサムネイルだけが対象です。")
    return ThumbnailCopyState.model_validate(read_copy_state(copy_state_path(paths, export)))


@router.post("/{export_id}/thumbnail/copy", response_model=ThumbnailCopyState, status_code=202)
def generate_thumbnail_copy(export_id: str, force: bool = False, db: Session = Depends(get_db),
                            paths: StoragePaths = Depends(get_storage_paths),
                            enqueue: Callable[[str, str], None] = Depends(get_enqueue_thumbnail_copy)):
    export = _get_export_or_404(db, export_id, paths)
    try:
        return queue_copy_generation(db, paths, export, enqueue, force=force)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (KeyError, FileNotFoundError):
        raise HTTPException(409, "完成動画の確定字幕・切り抜き範囲を確認できません。") from None
    except Exception:
        raise HTTPException(503, "文言生成を開始できませんでした。") from None


@router.get("/{export_id}/metadata")
def download_export_metadata(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    return _stored_file_or_404(
        paths,
        export.metadata_path,
        detail="metadata file not found",
        media_type="application/json",
    )


@router.get("/{export_id}/subtitle")
def download_export_subtitle(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    return _stored_file_or_404(
        paths,
        export.subtitle_path,
        detail="subtitle file not found",
        media_type="text/plain",
    )


@router.get("/{export_id}/thumbnail/assets", response_model=CharacterAssetList)
def export_thumbnail_assets(export_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths)):
    export = _get_export_or_404(db, export_id, paths)
    job = db.get(Job, export.job_id)
    groups = {emotion: [] for emotion in CHARACTER_EMOTIONS}
    if job and export.type == "normal":
        for asset in available_character_assets(db, paths, job.settings_json or {}):
            groups[asset.emotion].append(asset_read(asset))
    return CharacterAssetList(emotions=groups)


@router.post("/{export_id}/thumbnail/preview/prepare", response_model=ThumbnailPreviewState)
def prepare_export_thumbnail_preview(export_id: str, force: bool = False, db: Session = Depends(get_db),
                                     paths: StoragePaths = Depends(get_storage_paths),
                                     enqueue: Callable[[str, str], None] = Depends(get_enqueue_thumbnail_preview),
                                     subjectSource: Literal["video", "asset"] = "video", characterAssetId: str | None = None,
                                     frameCandidateId: str | None = None):
    export = _get_export_or_404(db, export_id, paths)
    try:
        return prepare_thumbnail_preview(db, paths, export, enqueue, force=force,
                                         subject_source=subjectSource, character_asset_id=characterAssetId, candidate_id=frameCandidateId)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, "プレビューの元動画・サムネ設定を確認できません。") from exc
    except Exception as exc:
        raise HTTPException(503, "プレビューを準備できませんでした。") from exc


@router.post("/{export_id}/thumbnail/preview")
def preview_export_thumbnail(export_id: str, request: ThumbnailPreviewRequest, db: Session = Depends(get_db),
                             paths: StoragePaths = Depends(get_storage_paths)):
    export = _get_export_or_404(db, export_id, paths)
    try:
        asset_info = {}
        data, text_regions = render_thumbnail_preview(db, paths, export, request, asset_render_info=asset_info)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, "プレビューを読み込み直してください。") from exc
    return Response(data, media_type="image/jpeg", headers={
        "Cache-Control": "no-store", "X-Thumbnail-Text-Regions": json.dumps(text_regions),
        "X-Thumbnail-Warnings": json.dumps(asset_info.get("warnings", [])),
    })


@router.get("/{export_id}/thumbnail")
def view_export_thumbnail(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    thumbnail_path = _thumbnail_file_or_404(export, paths)
    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.get("/{export_id}/thumbnail/download")
def download_export_thumbnail(
    export_id: str,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
) -> FileResponse:
    export = _get_export_or_404(db, export_id, paths)
    thumbnail_path = _thumbnail_file_or_404(export, paths)
    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        filename=thumbnail_path.name,
    )


@router.post(
    "/{export_id}/thumbnail/regenerate",
    response_model=ThumbnailRegenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_export_thumbnail(
    export_id: str,
    request: ThumbnailRegenerationRequest,
    db: Session = Depends(get_db),
    paths: StoragePaths = Depends(get_storage_paths),
    enqueue_thumbnail: ThumbnailRegenerationEnqueue = Depends(
        get_enqueue_thumbnail_regeneration
    ),
) -> ThumbnailRegenerationResponse:
    export = _get_export_or_404(db, export_id, paths)
    if export.type != "normal":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="thumbnail regeneration supports normal clips only",
        )
    if request.frame_seconds > float(export.duration) + 0.001:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="thumbnail frame must stay within the completed clip",
        )
    if not export.metadata_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thumbnail export metadata is unavailable",
        )
    metadata_path = paths.resolve_stored_file(export.metadata_path)
    try:
        metadata_path.resolve(strict=False).relative_to(
            paths.job_outputs(export.job_id).resolve(strict=False)
        )
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="export metadata is not published",
        ) from None
    if not metadata_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thumbnail export metadata is unavailable",
        )
    with subtitle_review_document_lock(candidate_directory(paths.job_outputs(export.job_id), export.id)):
        return _queue_thumbnail_regeneration(export, metadata_path, request, db, paths, enqueue_thumbnail)


def _queue_thumbnail_regeneration(export, metadata_path, request, db, paths, enqueue_thumbnail):
    previous = read_export_metadata(export)
    source = request.subject_source or previous.get("thumbnail_subject_source", "video")
    candidate = selected_frame(previous, candidate_id=request.frame_candidate_id)
    if request.frame_candidate_id and not candidate:
        raise HTTPException(422, "保存済みの人物候補にありません。")
    if (source != "asset" and candidate and request.crop_mode == "close" and not candidate["close_available"]
            and not request.advance_frame and not request.select_with_codex):
        raise HTTPException(422, "この候補は2倍以内の拡大で顔のアップにできません。")
    requested_id = request.character_asset_id
    requested_emotion = request.emotion
    if source == "asset":
        job = db.get(Job, export.job_id)
        if requested_id or requested_emotion or not request.select_with_codex:
            requested_id = requested_id or (None if requested_emotion else previous.get("thumbnail_character_asset_id"))
            try:
                selected_asset = explicit_character_asset(db, paths, job.settings_json or {} if job else {},
                                                          requested_id, requested_emotion)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            requested_id, requested_emotion = selected_asset.id, selected_asset.emotion
        elif not job or not available_character_assets(db, paths, job.settings_json or {}):
            raise HTTPException(422, "このキャラの素材がありません。")
    try:
        revision = max(0, int(previous.get("thumbnail_request_revision", 0))) + 1
    except (TypeError, ValueError):
        revision = 1
    try:
        previous_variant_index = int(previous.get("thumbnail_variant_index", -1))
    except (TypeError, ValueError):
        previous_variant_index = -1
    variant_index = (
        (previous_variant_index + 1) % (8 if request.select_with_codex else 6)
        if request.advance_frame or request.select_with_codex
        else max(0, previous_variant_index)
    )
    pending = {
        **previous,
        "thumbnail_subject_source": source,
        "thumbnail_requested_asset_id": requested_id,
        "thumbnail_requested_emotion": requested_emotion,
        "thumbnail_status": "generating",
        "thumbnail_frame_seconds": round(candidate["second"] if candidate and request.frame_candidate_id else request.frame_seconds, 3),
        "thumbnail_frame_candidate_id": request.frame_candidate_id,
        "thumbnail_subject_anchor_x": round(request.subject_anchor_x, 3),
        "thumbnail_advance_frame": request.advance_frame,
        "thumbnail_select_with_codex": request.select_with_codex,
        "thumbnail_variant_index": variant_index,
        "thumbnail_crop_mode": request.crop_mode,
        "thumbnail_request_revision": revision,
        "thumbnail_error_code": None,
    }
    if request.subject_placement is not None:
        pending["thumbnail_subject_placement"] = request.subject_placement.model_dump(mode="json", by_alias=True)
    if request.design is not None:
        from app.thumbnail_style import resolve_export_thumbnail_style
        job = db.get(Job, export.job_id)
        try:
            resolve_export_thumbnail_style(
                (job.settings_json or {}).get("normalThumbnailStyle") if job else None,
                request.design,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        pending["thumbnail_design"] = request.design
    if request.text is not None:
        pending.update({"thumbnail_kicker": request.text.heading.strip(),
                        "thumbnail_line1": request.text.upper.strip(), "thumbnail_line2": request.text.lower.strip()})
    if request.text_styles is not None:
        pending["thumbnail_text_styles"] = request.text_styles.model_dump(mode="json", by_alias=True)
    write_export_metadata(metadata_path, pending)
    try:
        enqueue_thumbnail(export.id, revision)
    except Exception as exc:
        write_export_metadata(metadata_path, previous)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not queue thumbnail regeneration",
        ) from exc
    return ThumbnailRegenerationResponse(
        exportId=export.id,
        status="generating",
        revision=revision,
    )


@router.post("/{export_id}/thumbnail/candidates/prepare", response_model=ThumbnailCandidatesState)
def prepare_export_thumbnail_candidates(export_id: str, db: Session = Depends(get_db),
                                        paths: StoragePaths = Depends(get_storage_paths),
                                        enqueue: Callable[[str, str], None] = Depends(get_enqueue_thumbnail_candidates),
                                        force: bool = False):
    export = _get_export_or_404(db, export_id, paths)
    try:
        return prepare_candidates(db, paths, export, enqueue, force=force)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "サムネ候補の抽出を開始できませんでした。") from exc


@router.get("/{export_id}/thumbnail/candidates/{candidate_id}/image")
def view_thumbnail_candidate(export_id: str, candidate_id: str, db: Session = Depends(get_db),
                             paths: StoragePaths = Depends(get_storage_paths)):
    export = _get_export_or_404(db, export_id, paths)
    if not selected_frame(read_export_metadata(export), candidate_id=candidate_id):
        raise HTTPException(404, "サムネ候補がありません。")
    path = candidate_directory(paths.job_outputs(export.job_id), export.id) / f"{candidate_id}.small.jpg"
    if not path.is_file():
        raise HTTPException(404, "サムネ候補の画像がありません。")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{export_id}/thumbnail/candidates", response_model=ThumbnailCandidatesState)
def get_export_thumbnail_candidates(export_id: str, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths)):
    export = _get_export_or_404(db, export_id, paths)
    return candidate_state(export, paths.job_outputs(export.job_id))
