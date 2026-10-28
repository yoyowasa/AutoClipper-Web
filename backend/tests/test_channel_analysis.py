from datetime import UTC, timedelta
from types import SimpleNamespace

import httpx
import pytest
from rq.timeouts import JobTimeoutException
from sqlalchemy import select

import app.api.channel_analysis as api
import app.intelligence.analysis_runner as runner
import app.intelligence.sync as sync
from app.intelligence.analysis_errors import AnalysisError
from app.intelligence.analysis_input import build_analysis_input
from app.intelligence.analysis_prompt import analysis_prompt
from app.intelligence.models import AnalysisRun, Channel, SyncRun, VideoDailyStat
from app.intelligence.policy import expire_youtube_data
from app.intelligence.queue import get_enqueue_channel_analysis
from app.intelligence.recommendation_rules import FRAMEWORK_VERSION
from app.intelligence.production_links import reconcile_safely
from app.main import app
from app.storage.json_io import write_json_atomic
from app.intelligence.youtube_client import YouTubeClient
from test_api_routes import client as client
from test_intelligence import CLOCK, VIDEO_ID, enqueue, transport
from test_intelligence import environment as environment
from test_production_links import record

URL = "/api/intelligence/channels/1/analysis"


@pytest.fixture
def prepared(client, environment, monkeypatch):
    run_id = enqueue(client, environment)
    sync.run_youtube_sync(
        run_id,
        session_factory=environment.factory,
        paths=environment.paths,
        client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)),
    )
    environment.db.get(SyncRun, run_id).queued_at = CLOCK - timedelta(hours=1)
    environment.db.commit()
    monkeypatch.setattr(runner, "now", lambda: CLOCK)
    monkeypatch.setattr(api, "now", lambda: CLOCK)
    calls = []
    app.dependency_overrides[get_enqueue_channel_analysis] = lambda: calls.append
    environment.enqueue_calls = calls
    return environment


def valid_review(context):
    ref = next(id for id, item in context.evidence.items() if item["video_id"] == VIDEO_ID and item["source"] == "youtube_analytics")
    return {
        "id": context.payload["review_id"],
        "channel_id": context.payload["channel"]["id"],
        "batch_run_id": context.payload["batch"]["run_id"],
        "title": "観測と次の確認",
        "summary": "効果はまだ検証していません。",
        "goals": {"normal_views": 100000, "short_views": 1000000, "window_days": 30, "interim_days": 7},
        "recommendation_framework_version": FRAMEWORK_VERSION,
        "reviewed_material": "statistics_and_titles",
        "limitations": ["表示機会と動画本編は未確認です。"],
        "findings": [
            {
                "id": "finding_one",
                "format": "shorts",
                "title": "初期実績を確認する",
                "evidence_ids": [ref],
                "observation": "公式値が返っています。",
                "hypothesis": "題材の適合が候補です。",
                "alternatives": ["公開からの経過時間", "視聴者の違い"],
                "counter_evidence": "母数が小さいです。",
                "next_check": "Studioで表示機会を確認します。",
                "confidence": "low",
            }
        ],
        "proposals": [
            {
                "id": "proposal_one",
                "format": "shorts",
                "priority": 1,
                "title": "題材を先に示す仮説",
                "baseline_video_id": VIDEO_ID,
                "evidence_ids": [ref],
                "reason": "初期7日をそろえて比較するためです。",
                "goal_path": "反応を確認する仮説です。",
                "material_to_find": "単独で成立する場面",
                "title_candidates": ["題材が伝わる案"],
                "hook": "題材を示すテロップ",
                "structure": [{"start": 0, "end": 3, "action": "題材"}, {"start": 3, "end": 20, "action": "内容"}],
                "change_one": "冒頭の題材語",
                "keep_fixed": "尺",
                "primary_metric": "views",
                "result_check": "公開翌日から7日で確認",
                "rejection_condition": "差が判定できないときは保留",
                "recommendation_link": {
                    "surface": "shorts_feed",
                    "viewer_need": "題材がすぐ分かること",
                    "stage": "appeal",
                    "signal_hypothesis": "視聴選択を改善する仮説",
                    "evidence_gap": "表示機会が未取得",
                    "rule_ids": ["shorts_response"],
                },
            }
        ],
    }


class FixedGenerator:
    def __init__(self, *, on_request, **kwargs):
        self.on_request = on_request

    def analyze(self, context):
        self.on_request("a" * 32)
        return valid_review(context)


def execute(prepared, id, factory=FixedGenerator):
    runner.run_channel_analysis(
        id, session_factory=prepared.factory, paths=prepared.paths, config=prepared.config, generator_factory=factory
    )
    prepared.db.expire_all()
    return prepared.db.get(AnalysisRun, id)


