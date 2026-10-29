import html

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.common import ERROR_MESSAGES, YouTubeError, now
from app.intelligence.job_claims import ChannelClaimError, claim_channel_run
from app.intelligence.credentials import persist_credentials
from app.intelligence.models import Channel, ChannelConnection, SyncRun
from app.intelligence.oauth import COOKIE, STATE_TTL_SECONDS, begin_oauth, complete_oauth
from app.intelligence.queue import get_enqueue_youtube_sync
from app.intelligence.schemas import ChannelRead, OAuthStartRequest, OAuthStartResponse, SyncRunRead, YouTubeConnectionsRead
from app.intelligence.sync import mark_sync_failed
from app.intelligence.youtube_client import YouTubeClient
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def require_local_origin(request: Request, config: Settings) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in config.cors_origins:
        raise HTTPException(403, "許可されていない接続元です。")


def read_run(run: SyncRun) -> SyncRunRead:
    return SyncRunRead(id=run.id, status=run.status, queuedAt=run.queued_at, finishedAt=run.finished_at,
        errorCode=run.error_code, errorMessage=ERROR_MESSAGES.get(run.error_code), requestedStart=run.requested_start,
        requestedEnd=run.requested_end, lastReportDate=run.last_report_date, fetchedCount=run.fetched_count,
        truncated=run.truncated, missingReportCount=sum(item.get("reason") == "NO_ROWS" for item in run.missing_reports))


@router.get("/channels", response_model=YouTubeConnectionsRead)
def list_channels(response: Response, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
                  config: Settings = Depends(get_settings)) -> YouTubeConnectionsRead:
    response.headers.update(PRIVATE_HEADERS)
    channels = []
    for channel in db.scalars(select(Channel).order_by(Channel.id)):
        connection = db.get(ChannelConnection, channel.id)
        connected = bool(connection and connection.status == "connected" and paths.youtube_token(channel.external_id).is_file())
        latest = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel.id).order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()))
        channels.append(ChannelRead(id=channel.id, externalId=channel.external_id, name=channel.name,
            connectionStatus="connected" if connected else "reconnect_required",
            errorMessage=ERROR_MESSAGES["RECONNECT_REQUIRED"] if not connected else None,
            lastSyncAt=channel.last_sync_at, latestRun=read_run(latest) if latest else None))
    return YouTubeConnectionsRead(clientConfigured=paths.google_client.is_file(), channels=channels,
        derivedAllowed=config.youtube_derived_allowed, extendedStorage=config.youtube_extended_storage,
        reviewedAt=config.youtube_policy_reviewed_at, policyReference=config.youtube_policy_reference,
        automation={"enabled": config.youtube_automation_enabled, "syncHourUtc": config.youtube_auto_sync_hour_utc,
                    "analysisWeekday": config.youtube_auto_analysis_weekday, "timezone": "UTC"})


@router.post("/oauth/start", response_model=OAuthStartResponse)
def start_oauth(body: OAuthStartRequest, request: Request, response: Response, paths: StoragePaths = Depends(get_storage_paths),
                config: Settings = Depends(get_settings)) -> OAuthStartResponse:
    require_local_origin(request, config)
    try:
        url, nonce = begin_oauth(paths, config, body.channel_external_id)
    except YouTubeError as error:
        raise HTTPException(409, str(error)) from None
    except Exception:
        raise HTTPException(409, ERROR_MESSAGES["OAUTH_FAILED"]) from None
    response.headers.update(PRIVATE_HEADERS)
    response.set_cookie(COOKIE, nonce, max_age=STATE_TTL_SECONDS, httponly=True, samesite="lax", path="/api/intelligence/oauth")
    return OAuthStartResponse(authorizationUrl=url)


@router.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(request: Request, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
                   config: Settings = Depends(get_settings)) -> HTMLResponse:
    try:
        expected, credentials = complete_oauth(paths, config, request.query_params.get("state", ""),
            request.query_params.get("code", ""), request.cookies.get(COOKIE, ""))
        identity = YouTubeClient(credentials.token, budget_seconds=20).identity()
        if identity["id"] != expected:
            raise YouTubeError("CHANNEL_MISMATCH")
        channel = db.scalar(select(Channel).where(Channel.external_id == expected))
        if channel is None:
            channel = Channel(external_id=expected)
            db.add(channel)
            db.flush()
        channel.name, channel.metadata_updated_at = identity["snippet"]["title"], now()
        connection = db.get(ChannelConnection, channel.id)
        if connection is None:
            connection = ChannelConnection(channel_id=channel.id)
            db.add(connection)
        connection.status, connection.error_code, connection.verified_at = "connected", None, now()
        persist_credentials(paths, expected, credentials)
        db.commit()
        message, status = "YouTubeに接続しました。設定画面に戻り「同期する」を押してください。", 200
    except Exception as error:
        db.rollback()
        message = str(error) if isinstance(error, YouTubeError) else ERROR_MESSAGES["OAUTH_FAILED"]
        status = 400
    target = html.escape(config.cors_origins[0] + "/settings", quote=True)
    response = HTMLResponse(f'<!doctype html><html lang="ja"><meta charset="utf-8"><title>YouTube連携</title>'
        f'<h1>YouTube連携</h1><p>{html.escape(message)}</p><a href="{target}">AutoClipperの設定へ戻る</a></html>',
        status_code=status, headers={**PRIVATE_HEADERS, "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"})
    response.delete_cookie(COOKIE, path="/api/intelligence/oauth")
    return response


@router.post("/channels/{channel_id}/sync", response_model=SyncRunRead, status_code=202)
def sync_channel(channel_id: int, request: Request, db: Session = Depends(get_db),
                 enqueue=Depends(get_enqueue_youtube_sync), config: Settings = Depends(get_settings)) -> SyncRunRead:
    require_local_origin(request, config)
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(404, "チャンネルがありません。")
    connection = db.get(ChannelConnection, channel_id)
    if not connection or connection.status != "connected":
        raise HTTPException(409, ERROR_MESSAGES["RECONNECT_REQUIRED"])
    try:
        run = claim_channel_run(db, channel_id, "sync", now())
    except ChannelClaimError:
        raise HTTPException(409, "このチャンネルは同期または分析中です。接続状態も確認してください。") from None
    try:
        enqueue(run.id)
    except Exception:
        mark_sync_failed(db, run.id, "QUEUE_FAILED")
        raise HTTPException(503, ERROR_MESSAGES["QUEUE_FAILED"]) from None
    return read_run(run)
