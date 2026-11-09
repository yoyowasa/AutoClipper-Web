from datetime import UTC, timedelta

import httpx
import pytest
from sqlalchemy import select

import app.intelligence.analysis_input as inputs
from app.intelligence.analysis_budget import fit_analysis_budget
from app.intelligence.analysis_prompt import render_analysis_prompt
from app.intelligence.models import VideoDailyStat, YouTubeVideo
from app.intelligence.production_links import reconcile_safely
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_channel_analysis import URL, FixedGenerator, execute, prepared as prepared, valid_review
from test_intelligence import CLOCK, VIDEO_ID, enqueue, environment as environment, transport
from test_intelligence_report_chunking import run_sync
from test_production_links import record

SOURCE_ID = "source00001"
OTHER_ID = "source00002"


def test_fixed_windows_saved_once_and_used_as_evidence(client, environment):
    calls = []

    def mocked(request):
        if request.url.params.get("dimensions") == "elapsedVideoTimeRatio":
            calls.append(request.url.params)
        return transport(request)

    run = run_sync(environment, enqueue(client, environment), mocked)
    assert run.status == "success"
    assert [(q["startDate"], q["endDate"]) for q in calls] == [
        ("2026-09-01", "2026-09-07"), ("2026-09-01", "2026-09-30"),
    ]
    assert all(q["filters"] == f"video=={VIDEO_ID}" and q["startIndex"] == "1" and
               q["metrics"] == "audienceWatchRatio,relativeRetentionPerformance" for q in calls)
    rows = list(environment.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind.in_(["retention7", "retention30"]))))
    assert len(rows) == 2
    assert all(len(row.values["audienceWatchRatio"]) == 100 and row.values["audienceWatchRatio"]["0.15"] == 0.83 for row in rows)
    calls.clear()
    run_sync(environment, client.post("/api/intelligence/channels/1/sync").json()["id"], mocked)
    assert not calls
    ctx = inputs.build_analysis_input(environment.db, environment.paths, environment.config, 1, "retention_test", CLOCK)
    assert "retention" not in ctx.payload["unavailable_reports"]
    assert ctx.evidence[f"v:{VIDEO_ID}:retention7:watch_at_10s"]["value"] == 0.83
    assert ctx.evidence[f"v:{VIDEO_ID}:retention30:relative_at_3s"]["value"] == 0.56


@pytest.mark.parametrize("returned,publication", [(False, None), (True, "2026-10-12T00:00:00Z")])
def test_retention_no_rows_and_unreached_are_not_zero(client, environment, returned, publication):
    calls = []

    def mocked(request):
        if request.url.params.get("dimensions") == "elapsedVideoTimeRatio":
            calls.append(request)
            return transport(request) if returned else httpx.Response(200, json={"rows": []})
        response = transport(request)
        if publication and request.url.path.endswith("/videos"):
            data = response.json()
            data["items"][0]["snippet"]["publishedAt"] = publication
            return httpx.Response(200, json=data)
        return response

    run = run_sync(environment, enqueue(client, environment), mocked)
    ctx = inputs.build_analysis_input(environment.db, environment.paths, environment.config, 1, "retention_missing", CLOCK)
    reports = [r for r in ctx.videos[VIDEO_ID]["reports"] if r["kind"].startswith("retention")]
    assert len(reports) == 2 and all(not r["values"] for r in reports)
    if publication:
        assert not calls and all(r["missing"]["report"] == "WINDOW_NOT_REACHED" for r in reports)
    else:
        assert len(calls) == 2 and all(r["missing"]["report"] == "NO_ROWS" for r in reports)
        assert {r["kind"] for r in run.missing_reports if r["reason"] == "NO_ROWS"} >= {"retention7", "retention30"}
        calls.clear()
        run_sync(environment, client.post("/api/intelligence/channels/1/sync").json()["id"], mocked)
        assert len(calls) == 2


