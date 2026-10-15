from datetime import datetime, timedelta, date
import logging
import os
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import httpx
import pytest
from rq.job import JobStatus
from rq.timeouts import JobTimeoutException
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

import app.api.intelligence as api
import app.db as app_db
import app.intelligence.oauth as oauth
import app.intelligence.sync as sync
from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.common import YouTubeError
from app.intelligence.credentials import SCOPES
from app.intelligence.maintenance import maintain_youtube
from app.intelligence.models import Channel, ChannelConnection, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.policy import expire_youtube_data, statistical_expiry
from app.intelligence.queue import get_enqueue_youtube_sync
from app.intelligence.secret_files import read_private_json, write_private_json
from app.intelligence.youtube_client import METRICS, YouTubeClient
from app.main import app
from app.models import Job
from app.models import AppPreference
from app.storage.paths import get_storage_paths
from test_api_routes import client as client

CHANNEL_ID = "UC" + "a" * 22
OTHER_CHANNEL = "UC" + "b" * 22
VIDEO_ID = "video000001"
CLOCK = datetime(2026, 10, 15, 12)


@pytest.fixture
def environment(client, monkeypatch):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    paths = app.dependency_overrides[get_storage_paths]()
    config = Settings(_env_file=None)
    app.dependency_overrides[get_settings] = lambda: config
    write_private_json(paths.google_client, {"installed": {
        "client_id": "test.apps.googleusercontent.com", "client_secret": "synthetic-client-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }})
    def exchange(flow, **kwargs):
        assert kwargs["timeout"] == 10
        flow.oauth2session.token = {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                                   "token_type": "Bearer", "expires_at": time.time() + 3600, "scope": list(SCOPES)}
    monkeypatch.setattr(Flow, "fetch_token", exchange)
    monkeypatch.setattr(api, "YouTubeClient", lambda *args, **kwargs: SimpleNamespace(identity=lambda: {
        "id": CHANNEL_ID, "snippet": {"title": "テストチャンネル"}}))
    monkeypatch.setattr(sync, "now", lambda: CLOCK)
    yield SimpleNamespace(db=db, factory=factory, paths=paths, config=config)
    generator.close()


def connect(client):
    response = client.post("/api/intelligence/oauth/start", json={"channelExternalId": CHANNEL_ID})
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)
    assert set(query["scope"][0].split()) == set(SCOPES)
    assert query["redirect_uri"] == ["http://localhost:8000/api/intelligence/oauth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    return client.get("/api/intelligence/oauth/callback", params={"state": query["state"][0], "code": "synthetic-code"})


def enqueue(client, environment):
    assert connect(client).status_code == 200
    calls = []
    app.dependency_overrides[get_enqueue_youtube_sync] = lambda: calls.append
    response = client.post("/api/intelligence/channels/1/sync")
    assert response.status_code == 202
    assert calls == [response.json()["id"]]
    return response.json()["id"]


def test_oauth_token_file_identity_and_no_secrets_in_response(client, environment):
    assert connect(client).status_code == 200
    token = environment.paths.youtube_token(CHANNEL_ID)
    assert token.is_file()
    if os.name != "nt":
        assert token.stat().st_mode & 0o777 == 0o600
    payload = client.get("/api/intelligence/channels")
    assert payload.headers["cache-control"] == "no-store"
    assert payload.json()["channels"][0]["connectionStatus"] == "connected"
    assert all(value not in payload.text for value in ("synthetic-access", "synthetic-refresh", "synthetic-client-secret"))
    assert environment.db.scalar(select(Channel)).external_id == CHANNEL_ID


@pytest.mark.parametrize("problem", ["state", "cookie", "expired", "mismatch"])
def test_oauth_rejects_invalid_state_and_wrong_channel(client, environment, monkeypatch, problem):
    response = client.post("/api/intelligence/oauth/start", json={"channelExternalId": CHANNEL_ID})
    state = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)["state"][0]
    if problem == "state":
        state = "z" * 43
    elif problem == "cookie":
        client.cookies.clear()
    elif problem == "expired":
        monkeypatch.setattr(oauth, "now", lambda: CLOCK + timedelta(days=100))
    else:
        monkeypatch.setattr(api, "YouTubeClient", lambda *args, **kwargs: SimpleNamespace(identity=lambda: {
            "id": OTHER_CHANNEL, "snippet": {"title": "別チャンネル"}}))
    denied = client.get("/api/intelligence/oauth/callback", params={"state": state, "code": "synthetic-code"})
    assert denied.status_code == 400
    assert "synthetic-code" not in denied.text
    assert not environment.paths.youtube_token(CHANNEL_ID).exists()
    assert environment.db.scalar(select(Channel)) is None


def test_oauth_state_is_single_use_and_start_rejects_cross_origin(client, environment):
    assert client.post("/api/intelligence/oauth/start", json={"channelExternalId": CHANNEL_ID},
                       headers={"Origin": "https://untrusted.example"}).status_code == 403
    response = client.post("/api/intelligence/oauth/start", json={"channelExternalId": CHANNEL_ID})
    state = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)["state"][0]
    nonce = client.cookies.get(oauth.COOKIE)
    assert client.get("/api/intelligence/oauth/callback", params={"state": state, "code": "code"}).status_code == 200
    client.cookies.set(oauth.COOKIE, nonce)
    assert client.get("/api/intelligence/oauth/callback", params={"state": state, "code": "code"}).status_code == 400


@pytest.mark.parametrize("callback_path", ["/api/intelligence/oauth/callback", "/api/intelligence/oauth/callback/"])
def test_callback_and_oauth_library_logs_hide_credentials(caplog, callback_path):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("requests_oauthlib.oauth2_session").debug("synthetic-client-secret synthetic-refresh")
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %s',
        "local", "GET", callback_path + "?code=synthetic-code&state=synthetic-state", "1.1", 200)
    assert "synthetic-" not in caplog.text
    assert "/api/intelligence/oauth/callback" in caplog.text


