from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.queue import get_queue
from app.jobs.short_framing_guide import ShortFramingGuide, prepare_framing_guide, run_short_framing_guide
from app.storage.paths import StoragePaths, get_storage_paths
from app.schemas import ShortLayout

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def enqueue_guide(job_id, clip_id, request_id, layout=None):
    get_queue().enqueue(run_short_framing_guide, job_id, clip_id, request_id, layout,
                        job_id=f"framing-guide-{request_id}", job_timeout=150, at_front=True)


def get_enqueue_guide():
    return enqueue_guide


@router.post("/{job_id}/subtitle-review/clips/{clip_id}/framing-guide", response_model=ShortFramingGuide)
def prepare_guide(
    job_id: str, clip_id: str, force: bool = False, layout: ShortLayout | None = None,
    db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
    enqueue=Depends(get_enqueue_guide),
):
    from app.models import Job
    from app.jobs.automation import is_subtitle_only_auto
    job = db.get(Job, job_id)
    if job is not None and is_subtitle_only_auto(job.settings_json or {}):
        from app.api.jobs import _get_subtitle_review_or_404
        from app.jobs.manual_framing import framing_edit_error
        from app.jobs.subtitle_review_preview import subtitle_review_document_lock
        with subtitle_review_document_lock(paths.job_outputs(job_id)):
            document = _get_subtitle_review_or_404(job_id, paths)
            clip = next((c for c in document.clips if c.id == clip_id), None)
            if clip is None:
                raise HTTPException(404, "対象のclipがありません。")
            if error := framing_edit_error(document, clip):
                raise HTTPException(409, error)
    try:
        return prepare_framing_guide(db, paths, job_id, clip_id, enqueue, force=force, layout=layout)
    except FileNotFoundError as error:
        raise HTTPException(404, "元動画または字幕確認が見つかりません。") from error
    except ValueError as error:
        raise HTTPException(409, "このショートの画角を読み込めません。") from error
    except Exception as error:
        raise HTTPException(503, "画角の準備を開始できませんでした。") from error
