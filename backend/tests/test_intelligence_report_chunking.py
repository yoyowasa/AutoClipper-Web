import json
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select

import app.intelligence.sync as sync
import app.intelligence.youtube_client as youtube_client
from app.intelligence.collection import split_video_day_requests
from app.intelligence.common import YouTubeError
from app.intelligence.models import SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.youtube_client import MAX_REQUESTS, METRICS, YouTubeClient
from test_api_routes import client as client
from test_intelligence import CHANNEL_ID, enqueue, transport
from test_intelligence import environment as environment

START, END = date(2026, 8, 16), date(2026, 10, 14)


@pytest.mark.parametrize("count,expected", [(85, 29), (20, 7), (1, 1)])
def test_day_video_chunks_cover_every_video_and_day_once(count, expected):
    ids = [f"video{i:06}" for i in range(count)]
    chunks = split_video_day_requests(ids, START, END)
    assert len(chunks) == expected
    assert [id for chunk in chunks for id in chunk.video_ids] == ids
    assert all(chunk.start == START and chunk.end == END and len(chunk.video_ids) * 60 <= 200 for chunk in chunks)


def test_chunking_can_split_long_period_and_empty_inventory():
    end = START + timedelta(days=400)
    chunks = split_video_day_requests(["video000001"], START, end)
    assert [(chunk.end - chunk.start).days + 1 for chunk in chunks] == [200, 200, 1]
    assert chunks[0].start == START and chunks[-1].end == end
    assert all(left.end + timedelta(days=1) == right.start for left, right in zip(chunks, chunks[1:]))
    assert split_video_day_requests([], START, END) == []
    with pytest.raises(ValueError):
        split_video_day_requests([], END, START)


def analytics_response(rows):
    return httpx.Response(200, json={"columnHeaders": [{"name": key} for key in rows[0]],
                                     "rows": [list(row.values()) for row in rows]})


def test_exactly_200_rows_never_requests_second_page():
    calls = []
    end = START + timedelta(days=199)
    rows = [{"day": str(START + timedelta(days=index)), **dict.fromkeys(METRICS, 1)} for index in range(200)]
    def mocked(request):
        calls.append(request)
        return analytics_response(rows)
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(mocked))
    assert len(api.report(CHANNEL_ID, START, end, "day,video", ["video000001"])) == 200
    assert len(calls) == 1 and calls[0].url.params["startIndex"] == "1"
    with pytest.raises(YouTubeError) as error:
        api.report(CHANNEL_ID, START, end + timedelta(days=1), "day,video", ["video000001"])
    assert error.value.code == "API_BAD_REQUEST" and len(calls) == 1


def failure_response(status=500, reason="internalError"):
    return httpx.Response(status, json={"error": {"errors": [{"reason": reason}], "message": "synthetic-private-body"}})


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@pytest.mark.parametrize("recovers", [True, False])
def test_5xx_retries_twice_with_short_waits(status, recovers):
    calls, waits = [], []
    def mocked(request):
        calls.append(request)
        return httpx.Response(200, json={}) if recovers and len(calls) == 3 else failure_response(status)
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(mocked), sleep=waits.append)
    if recovers:
        assert api.get("reports", {}, analytics=True) == {}
    else:
        with pytest.raises(YouTubeError) as error:
            api.get("reports", {}, analytics=True)
        assert error.value.details() == {"reason": "API_5XX", "httpStatus": status, "googleReasons": ["internalError"]}
        assert "synthetic-private-body" not in str(error.value)
    assert len(calls) == api.requests == 3
    assert waits == [0.25, 0.5]


@pytest.mark.parametrize("status,reason,code", [
    (400, "badRequest", "API_BAD_REQUEST"), (401, "authError", "RECONNECT_REQUIRED"),
    (403, "forbidden", "FORBIDDEN"), (403, "quotaExceeded", "QUOTA_EXCEEDED"),
    (404, "notFound", "API_NOT_FOUND"), (409, "conflict", "API_CONFLICT"),
    (410, "gone", "API_GONE"), (429, "rateLimitExceeded", "QUOTA_EXCEEDED"), (418, "other", "API_HTTP_ERROR"),
])
def test_other_http_failures_keep_status_reason_and_do_not_retry(status, reason, code):
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(lambda _: failure_response(status, reason)),
                        sleep=lambda _: pytest.fail("non-5xx must not retry"))
    with pytest.raises(YouTubeError) as error:
        api.get("reports", {}, analytics=True)
    assert error.value.code == code and error.value.http_status == status and error.value.reasons == [reason]
    assert api.requests == 1