def test_input_native_periods_missing_ids_and_production(prepared):
    ctx = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    assert set(ctx.payload["format_videos"]["shorts"]) == {VIDEO_ID}
    reports = [*ctx.payload["channel_reports"], *ctx.videos[VIDEO_ID]["reports"]]
    kinds = {report["kind"] for report in reports}
    assert {"daily", "current", "previous", "first7", "video_period", "public"} <= kinds
    assert "video_format" not in kinds and ctx.payload["deduplicated_reports"] == 1
    assert any("UNAVAILABLE" in report["missing"].values() for report in reports)
    assert all(item["value"] is not None for item in ctx.evidence.values())
    assert any(item["value"] == -1 for item in ctx.evidence.values())
    assert "production_evidence_id" not in ctx.videos[VIDEO_ID]
    item = record(prepared.paths, title="公開動画", created=CLOCK.replace(tzinfo=UTC) - timedelta(days=60))
    item.hookSceneStart, item.hookSceneEnd, item.hookText = 1, 4, "題材を示す"
    write_json_atomic(prepared.paths.production_record(item.recordId), item.model_dump(mode="json"))
    reconcile_safely(prepared.db, prepared.paths)
    ctx = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    id = ctx.videos[VIDEO_ID]["production_evidence_id"]
    assert id in ctx.evidence and ctx.evidence[id]["source"] == "production_record"
    assert ctx.evidence[id]["value"]["hookSceneDuration"] == 3
    assert ctx.evidence[id]["value"]["hasHookScene"] is True
    prompt = analysis_prompt(ctx.payload)
    assert "<untrusted_channel_data>" in prompt and "反対証拠" in prompt and "production:" in prompt


def test_http_enqueue_exclusive_and_success_saved(client, prepared):
    response = client.post(URL, json={})
    assert response.status_code == 202 and response.json()["syncBefore"] == "auto"
    id = response.json()["id"]
    assert prepared.enqueue_calls == [id]
    assert client.post(URL, json={}).status_code == 409
    assert client.get(URL).json()["latestRun"]["status"] == "queued"
    saved = execute(prepared, id)
    assert saved.status == "success" and saved.review["id"] == id and saved.request_id == "a" * 32
    assert saved.requested_model == "gpt-6-astra" and saved.requested_effort == "high"
    assert saved.active_channel_id is None
    assert saved.expires_at == CLOCK + timedelta(days=30)
    listing = client.get(URL)
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    assert listing.json()["latestResult"]["review"]["summary"] == "効果はまだ検証していません。"
    assert len(listing.json()["history"]) == 1
    assert not list((prepared.paths.root / "codex_bridge").glob("*/*.json"))


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_evidence",
        "wrong_channel",
        "wrong_batch",
        "bad_schema",
        "wrong_baseline",
        "wrong_format",
        "wrong_goal",
        "surface_rule",
        "missing_relation",
    ],
)
def test_invalid_output_is_not_saved(client, prepared, problem):
    id = client.post(URL, json={"syncBefore": "never"}).json()["id"]

    class Invalid(FixedGenerator):
        def analyze(self, context):
            self.on_request("b" * 32)
            output = valid_review(context)
            if problem == "unknown_evidence":
                output["findings"][0]["evidence_ids"] = ["invented"]
            elif problem == "wrong_channel":
                output["channel_id"] = 2
            elif problem == "wrong_batch":
                output["batch_run_id"] = "nonexistent_sync"
            elif problem == "bad_schema":
                output["findings"][0]["alternatives"] = []
            elif problem == "wrong_baseline":
                output["proposals"][0]["baseline_video_id"] = "video000009"
            elif problem == "wrong_format":
                output["proposals"][0]["format"] = "videoondemand"
            elif problem == "wrong_goal":
                output["proposals"][0]["primary_metric"] = "averageViewPercentage"
            elif problem == "surface_rule":
                output["proposals"][0]["recommendation_link"]["rule_ids"] = ["viewer_fit"]
            else:
                output["proposals"][0]["recommendation_link"] = None
            return output

    fatal = problem in {"unknown_evidence", "wrong_channel", "wrong_batch", "bad_schema"}
    if fatal:
        with pytest.raises(AnalysisError) as error:
            execute(prepared, id, Invalid)
        assert error.value.code == "CODEX_INVALID_OUTPUT"
    else:
        execute(prepared, id, Invalid)
    prepared.db.expire_all()
    saved = prepared.db.get(AnalysisRun, id)
    assert saved.status == ("failed" if fatal else "success") and saved.active_channel_id is None
    assert saved.validation.report["issues"]
    if fatal:
        assert saved.review is None
    else:
        assert len(saved.review["findings"]) == 1 and saved.review["proposals"] == []


def test_context_change_during_generation_rejects_result(client, prepared):
    id = client.post(URL, json={"syncBefore": "never"}).json()["id"]

    class Changing(FixedGenerator):
        def analyze(self, context):
            with prepared.factory() as db:
                row = db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "current"))
                row.values = {**row.values, "views": 123}
                db.commit()
            return valid_review(context)

    with pytest.raises(AnalysisError) as error:
        execute(prepared, id, Changing)
    assert error.value.code == "CODEX_STALE_EVIDENCE"
    assert prepared.db.get(AnalysisRun, id).review is None


