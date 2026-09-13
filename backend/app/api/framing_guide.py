from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.queue import get_queue
from app.jobs.short_framing_guide import ShortFramingGuide, prepare_framing_guide, run_short_framing_guide
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def enqueue_guide(job_id, clip_id, request_id):
    get_queue().enqueue(run_short_framing_guide, job_id, clip_id, request_id,
                        job_id=f"framing-guide-{request_id}", job_timeout=150)


def get_enqueue_guide():
    return enqueue_guide


@router.post("/{job_id}/subtitle-review/clips/{clip_id}/framing-guide", response_model=ShortFramingGuide)
def prepare_guide(
    job_id: str, clip_id: str, force: bool = False,
    db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
    enqueue=Depends(get_enqueue_guide),
):
    try:
        return prepare_framing_guide(db, paths, job_id, clip_id, enqueue, force=force)
    except FileNotFoundError as error:
        raise HTTPException(404, "元動画または字幕確認が見つかりません。") from error
    except ValueError as error:
        raise HTTPException(409, "このショートの画角を読み込めません。") from error
    except Exception as error:
        raise HTTPException(503, "画角の準備を開始できませんでした。") from error