def test_retry_wait_and_attempts_respect_deadline_and_request_limit():
    clock, waits = [0.0], []
    def wait(seconds):
        waits.append(seconds)
        clock[0] += seconds
    api = YouTubeClient("synthetic", budget_seconds=0.3, clock=lambda: clock[0], sleep=wait,
                        transport=httpx.MockTransport(lambda _: failure_response()))
    with pytest.raises(YouTubeError) as error:
        api.get("reports", {}, analytics=True)
    assert error.value.code == "SYNC_LIMIT" and api.requests == 2 and waits == [0.25]
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(lambda _: failure_response()), sleep=wait)
    api.requests = MAX_REQUESTS - 1
    with pytest.raises(YouTubeError) as error:
        api.get("reports", {}, analytics=True)
    assert error.value.code == "SYNC_LIMIT" and api.requests == MAX_REQUESTS and waits == [0.25]


def channel_transport(count, calls, fail=None):
    ids = [f"video{i:06}" for i in range(count)]
    def mocked(request):
        calls.append(request)
        endpoint, params = request.url.path.rsplit("/", 1)[-1], request.url.params
        if fail:
            error = fail(endpoint, params)
            if error is not None:
                return error
        if endpoint == "playlistItems":
            offset = int(params.get("pageToken", "0"))
            payload = {"items": [{"contentDetails": {"videoId": id}} for id in ids[offset:offset + 50]]}
            if offset + 50 < len(ids):
                payload["nextPageToken"] = str(offset + 50)
            return httpx.Response(200, json=payload)
        if endpoint == "videos":
            return httpx.Response(200, json={"items": [{"id": id, "snippet": {
                "channelId": CHANNEL_ID, "title": "公開動画", "publishedAt": "2026-08-01T00:00:00Z"},
                "contentDetails": {"duration": "PT1M"}, "status": {"privacyStatus": "public"}}
                for id in params["id"].split(",")]})
        if endpoint != "reports":
            return transport(request)
        dimensions = params.get("dimensions", "").split(",") if params.get("dimensions") else []
        selected = params["filters"].removeprefix("video==").split(",") if params.get("filters") else [None]
        begin, finish = date.fromisoformat(params["startDate"]), date.fromisoformat(params["endDate"])
        days = [begin + timedelta(days=index) for index in range((finish - begin).days + 1)] if "day" in dimensions else [None]
        rows = []
        for video in selected:
            for day in days:
                values = {"day": str(day), "video": video, "creatorContentType": "SHORTS"}
                rows.append({**{key: values[key] for key in dimensions}, **dict.fromkeys(METRICS, 1)})
        assert len(rows) <= 200
        assert params["startIndex"] == "1"
        return analytics_response(rows)
    return mocked


def run_sync(environment, run_id, mocked):
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(mocked), sleep=lambda _: None)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths, config=environment.config, client=api)
    environment.db.expire_all()
    return environment.db.get(SyncRun, run_id)


def test_85_video_sync_stays_within_budget_and_resumes_initial_reports(client, environment):
    run_id = enqueue(client, environment)
    calls = []
    saved = run_sync(environment, run_id, channel_transport(85, calls))
    assert saved.status == "partial" and saved.truncated and saved.request_count == 89 <= MAX_REQUESTS
    pending = next(item["requests"] for item in saved.missing_reports if item["kind"] == "pending_reports")
    assert len(pending) == 120 and {item["kind"] for item in pending} == {"first7", "first30"}
    daily = environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "video_day")).all()
    assert len(daily) == 85 * 60
    for _ in range(3):
        next_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
        calls.clear()
        resumed = run_sync(environment, next_id, channel_transport(85, calls))
        assert resumed.request_count <= MAX_REQUESTS
        assert all(not (request.url.params.get("filters") and "day" in request.url.params.get("dimensions", "")) for request in calls)
    assert resumed.status == "success" and not resumed.truncated
    first7 = environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "first7")).all()
    assert len(first7) == 85
    assert len(environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "first30")).all()) == 85


