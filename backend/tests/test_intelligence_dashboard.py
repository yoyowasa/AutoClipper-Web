from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import inspect, select

import app.api.intelligence_dashboard as api
from app.intelligence.dashboard import dashboard_data, evidence_video_ids
from app.intelligence.dashboard_reports import duration_band, first7_report
from app.intelligence.models import (
    AnalysisRun, Channel, ChannelConnection, ImprovementTrial, ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo,
)
from app.intelligence.policy import expire_youtube_data
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_intelligence import environment as environment
from test_production_links import record

STAMP = datetime(2026, 10, 22, 12)
BASE = "/api/intelligence/channels/1"


def stat(db, *, kind, start, end=None, video=None, values=None, format=None, observed=STAMP):
    row = VideoDailyStat(channel_id=1, sync_run_id="sync_dashboard", kind=kind, video_id=video,
        dimension_key=f"{start}:{video or ''}:{format or ''}", period_start=start, period_end=end or start,
        dimensions={"creatorContentType": format} if format else {}, values=values or {"views": 10, "engagedViews": None},
        missing_reasons={"engagedViews": "API_5XX"}, observed_at=observed, expires_at=observed + timedelta(days=365))
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def dashboard(environment, monkeypatch):
    db = environment.db
    monkeypatch.setattr(api, "now", lambda: STAMP)
    db.add(Channel(id=1, external_id="UC" + "a" * 22, name="確認用", metadata_updated_at=STAMP))
    db.flush()
    db.add(ChannelConnection(channel_id=1))
    db.add(SyncRun(id="sync_dashboard", channel_id=1, status="success", queued_at=STAMP,
                   last_report_date=date(2026, 10, 20)))
    db.flush()
    for index, format in enumerate(("shorts", "shorts", "long"), start=1):
        db.add(YouTubeVideo(id=f"video{index:06}", channel_id=1, title=f"動画{index}", format=format,
            published_at=datetime(2026, 9, index, 4), duration_seconds=60 if format == "shorts" else 200,
            metadata_updated_at=STAMP, availability="available"))
    db.flush()
    stat(db, kind="current", start=date(2026, 9, 23), end=date(2026, 10, 20), values={"views": 100, "subscribersGained": 0})
    stat(db, kind="previous", start=date(2026, 8, 26), end=date(2026, 9, 22), values={"views": 80})
    for index in (1, 2, 3):
        id = f"video{index:06}"
        stat(db, kind="first7", start=date(2026, 9, index), end=date(2026, 9, index + 6), video=id,
             format="shorts" if index != 3 else "videoOnDemand", values={"views": 100 * index,
                "engagedViews": 50 * index, "averageViewPercentage": 110, "averageViewDuration": 20, "subscribersGained": 0})
        stat(db, kind="video_day", start=date(2026, 10, 20), video=id, values={"views": index, "engagedViews": None})
        stat(db, kind="video_period", start=date(2026, 9, 23), end=date(2026, 10, 20), video=id, values={"views": 10 * index})
    item = record(environment.paths, id="exp_trial_target")
    item.characterPresetName = "検証キャラ"
    write_json_atomic(environment.paths.production_record(item.recordId), item.model_dump(mode="json"))
    db.add(ProductionLink(record_family_id=item.recordId, record_id=item.recordId, youtube_video_id="video000002", mode="manual"))
    db.add(AnalysisRun(id="analysis_trial_test", channel_id=1, status="success", queued_at=STAMP,
        finished_at=STAMP, expires_at=STAMP + timedelta(days=20), input_snapshot={"videos": []}, review={"proposals": [{
        "id": "proposal_one", "format": "shorts", "priority": 1, "title": "試す", "baseline_video_id": "video000001",
        "evidence_ids": ["r:1:views"], "reason": "理由", "goal_path": "仮説", "material_to_find": "題材",
        "title_candidates": ["案"], "hook": "冒頭", "structure": [{"start": 0, "end": 3, "action": "題材"},
        {"start": 3, "end": 10, "action": "展開"}], "change_one": "冒頭に題材語", "keep_fixed": "尺",
        "primary_metric": "views", "result_check": "7暦日を比較", "rejection_condition": "増えなければ保留"}]}))
    db.commit()
    return environment


