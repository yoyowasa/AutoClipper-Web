from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.common import now
from app.intelligence.dashboard import dashboard_data, evidence_video_ids
from app.intelligence.dashboard_schemas import DashboardRead, EvidenceVideosRead
from app.intelligence.models import AnalysisRun, Channel, ChannelConnection, ImprovementTrial
from app.intelligence.trial_schemas import TrialRead, TrialUpdate
from app.intelligence.trials import adopt_proposal, read_trial, update_trial
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/intelligence/channels", tags=["intelligence"])


def require_channel(channel_id, db):
    if db.get(Channel, channel_id) is None or db.get(ChannelConnection, channel_id) is None:
        raise HTTPException(404, "接続した自チャンネルがありません。")


def find_trial(channel_id, trial_id, db):
    require_channel(channel_id, db)
    trial = db.get(ImprovementTrial, trial_id)
    if not trial or trial.channel_id != channel_id:
        raise HTTPException(404, "改善試験がありません。")
    return trial


def videos_for_trials(db, paths, config, channel_id):
    return {video.id: video for video in dashboard_data(db, paths, config, channel_id, "all", now()).videos}


@router.get("/{channel_id}/dashboard", response_model=DashboardRead)
def get_dashboard(channel_id: int, response: Response, format: Literal["all", "shorts", "long"] = "all",
                  db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
                  config: Settings = Depends(get_settings)):
    require_channel(channel_id, db)
    response.headers.update(PRIVATE_HEADERS)
    return dashboard_data(db, paths, config, channel_id, format, now())


@router.get("/{channel_id}/analysis/{analysis_id}/evidence-videos", response_model=EvidenceVideosRead)
def get_evidence_videos(channel_id: int, analysis_id: str, response: Response, db: Session = Depends(get_db)):
    require_channel(channel_id, db)
    response.headers.update(PRIVATE_HEADERS)
    run = db.get(AnalysisRun, analysis_id)
    if not run or run.channel_id != channel_id or run.expires_at <= now() or not run.input_snapshot:
        raise HTTPException(404, "分析の根拠は未保存または保持期限切れです。")
    return EvidenceVideosRead(analysisId=analysis_id, evidenceVideos=evidence_video_ids(run.input_snapshot))


@router.get("/{channel_id}/trials", response_model=list[TrialRead])
def list_trials(channel_id: int, response: Response, db: Session = Depends(get_db),
                paths: StoragePaths = Depends(get_storage_paths), config: Settings = Depends(get_settings)):
    require_channel(channel_id, db)
    response.headers.update(PRIVATE_HEADERS)
    videos = videos_for_trials(db, paths, config, channel_id)
    return [read_trial(trial, videos) for trial in db.scalars(select(ImprovementTrial).where(
        ImprovementTrial.channel_id == channel_id).order_by(ImprovementTrial.updated_at.desc(), ImprovementTrial.id))]


@router.post("/{channel_id}/analysis/{analysis_id}/proposals/{proposal_id}/adopt", response_model=TrialRead)
def adopt(channel_id: int, analysis_id: str, proposal_id: str, request: Request, response: Response,
          db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths), config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    require_channel(channel_id, db)
    response.headers.update(PRIVATE_HEADERS)
    try:
        trial = adopt_proposal(db, channel_id, analysis_id, proposal_id, now())
    except ValueError:
        raise HTTPException(409, "提案または基準動画が無効です。同期・分析の状態と保持期限を確認してください。") from None
    return read_trial(trial, videos_for_trials(db, paths, config, channel_id))


@router.put("/{channel_id}/trials/{trial_id}", response_model=TrialRead)
def edit_trial(channel_id: int, trial_id: str, body: TrialUpdate, request: Request, response: Response,
               db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths), config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    response.headers.update(PRIVATE_HEADERS)
    trial = find_trial(channel_id, trial_id, db)
    try:
        update_trial(db, paths, trial, body, now())
    except (ValueError, RuntimeError) as error:
        raise HTTPException(409 if isinstance(error, RuntimeError) else 422, str(error)) from None
    return read_trial(trial, videos_for_trials(db, paths, config, channel_id))


@router.delete("/{channel_id}/trials/{trial_id}", status_code=204)
def delete_trial(channel_id: int, trial_id: str, request: Request, db: Session = Depends(get_db),
                 config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    db.delete(find_trial(channel_id, trial_id, db))
    db.commit()
    return Response(status_code=204, headers=PRIVATE_HEADERS)