def test_20_videos_finish_without_truncation(client, environment):
    saved = run_sync(environment, enqueue(client, environment), channel_transport(20, []))
    assert saved.status == "success" and saved.request_count == 55 and not saved.truncated
    daily = environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "video_day")).all()
    assert len(daily) == 1200


def test_request_limit_defers_exact_unfinished_requests_until_next_sync(client, environment, monkeypatch):
    monkeypatch.setattr(youtube_client, "MAX_REQUESTS", 8)
    saved = run_sync(environment, enqueue(client, environment), channel_transport(3, []))
    assert saved.status == "partial" and saved.truncated and saved.request_count == 8
    pending = next(item["requests"] for item in saved.missing_reports if item["kind"] == "pending_reports")
    assert [item["kind"] for item in pending] == ["video_format", "first30", "first7", "first30", "first7", "first30", "first7"]
    assert environment.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "video_day")) is not None
    calls = []
    next_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    resumed = run_sync(environment, next_id, channel_transport(3, calls))
    assert resumed.status == "partial" and resumed.request_count == 8
    remaining = next(item["requests"] for item in resumed.missing_reports if item["kind"] == "pending_reports")
    assert len(remaining) == 5 and remaining[0]["kind"] == "first7"
    for _ in range(3):
        final_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
        final = run_sync(environment, final_id, channel_transport(3, []))
        assert final.request_count <= 8
    assert final.status == "success"
    assert len(environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "first7")).all()) == 3
    assert len(environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "first30")).all()) == 3


def test_time_limit_saves_completed_reports_and_checkpoint(client, environment):
    run_id = enqueue(client, environment)
    clock = [0]
    mocked = channel_transport(3, [])
    def slow(request):
        result = mocked(request)
        clock[0] += 10
        return result
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(slow), clock=lambda: clock[0])
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths, client=api)
    environment.db.expire_all()
    saved = environment.db.get(SyncRun, run_id)
    assert saved.status == "partial" and saved.error_code == "SYNC_LIMIT" and saved.truncated
    assert saved.request_count == 12 and clock[0] == 120
    pending = next(item["requests"] for item in saved.missing_reports if item["kind"] == "pending_reports")
    assert [item["kind"] for item in pending] == ["first30", "first7", "first30", "first7"]
    next_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    assert run_sync(environment, next_id, channel_transport(3, [])).status == "success"


@pytest.mark.parametrize("optional_kind", ["video_day", "video_period", "video_format", "first7", "first30"])
def test_optional_5xx_records_missing_and_keeps_other_reports(client, environment, optional_kind):
    run_id = enqueue(client, environment)
    dims = {"video_day": "day,video", "video_period": "video", "video_format": "video,creatorContentType",
            "first7": "creatorContentType", "first30": "creatorContentType"}[optional_kind]
    def fail(endpoint, params):
        if endpoint == "reports" and params.get("filters") and params.get("dimensions") == dims:
            if optional_kind in {"first7", "first30"}:
                days = (date.fromisoformat(params["endDate"]) - date.fromisoformat(params["startDate"])).days + 1
                if days != (7 if optional_kind == "first7" else 30):
                    return None
            return failure_response()
    calls = []
    saved = run_sync(environment, run_id, channel_transport(3, calls, fail))
    assert saved.status == "partial" and not saved.truncated and saved.error_code == "API_5XX"
    missing = [item for item in saved.missing_reports if item["reason"] == "API_5XX"]
    assert len(missing) == 3 and all(item["kind"] == optional_kind and item["googleReasons"] == ["internalError"] for item in missing)
    assert "synthetic-private-body" not in json.dumps(saved.missing_reports)
    row = environment.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == optional_kind))
    assert set(row.values.values()) == {None} and set(row.missing_reasons.values()) == {"API_5XX"}
    assert environment.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "daily")).values["views"] == 1
    displayed = client.get("/api/intelligence/channels").json()["channels"][0]["latestRun"]
    assert displayed["errorCode"] == "API_5XX" and displayed["missingReportCount"] == 0