def test_dashboard_native_derived_missing_and_linked_production(client, dashboard):
    response = client.get(BASE + "/dashboard")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["current"]["source"] == "youtube_analytics"
    assert data["current"]["metrics"]["views"]["value"] == 100
    assert data["current"]["metrics"]["subscribersGained"]["value"] == 0
    assert data["current"]["metrics"]["engagedViews"] == {"value": None, "missingReason": "API_5XX", "observedSubtotal": None}
    assert len(data["daily"]) == 56 and data["daily"][0]["metrics"]["views"]["value"] is None
    target = next(video for video in data["videos"] if video["id"] == "video000002")
    assert target["production"]["characterPresetName"] == "検証キャラ" and len(target["aggregateGroupIds"]) == 7
    short = client.get(BASE + "/dashboard?format=shorts").json()
    assert len(short["videos"]) == 2 and short["current"]["source"] == "independent_aggregation"
    assert short["current"]["metrics"]["views"]["value"] is None
    assert short["current"]["metrics"]["views"]["observedSubtotal"] == 3
    assert short["current"]["metrics"]["views"]["missingReason"] == "PARTIAL_COVERAGE"
    assert short["daily"][-1]["metrics"]["views"]["value"] == 3
    assert short["daily"][-1]["metrics"]["engagedViews"]["value"] is None
    assert client.get(BASE + "/dashboard?format=invalid").status_code == 422


def test_first7_is_calendar_aligned_and_never_daily_reaveraged(client, dashboard):
    rows = list(dashboard.db.scalars(select(VideoDailyStat).where(VideoDailyStat.video_id == "video000001")))
    video = dashboard.db.get(YouTubeVideo, "video000001")
    report = first7_report(video, rows, date(2026, 10, 20))
    assert report.start == date(2026, 9, 1)  # UTC September 1, 04:00 is August 31 in Pacific time.
    assert report.end == date(2026, 9, 7) and report.metrics["averageViewPercentage"].value == 110
    video.published_at += timedelta(days=1)
    assert first7_report(video, rows, date(2026, 10, 20)).reason == "NO_ROWS"
    video.published_at = datetime(2026, 10, 20)
    assert first7_report(video, rows, date(2026, 10, 20)).reason == "FIRST7_NOT_READY"


def adopt(client):
    response = client.post(BASE + "/analysis/analysis_trial_test/proposals/proposal_one/adopt")
    assert response.status_code == 200, response.text
    return response.json()


def edit_body(trial, **overrides):
    return {key: trial[key] for key in ("baselineVideoId", "targetVideoId", "changeNote", "keepFixed", "primaryMetric",
        "rejectionCondition", "resultCheck", "status")} | {"expectedUpdatedAt": trial["updatedAt"]} | overrides


