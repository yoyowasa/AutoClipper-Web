from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.analysis_api_schemas import AnalysisHistoryRead, AnalysisRunRead, AnalysisStartRequest
from app.intelligence.analysis_errors import MESSAGES
from app.intelligence.analysis_runner import mark_analysis_failed
from app.intelligence.common import now
from app.intelligence.models import AnalysisRun, Channel, ChannelConnection, SyncRun
from app.intelligence.queue import get_enqueue_channel_analysis
from app.intelligence.production_aggregation import build_production_aggregates
from app.intelligence.models import ProductionAggregate
from app.intelligence.aggregate_api_schemas import ProductionAggregatesRead
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/intelligence/channels", tags=["intelligence"])


@router.get("/{channel_id}/production-aggregates", response_model=ProductionAggregatesRead)
def production_aggregates(channel_id: int, response: Response, db: Session = Depends(get_db),
                          paths: StoragePaths = Depends(get_storage_paths), config: Settings = Depends(get_settings)):
    response.headers.update(PRIVATE_HEADERS)
    if db.get(Channel, channel_id) is None:
        raise HTTPException(404, "チャンネルがありません。")
    if not config.youtube_derived_allowed:
        raise HTTPException(409, MESSAGES["DERIVED_NOT_ALLOWED"])
    cached = db.get(ProductionAggregate, channel_id)
    if cached and cached.expires_at > now():
        return cached.payload
    # Local DB/JSON calculation only. No HTTP/API/Codex calls here.
    return build_production_aggregates(db, paths, config, channel_id, now())


def read_analysis(run: AnalysisRun) -> AnalysisRunRead:
    return AnalysisRunRead(id=run.id, status=run.status, queuedAt=run.queued_at, startedAt=run.started_at,
        finishedAt=run.finished_at, expiresAt=run.expires_at, errorCode=run.error_code, errorMessage=MESSAGES.get(run.error_code),
        model=run.requested_model, reasoning=run.requested_effort, requestId=run.request_id, syncBefore=run.sync_before,
        syncRunId=run.sync_run_id, review=run.review, validation=run.validation.report if run.validation else None)


@router.post("/{channel_id}/analysis", response_model=AnalysisRunRead, status_code=202)
def start_analysis(channel_id: int, body: AnalysisStartRequest, request: Request, db: Session = Depends(get_db),
                   enqueue=Depends(get_enqueue_channel_analysis), config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    if db.get(Channel, channel_id) is None:
        raise HTTPException(404, "チャンネルがありません。")
    connection = db.get(ChannelConnection, channel_id)
    if not connection or connection.status != "connected":
        raise HTTPException(409, MESSAGES["OWN_OAUTH_REQUIRED"])
    if not config.youtube_derived_allowed:
        raise HTTPException(409, MESSAGES["DERIVED_NOT_ALLOWED"])
    if db.scalar(select(SyncRun).where(SyncRun.active_channel_id == channel_id)):
        raise HTTPException(409, MESSAGES["STATISTICS_BUSY"])
    run = AnalysisRun(id="analysis_" + uuid4().hex, channel_id=channel_id, active_channel_id=channel_id,
                      sync_before=body.syncBefore, queued_at=now(), expires_at=now() + timedelta(days=30))
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "このチャンネルは分析中です。") from None
    try:
        enqueue(run.id)
    except Exception:
        mark_analysis_failed(db, run.id, "QUEUE_FAILED")
        raise HTTPException(503, MESSAGES["QUEUE_FAILED"]) from None
    return read_analysis(run)


@router.get("/{channel_id}/analysis", response_model=AnalysisHistoryRead)
def analysis_history(channel_id: int, response: Response, db: Session = Depends(get_db)):
    response.headers.update(PRIVATE_HEADERS)
    if db.get(Channel, channel_id) is None:
        raise HTTPException(404, "チャンネルがありません。")
    query = select(AnalysisRun).where(AnalysisRun.channel_id == channel_id, AnalysisRun.expires_at > now())
    runs = db.scalars(query.order_by(AnalysisRun.queued_at.desc(), AnalysisRun.id.desc()).limit(20)).all()
    latest = db.scalar(query.where(AnalysisRun.status == "success").order_by(AnalysisRun.finished_at.desc()).limit(1))
    return AnalysisHistoryRead(latestRun=read_analysis(runs[0]) if runs else None,
        latestResult=read_analysis(latest) if latest else None, history=[read_analysis(run) for run in runs])