@pytest.mark.parametrize("required", ["channels", "playlistItems", "videos", "daily", "current", "previous"])
def test_required_5xx_fails_sync_and_records_safe_details(client, environment, required):
    run_id = enqueue(client, environment)
    def fail(endpoint, params):
        if endpoint == required or (endpoint == "reports" and not params.get("filters") and
                                   (params.get("dimensions") == "day" if required == "daily" else
                                    (required == "current" and params["endDate"] == str(END)) or
                                    (required == "previous" and params["endDate"] == str(END - timedelta(days=28))))):
            return failure_response(503, "backendError")
    with pytest.raises(YouTubeError) as error:
        run_sync(environment, run_id, channel_transport(3, [], fail))
    assert error.value.code == "API_5XX"
    environment.db.expire_all()
    saved = environment.db.get(SyncRun, run_id)
    assert saved.status == "failed" and saved.error_code == "API_5XX"
    assert saved.missing_reports == [{"kind": "sync_failure", "reason": "API_5XX", "httpStatus": 503, "googleReasons": ["backendError"]}]
    assert environment.db.scalar(select(YouTubeVideo)) is None
    assert environment.db.scalar(select(VideoDailyStat)) is None


def test_400_stored_separately_and_provider_message_is_never_stored(client, environment):
    run_id = enqueue(client, environment)
    def fail(endpoint, params):
        if endpoint == "reports":
            return failure_response(400, "badRequest")
    with pytest.raises(YouTubeError):
        run_sync(environment, run_id, channel_transport(3, [], fail))
    environment.db.expire_all()
    saved = environment.db.get(SyncRun, run_id)
    assert saved.error_code == "API_BAD_REQUEST"
    assert saved.missing_reports[0]["httpStatus"] == 400 and saved.missing_reports[0]["googleReasons"] == ["badRequest"]
    assert "synthetic-private-body" not in json.dumps(saved.missing_reports)


@pytest.mark.parametrize("status,reason", [(400, "badRequest"), (401, "authError"), (403, "forbidden"), (429, "quotaExceeded")])
def test_non_5xx_optional_failures_still_fail_whole_sync(client, environment, status, reason):
    run_id = enqueue(client, environment)
    def fail(endpoint, params):
        if endpoint == "reports" and params.get("filters"):
            return failure_response(status, reason)
    with pytest.raises(YouTubeError):
        run_sync(environment, run_id, channel_transport(3, [], fail))
    environment.db.expire_all()
    assert environment.db.get(SyncRun, run_id).status == "failed"
    assert environment.db.scalar(select(VideoDailyStat)) is None


def test_transient_failure_preserves_previous_values_and_recovery_removes_placeholder(client, environment):
    original_id = enqueue(client, environment)
    run_sync(environment, original_id, channel_transport(3, []))
    def fail(endpoint, params):
        if endpoint == "reports" and params.get("filters"):
            return failure_response()
    failed_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    saved = run_sync(environment, failed_id, channel_transport(3, [], fail))
    assert saved.status == "partial"
    previous = environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "video_period")).all()
    assert len(previous) == 3 and all(row.values["views"] == 1 and row.sync_run_id == original_id for row in previous)
    placeholders = [row for row in environment.db.scalars(select(VideoDailyStat)) if "API_5XX" in row.missing_reasons.values()]
    assert len(placeholders) == 12 and {row.kind for row in placeholders} == {"video_day", "video_format", "first7", "first30"}
    recovered_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    assert run_sync(environment, recovered_id, channel_transport(3, [])).status == "success"
    assert not [row for row in environment.db.scalars(select(VideoDailyStat)) if "API_5XX" in row.missing_reasons.values()]


def test_malformed_google_reasons_are_not_persisted():
    api = YouTubeClient("synthetic", transport=httpx.MockTransport(lambda _: httpx.Response(400, json={"error": {
        "message": "synthetic-private-body", "errors": [{"reason": "badRequest"}, {"reason": {"secret": "private"}},
                                                     {"reason": "Bearer synthetic-token"}]}})))
    with pytest.raises(YouTubeError) as error:
        api.get("reports", {}, analytics=True)
    assert error.value.reasons == ["badRequest"]
    assert "private" not in json.dumps(error.value.details())