@pytest.mark.parametrize("origin", ["production_record", "description", None])
def test_explicit_source_and_weekly_evidence_in_saved_snapshot(client, prepared, origin):
    if origin == "production_record":
        item = record(prepared.paths, title="公開動画", created=CLOCK.replace(tzinfo=UTC) - timedelta(days=60))
        item.source.url = f"https://www.youtube.com/live/{SOURCE_ID}"
        write_json_atomic(prepared.paths.production_record(item.recordId), item.model_dump(mode="json"))
        reconcile_safely(prepared.db, prepared.paths)
    lookups = []

    def mocked(request):
        if not request.url.path.endswith("/videos"):
            return transport(request)
        id = request.url.params["id"]
        if id == VIDEO_ID:
            payload = transport(request).json()
            payload["items"][0]["snippet"]["description"] = (
                f"元配信\nhttps://youtu.be/{OTHER_ID}" if origin else f"関連動画 https://youtu.be/{OTHER_ID}")
            return httpx.Response(200, json=payload)
        lookups.append(id)
        return httpx.Response(200, json={"items": [{"id": id, "snippet": {"publishedAt": "2026-08-29T02:00:00Z"},
            "liveStreamingDetails": {"actualStartTime": "2026-08-30T02:00:00Z"}}]})

    run_sync(prepared, client.post("/api/intelligence/channels/1/sync").json()["id"], mocked)
    assert lookups == ([SOURCE_ID] if origin == "production_record" else [OTHER_ID] if origin else [])

    class WeeklyGenerator(FixedGenerator):
        def analyze(self, context):
            result = valid_review(context)
            weekly = context.payload["weekly_trends"]["groups"][0]
            assert context.evidence[weekly["id"]]["source"] == "independent_aggregation"
            result["findings"][0]["evidence_ids"].append(weekly["id"])
            if origin:
                result["findings"][0]["evidence_ids"].append(f"s:{VIDEO_ID}")
            return result

    run = execute(prepared, client.post(URL, json={}).json()["id"], WeeklyGenerator)
    assert run.status == "success"
    video = run.input_snapshot["videos"][0]
    assert any(r["values"].get("watch_at_10s") == 0.83 for r in video["reports"])
    assert ("production" in video) == (origin == "production_record")
    if origin == "production_record":
        assert video["production"]["value"]["createdAt"] == item.createdAt.isoformat()
    group = run.input_snapshot["weekly_trends"]["groups"][0]
    assert group["video_count"] == 1 and group["first7_views"] == {"count": 1, "median": 1}
    assert group["retention"]["retention7:watch_at_10s"] == {"count": 1, "median": 0.83}
    if origin:
        timing = video["source_timing"]["value"]
        assert timing["link_origin"] == origin and timing["days_since_source"] == 2
        assert group["days_since_source"] == {"count": 1, "median": 2, "min": 2, "max": 2,
                                              "counts_by_age": {"0_1": 0, "2_7": 1, "8_30": 0, "31_plus": 0}}
    else:
        assert "source_timing" not in video
        assert group["days_since_source"]["median"] is None


def test_weekly_totals_include_video_omitted_by_prompt_budget(prepared, monkeypatch):
    prepared.db.add(YouTubeVideo(id="video000002", channel_id=1, title="最近の動画",
        published_at=CLOCK - timedelta(days=3), format="shorts", availability="available", metadata_updated_at=CLOCK))
    prepared.db.commit()
    args = (prepared.db, prepared.paths, prepared.config, 1, "retention_budget", CLOCK)
    full = inputs.build_analysis_input(*args)
    limit = len(render_analysis_prompt(full.payload)) - 100
    monkeypatch.setattr(inputs, "fit_analysis_budget", lambda payload: fit_analysis_budget(payload, budget=limit))
    fitted = inputs.build_analysis_input(*args)
    assert VIDEO_ID not in fitted.videos and fitted.payload["weekly_trends"] == full.payload["weekly_trends"]
    group = next(g for g in fitted.payload["weekly_trends"]["groups"] if g["retention"])
    assert group["retention"]["retention7:watch_at_10s"]["median"] == 0.83
    assert group["id"] in fitted.evidence
    assert f"v:{VIDEO_ID}:retention7:watch_at_10s" not in fitted.evidence