def test_private_atomic_write_cleans_failed_temporary_file(tmp_path, monkeypatch):
    from app.intelligence import secret_files
    path = tmp_path / "secrets" / "test.json"
    monkeypatch.setattr(secret_files.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("synthetic IO failure")))
    with pytest.raises(OSError):
        write_private_json(path, {"value": "synthetic"})
    assert list(path.parent.iterdir()) == []


def test_invalid_grant_records_reconnect_and_failed_sync(client, environment, monkeypatch):
    run_id = enqueue(client, environment)
    path = environment.paths.youtube_token(CHANNEL_ID)
    info = read_private_json(path)
    info["expiry"] = "2000-01-01T00:00:00Z"
    write_private_json(path, info)
    def invalid(*args, **kwargs):
        raise RefreshError("invalid_grant synthetic-refresh")
    monkeypatch.setattr(Credentials, "refresh", invalid)
    with pytest.raises(YouTubeError, match="再接続") as error:
        sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths)
    assert "synthetic-refresh" not in str(error.value)
    result = client.get("/api/intelligence/channels").json()["channels"][0]
    assert result["connectionStatus"] == "reconnect_required"
    assert result["latestRun"]["status"] == "failed"
    assert result["latestRun"]["errorCode"] == "RECONNECT_REQUIRED"


def api_row(dimensions, **overrides):
    return {**dict.fromkeys(METRICS, 1), "averageViewPercentage": 120.5, "likes": -1, **dimensions, **overrides}


def transport(request):
    endpoint = request.url.path.rsplit("/", 1)[-1]
    if endpoint == "channels":
        return httpx.Response(200, json={"items": [{"id": CHANNEL_ID, "snippet": {"title": "本人"},
            "contentDetails": {"relatedPlaylists": {"uploads": "uploads"}}}]})
    if endpoint == "playlistItems":
        return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": VIDEO_ID}}]})
    if endpoint == "videos":
        return httpx.Response(200, json={"items": [{"id": VIDEO_ID,
            "snippet": {"channelId": CHANNEL_ID, "title": "公開動画", "publishedAt": "2026-09-01T00:00:00Z"},
            "contentDetails": {"duration": "PT1M10S"}, "statistics": {"viewCount": "10"}, "status": {"privacyStatus": "public"}}]})
    dimensions = request.url.params.get("dimensions", "")
    dims = {"day": "2026-10-13", "video": VIDEO_ID, "creatorContentType": "SHORTS"}
    row = api_row({key: dims[key] for key in dimensions.split(",") if key}, shares=None)
    return httpx.Response(200, json={"columnHeaders": [{"name": key} for key in row], "rows": [list(row.values())]})