def test_sync_policy_boundaries():
    assert runner.needs_sync("auto", None, CLOCK)
    assert runner.needs_sync("auto", CLOCK - timedelta(hours=24), CLOCK)
    assert not runner.needs_sync("auto", CLOCK - timedelta(hours=24) + timedelta(seconds=1), CLOCK)
    assert runner.needs_sync("always", CLOCK, CLOCK)
    assert not runner.needs_sync("never", CLOCK - timedelta(days=99), CLOCK)


def test_old_sync_is_refreshed_in_same_rq_job(client, prepared, monkeypatch):
    channel = prepared.db.get(Channel, 1)
    channel.last_sync_at = CLOCK - timedelta(hours=25)
    prepared.db.commit()
    calls = []

    def refresh(id, **kwargs):
        calls.append(id)
        sync.run_youtube_sync(id, **kwargs, client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)))

    monkeypatch.setattr(runner, "run_youtube_sync", refresh)
    id = client.post(URL, json={}).json()["id"]
    saved = execute(prepared, id)
    assert len(calls) == 1 and saved.sync_run_id == calls[0]


def test_sync_failure_and_timeout_keep_previous_result(client, prepared, monkeypatch):
    first = client.post(URL, json={"syncBefore": "never"}).json()["id"]
    execute(prepared, first)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-private-error")

    monkeypatch.setattr(runner, "run_youtube_sync", fail)
    second = client.post(URL, json={"syncBefore": "always"}).json()["id"]
    with pytest.raises(AnalysisError) as error:
        execute(prepared, second)
    assert error.value.code == "STATISTICS_FAILED" and "private" not in str(error.value)

    class Timeout(FixedGenerator):
        def analyze(self, context):
            raise JobTimeoutException()

    third = client.post(URL, json={"syncBefore": "never"}).json()["id"]
    with pytest.raises(AnalysisError) as error:
        execute(prepared, third, Timeout)
    assert error.value.code == "CODEX_TIMEOUT"
    assert client.get(URL).json()["latestResult"]["id"] == first


def test_origin_sync_busy_queue_failure_and_retention(client, prepared):
    assert client.post(URL, json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    busy = SyncRun(id="sync_busy", channel_id=1, active_channel_id=1)
    prepared.db.add(busy)
    prepared.db.commit()
    assert client.post(URL, json={}).status_code == 409
    prepared.db.delete(busy)
    prepared.db.commit()
    id = client.post(URL, json={"syncBefore": "never"}).json()["id"]
    execute(prepared, id)
    expire_youtube_data(prepared.db, prepared.config, clock=CLOCK + timedelta(days=30))
    prepared.db.expire_all()
    saved = prepared.db.get(AnalysisRun, id)
    assert saved.status == "expired" and saved.review is None and saved.input_snapshot is None
    assert saved.requested_model == "gpt-6-astra"  # content-free audit remains.
    app.dependency_overrides[get_enqueue_channel_analysis] = lambda: lambda *_: (_ for _ in ()).throw(RuntimeError("private"))
    response = client.post(URL, json={})
    assert response.status_code == 503 and "private" not in response.text


def test_context_limit_fails_before_request(prepared):
    context = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    context.payload["oversized"] = "x" * 280000
    with pytest.raises(ValueError, match="CODEX_CONTEXT_TOO_LARGE"):
        analysis_prompt(context.payload)


def test_input_expiry_and_connection_and_missing_evidence(prepared):
    from app.intelligence.models import ChannelConnection

    channel = prepared.db.get(Channel, 1)
    channel.metadata_updated_at = CLOCK - timedelta(days=29)
    prepared.db.commit()
    context = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    assert context.expires_at == CLOCK + timedelta(days=1)
    channel.metadata_updated_at = CLOCK - timedelta(days=30)
    prepared.db.commit()
    with pytest.raises(ValueError, match="CODEX_EVIDENCE_UNAVAILABLE"):
        build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    channel.metadata_updated_at = CLOCK
    connection = prepared.db.get(ChannelConnection, 1)
    connection.status = "reconnect_required"
    prepared.db.commit()
    with pytest.raises(ValueError, match="OWN_OAUTH_REQUIRED"):
        build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    connection.status = "connected"
    for row in prepared.db.scalars(select(VideoDailyStat)):
        row.values = {key: None for key in row.values}
    prepared.db.commit()
    with pytest.raises(ValueError, match="CODEX_EVIDENCE_UNAVAILABLE"):
        build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)


def test_rq_failure_and_maintenance_reconcile_without_touching_other_work(client, prepared):
    from app.intelligence.maintenance import maintain_youtube

    id = client.post(URL, json={}).json()["id"]
    runner.record_rq_analysis_failure(prepared.db, SimpleNamespace(func_name="other.task", args=[id]))
    assert prepared.db.get(AnalysisRun, id).status == "queued"
    maintain_youtube(
        prepared.db, prepared.config, prepared.paths, [SimpleNamespace(fetch_job=lambda _: None)], clock=CLOCK + timedelta(hours=1)
    )
    prepared.db.expire_all()
    assert prepared.db.get(AnalysisRun, id).error_code == "WORKER_INTERRUPTED"