def test_adopt_assign_compare_edit_delete_and_idempotence(client, dashboard, monkeypatch):
    trial = adopt(client)
    assert adopt(client)["id"] == trial["id"]
    assert trial["changeNote"] == "冒頭に題材語" and trial["rejectionCondition"] == "増えなければ保留"
    url = BASE + "/trials/" + trial["id"]
    response = client.put(url, json=edit_body(trial, targetVideoId="video000002"))
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["direction"] == "increase" and not saved["comparisonIssues"]
    assert saved["recordedAfterPublication"] is True
    assert saved["baseline"]["first7"]["start"] == "2026-09-01"
    assert saved["target"]["first7"]["start"] == "2026-09-02"
    assert saved["causalVerdict"] and "断定できません" in saved["causalVerdict"]
    monkeypatch.setattr(api, "now", lambda: STAMP + timedelta(seconds=1))
    edited = client.put(url, json=edit_body(saved, changeNote="タイトルに題材語", status="closed"))
    assert edited.status_code == 200 and edited.json()["registeredAt"] != trial["registeredAt"]
    assert client.put(url, json=edit_body(saved)).status_code == 409
    assert client.delete(url, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.delete(url).status_code == 204
    assert client.get(BASE + "/trials").json() == []
    assert dashboard.db.get(YouTubeVideo, "video000002") is not None
    assert dashboard.paths.production_record("exp_trial_target").exists()


@pytest.mark.parametrize("target", ["video000001", "video000003", "video999999"])
def test_target_must_be_newer_own_and_linked(client, dashboard, target):
    trial = adopt(client)
    assert client.put(BASE + "/trials/" + trial["id"], json=edit_body(trial, targetVideoId=target)).status_code == 422


@pytest.mark.parametrize("issue", ["FORMAT_MISMATCH", "DURATION_MISMATCH", "METRIC_UNAVAILABLE", "TARGET_NOT_LINKED"])
def test_trial_mismatches_are_shown_without_verdict(client, dashboard, issue):
    trial = adopt(client)
    url = BASE + "/trials/" + trial["id"]
    assert client.put(url, json=edit_body(trial, targetVideoId="video000002")).status_code == 200
    video = dashboard.db.get(YouTubeVideo, "video000002")
    native = dashboard.db.scalar(select(VideoDailyStat).where(VideoDailyStat.video_id == video.id, VideoDailyStat.kind == "first7"))
    if issue == "FORMAT_MISMATCH":
        video.format = "long"
        native.dimensions = {"creatorContentType": "videoOnDemand"}
    elif issue == "DURATION_MISMATCH":
        video.duration_seconds = 20
    elif issue == "METRIC_UNAVAILABLE":
        native.values = {**native.values, "views": None}
    else:
        dashboard.db.delete(dashboard.db.get(ProductionLink, "exp_trial_target"))
    dashboard.db.commit()
    saved = client.get(BASE + "/trials").json()[0]
    assert issue in saved["comparisonIssues"] and saved["direction"] is None


def test_expiry_preserves_intent_but_never_exposes_expired_metrics_or_metadata(client, dashboard, monkeypatch):
    trial = adopt(client)
    before = client.get(BASE + "/trials").json()[0]
    later = STAMP + timedelta(days=1100)
    expire_youtube_data(dashboard.db, dashboard.config, clock=later)
    monkeypatch.setattr(api, "now", lambda: later)
    after = client.get(BASE + "/trials").json()[0]
    assert after["id"] == trial["id"] and after["changeNote"] == before["changeNote"]
    assert after["baseline"] is None and "BASELINE_UNAVAILABLE" in after["comparisonIssues"]
    assert client.get(BASE + "/dashboard").json()["current"]["metrics"]["views"]["value"] is None
    assert "improvement_trials" in inspect(dashboard.db.get_bind()).get_table_names()
    assert dashboard.db.get(ImprovementTrial, trial["id"]) is not None
    edited = client.put(BASE + "/trials/" + trial["id"], json=edit_body(after, status="closed", changeNote="検証を保留"))
    assert edited.status_code == 200 and edited.json()["status"] == "closed"
    assert edited.json()["baseline"] is None


def test_expired_analysis_and_cross_channel_writes_are_rejected(client, dashboard):
    assert client.post(BASE + "/analysis/analysis_trial_test/proposals/proposal_one/adopt",
                       headers={"origin": "https://evil.example"}).status_code == 403
    dashboard.db.get(AnalysisRun, "analysis_trial_test").expires_at = STAMP
    dashboard.db.commit()
    assert client.post(BASE + "/analysis/analysis_trial_test/proposals/proposal_one/adopt").status_code == 409
    assert client.get("/api/intelligence/channels/2/dashboard").status_code == 404


def test_evidence_links_use_saved_snapshot_ids_and_expiry(client, dashboard):
    snapshot = {"videos": [{"id": "video000001", "reports": [{"id": "r:42", "values": {"views": 10}}],
                            "production": {"id": "production:exp_one"}}],
                "production_aggregates": {"groups": [{"id": "aggregate:test", "video_ids": ["video000002"]}]}}
    run = dashboard.db.get(AnalysisRun, "analysis_trial_test")
    run.input_snapshot = snapshot
    dashboard.db.commit()
    payload = client.get(BASE + "/analysis/analysis_trial_test/evidence-videos").json()
    assert payload["evidenceVideos"] == evidence_video_ids(snapshot)
    assert payload["evidenceVideos"]["r:42:views"] == ["video000001"]
    run.expires_at = STAMP
    dashboard.db.commit()
    assert client.get(BASE + "/analysis/analysis_trial_test/evidence-videos").status_code == 404


def test_derived_disabled_and_stale_metadata_are_not_used(client, dashboard):
    dashboard.config.youtube_derived_allowed = False
    dashboard.db.get(YouTubeVideo, "video000001").metadata_updated_at = STAMP - timedelta(days=31)
    dashboard.db.commit()
    data = dashboard_data(dashboard.db, dashboard.paths, dashboard.config, 1, "shorts", STAMP)
    assert len(data.videos) == 1 and data.excludedMetadataCount == 1
    assert data.current.reason == "DERIVED_NOT_ALLOWED"


def test_duration_bands_cover_extended_shorts_and_longform():
    assert [duration_band(value, "shorts") for value in (29, 30, 45, 60, 75, 75.1)] == [
        "30秒未満", "30〜45秒未満", "45〜60秒未満", "60〜75秒", "60〜75秒", "75秒超"]
    assert duration_band(1200, "long") == "20分以上"
    assert duration_band(None, "shorts") == "unknown"