def test_sync_native_statistics_periods_missing_values_and_idempotence(client, environment):
    run_id = enqueue(client, environment)
    requests = []
    def mocked(request):
        requests.append(request)
        return transport(request)
    def run(id):
        sync.run_youtube_sync(id, session_factory=environment.factory, config=environment.config, paths=environment.paths,
                             client=YouTubeClient("synthetic-access", transport=httpx.MockTransport(mocked)))
    run(run_id)
    environment.db.expire_all()
    saved = environment.db.get(SyncRun, run_id)
    assert saved.status == "success"
    assert saved.last_report_date == date(2026, 10, 13)
    daily = environment.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "video_day"))
    assert daily.video_id == VIDEO_ID
    assert daily.values["shares"] is None and daily.missing_reasons["shares"] == "UNAVAILABLE"
    assert daily.values["likes"] == -1 and daily.values["averageViewPercentage"] == 120.5
    assert daily.report_timezone == "America/Los_Angeles"
    video = environment.db.get(YouTubeVideo, VIDEO_ID)
    assert video.format == "shorts" and video.duration_seconds == 70
    assert video.public_statistics["values"]["likes"] is None
    assert video.public_statistics["missingReasons"]["likes"] == "UNAVAILABLE"
    params = [request.url.params for request in requests if request.url.path.endswith("reports")]
    current = next(item for item in params if not item.get("dimensions") and item["endDate"] == "2026-10-13")
    assert current["startDate"] == "2026-09-16"
    first = next(item for item in params if item.get("dimensions") == "creatorContentType" and item["endDate"] == "2026-09-07")
    assert first["startDate"] == "2026-09-01" and first["endDate"] == "2026-09-07"
    count = len(environment.db.scalars(select(VideoDailyStat)).all())
    new_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    run(new_id)
    environment.db.expire_all()
    assert len(environment.db.scalars(select(VideoDailyStat)).all()) == count


def test_no_rows_is_preserved_not_zero(client, environment):
    run_id = enqueue(client, environment)
    def empty(request):
        return httpx.Response(200, json={"rows": []}) if request.url.path.endswith("reports") else transport(request)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(empty)))
    row = environment.db.scalar(select(VideoDailyStat))
    assert set(row.values.values()) == {None}
    assert set(row.missing_reasons.values()) == {"NO_ROWS"}
    assert environment.db.get(SyncRun, run_id).last_report_date is None


def test_network_phase_does_not_hold_database_write_lock(client, environment):
    run_id = enqueue(client, environment)
    checked = False
    def concurrent(request):
        nonlocal checked
        if request.url.path.endswith("reports") and not checked:
            checked = True
            with environment.factory() as other:
                other.add(AppPreference(key="concurrent-test", value_json={"saved": True}))
                other.commit()
        return transport(request)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(concurrent)))
    assert checked
    assert environment.db.get(AppPreference, "concurrent-test").value_json == {"saved": True}


def test_missing_scope_cannot_persist_connection(client, environment, monkeypatch):
    def exchange(flow, **kwargs):
        flow.oauth2session.token = {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                                   "expires_at": time.time() + 3600, "scope": [SCOPES[0]]}
    monkeypatch.setattr(Flow, "fetch_token", exchange)
    response = connect(client)
    assert response.status_code == 400
    assert "両方許可" in response.text
    assert not environment.paths.youtube_token(CHANNEL_ID).exists()
    assert environment.db.scalar(select(ChannelConnection)) is None


@pytest.mark.parametrize("status,reason,code", [(403, "quotaExceeded", "QUOTA_EXCEEDED"), (403, "forbidden", "FORBIDDEN")])
def test_failed_api_run_does_not_publish_partial_statistics(client, environment, status, reason, code):
    run_id = enqueue(client, environment)
    def failed(request):
        if request.url.path.endswith("reports"):
            return httpx.Response(status, json={"error": {"errors": [{"reason": reason}], "message": "synthetic-private-error"}})
        return transport(request)
    with pytest.raises(YouTubeError) as error:
        sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                             client=YouTubeClient("synthetic", transport=httpx.MockTransport(failed)))
    assert error.value.code == code
    environment.db.expire_all()
    assert environment.db.get(SyncRun, run_id).status == "failed"
    assert environment.db.scalar(select(YouTubeVideo)) is None
    assert environment.db.scalar(select(VideoDailyStat)) is None


def test_queue_only_single_claim_and_enqueue_failure_audit(client, environment):
    run_id = enqueue(client, environment)
    assert client.post("/api/intelligence/channels/1/sync", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.post("/api/intelligence/channels/1/sync").status_code == 409
    with environment.factory() as db:
        sync.mark_sync_failed(db, run_id, "WORKER_INTERRUPTED")
    app.dependency_overrides[get_enqueue_youtube_sync] = lambda: lambda *args: (_ for _ in ()).throw(RuntimeError("private"))
    response = client.post("/api/intelligence/channels/1/sync")
    assert response.status_code == 503 and "private" not in response.text
    assert client.get("/api/intelligence/channels").json()["channels"][0]["latestRun"]["errorCode"] == "QUEUE_FAILED"


def test_rq_timeout_and_killed_worker_record_sync_failure(client, environment):
    run_id = enqueue(client, environment)
    fake = SimpleNamespace(identity=lambda: (_ for _ in ()).throw(JobTimeoutException()), requests=0)
    with pytest.raises(YouTubeError):
        sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths, client=fake)
    environment.db.expire_all()
    assert environment.db.get(SyncRun, run_id).status == "failed"
    assert environment.db.get(SyncRun, run_id).error_code == "SYNC_LIMIT"
    other = client.post("/api/intelligence/channels/1/sync").json()["id"]
    sync.record_rq_sync_failure(environment.db, SimpleNamespace(func_name="app.intelligence.sync.run_youtube_sync", args=[other]))
    environment.db.expire_all()
    assert environment.db.get(SyncRun, other).error_code == "WORKER_INTERRUPTED"
    assert environment.db.scalar(select(Job)) is None


def test_queue_timeout_and_request_budget(monkeypatch):
    import app.intelligence.queue as queue
    from app.intelligence.queue import enqueue_youtube_sync
    captured = []
    monkeypatch.setattr(queue, "get_intelligence_queue", lambda: SimpleNamespace(enqueue=lambda *args, **kwargs: captured.append(kwargs)))
    enqueue_youtube_sync("sync_test")
    assert captured[0]["job_timeout"] == get_settings().youtube_sync_budget_seconds + 30
    clock = [0]
    client = YouTubeClient("synthetic", clock=lambda: clock[0], transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
    clock[0] = 121
    with pytest.raises(YouTubeError) as error:
        client.identity()
    assert error.value.code == "SYNC_LIMIT" and client.requests == 0
    clock[0] = 0
    for _ in range(90):
        client.get("videos", {})
    with pytest.raises(YouTubeError) as error:
        client.get("videos", {})
    assert error.value.code == "SYNC_LIMIT" and client.requests == 90


def test_retention_expiry_and_metadata_deletion(client, environment):
    run_id = enqueue(client, environment)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)))
    environment.db.expire_all()
    assert statistical_expiry(datetime(2024, 2, 29), environment.config) == datetime(2027, 2, 28)
    expire_youtube_data(environment.db, environment.config, clock=CLOCK + timedelta(days=30))
    video = environment.db.get(YouTubeVideo, VIDEO_ID)
    assert video.title is None and video.published_at is None and video.duration_seconds is None
    assert environment.db.get(Channel, 1).name is None
    assert video.public_statistics is not None
    assert environment.db.scalar(select(VideoDailyStat)) is not None
    expire_youtube_data(environment.db, environment.config, clock=datetime(2029, 10, 15, 12))
    assert environment.db.scalar(select(VideoDailyStat)) is None
    assert video.public_statistics is None


def test_revoked_extended_storage_shortens_retention(client, environment):
    run_id = enqueue(client, environment)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)))
    config = environment.config.model_copy(update={"youtube_extended_storage": False})
    expire_youtube_data(environment.db, config, clock=CLOCK + timedelta(days=30))
    assert environment.db.scalar(select(VideoDailyStat)) is None


def test_maintenance_does_not_fail_queued_sync_and_expires_state(client, environment):
    run_id = enqueue(client, environment)
    future = CLOCK + timedelta(days=10)
    active_queue = SimpleNamespace(fetch_job=lambda _: SimpleNamespace(get_status=lambda **kwargs: JobStatus.QUEUED))
    maintain_youtube(environment.db, environment.config, environment.paths, [active_queue], clock=future)
    assert environment.db.get(SyncRun, run_id).status == "queued"
    maintain_youtube(environment.db, environment.config, environment.paths,
                     [SimpleNamespace(fetch_job=lambda _: None)], clock=future)
    environment.db.expire_all()
    assert environment.db.get(SyncRun, run_id).status == "failed"


def test_init_db_adds_tables_without_altering_existing_schema(client, environment, monkeypatch):
    engine = environment.db.get_bind()
    def columns():
        return [{**column, "type": str(column["type"])} for column in inspect(engine).get_columns("jobs")]
    old_columns = columns()
    new_tables = [VideoDailyStat.__table__, YouTubeVideo.__table__, ChannelConnection.__table__, SyncRun.__table__, Channel.__table__]
    for table in new_tables:
        table.drop(engine)
    monkeypatch.setattr(app_db, "engine", engine)
    app_db.init_db()
    assert {table.name for table in new_tables}.issubset(inspect(engine).get_table_names())
    assert columns() == old_columns


@pytest.mark.parametrize("uri", ["https://example.com/callback", "http://localhost:8000/wrong", "http://localhost:8000/api/intelligence/oauth/callback?q=x"])
def test_redirect_only_allows_loopback_callback(uri):
    with pytest.raises(ValueError):
        Settings(_env_file=None, youtube_oauth_redirect_uri=uri)
