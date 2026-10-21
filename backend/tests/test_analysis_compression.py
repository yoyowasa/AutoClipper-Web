"""Realistic growth, missingness, stable IDs and explicit oldest-first budgeting."""

from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import insert, select

import app.intelligence.analysis_input as inputs
from app.intelligence.analysis_budget import ANALYSIS_PROMPT_BUDGET_CHARS, fit_analysis_budget
from app.intelligence.analysis_cohort import MAX_ANALYSIS_VIDEOS, select_video_cohort
from app.intelligence.analysis_prompt import MAX_ANALYSIS_PROMPT_CHARS, analysis_prompt, render_analysis_prompt
from app.intelligence.analysis_reports import native_report, reports_for_video, summarize_video_days
from app.intelligence.models import SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.analysis_validation import validate_review
from test_api_routes import client as client
from test_intelligence import environment as environment, VIDEO_ID
from test_channel_analysis import CLOCK, URL, FixedGenerator, execute, prepared as prepared, valid_review


def day_row(index, values, **extra):
    return SimpleNamespace(id=index, video_id=VIDEO_ID, kind="video_day", source="youtube_analytics",
        period_start=date(2026, 10, index), period_end=date(2026, 10, index), observed_at=CLOCK,
        expires_at=CLOCK + timedelta(days=100), definition_version="youtube-native-2026-10-v1",
        report_timezone="America/Los_Angeles", dimensions={"day": f"2026-10-{index:02}"},
        values=values, missing_reasons={}, **extra)


def test_daily_summary_sums_only_additive_metrics_without_filling_missing_days():
    rows = [day_row(1, {"views": 10, "likes": -1, "averageViewPercentage": 120}),
            day_row(3, {"views": 30, "likes": None, "averageViewPercentage": 30})]
    rows[1].missing_reasons = {"likes": "UNAVAILABLE"}
    total, peak = summarize_video_days(VIDEO_ID, rows, date(2026, 10, 1), date(2026, 10, 3))
    assert total["values"] == {"views": 40}
    assert total["missing"]["likes"] == {"UNAVAILABLE": 1}
    assert "averageViewPercentage" not in total["values"]
    assert total["coverage"] == {"returned_days": 2, "unreturned_days": 1, "complete": False,
                                  "method": "sum_returned_days_additive_metrics_only"}
    assert peak["id"] == "r:3" and peak["values"]["averageViewPercentage"] == 30


def test_daily_summary_never_combines_definitions_and_peak_tie_uses_newer_day():
    rows = [day_row(1, {"views": 10}), day_row(2, {"views": 10})]
    rows[1].definition_version = "other-definition"
    total, peak = summarize_video_days(VIDEO_ID, rows, date(2026, 10, 1), date(2026, 10, 2))
    assert not total["values"] and total["missing"]["views"] == "INCOMPATIBLE_DEFINITIONS"
    assert peak["id"] == "r:2" and peak["definition_version"] == "other-definition"


def test_duplicate_native_reports_removed_but_different_partitions_preserved():
    period = day_row(1, {"views": 20, "averageViewDuration": 12})
    period.kind = "video_period"
    partition = deepcopy(period)
    partition.id, partition.kind = 2, "video_format"
    partition.dimensions = {"creatorContentType": "shorts"}
    reports, count = reports_for_video(VIDEO_ID, [period, partition], period.period_start, period.period_end)
    assert count == 1 and [r["id"] for r in reports if r["values"]] == ["r:1"]
    partition.values["averageViewDuration"] = 13
    reports, count = reports_for_video(VIDEO_ID, [period, partition], period.period_start, period.period_end)
    assert count == 0 and reports[1]["values"]["averageViewDuration"] == 13
    assert native_report(period)["values"]["averageViewDuration"] == 12


def test_cohort_retains_recent_and_old_performance_extremes_missing_views_not_zero():
    videos = {f"video{i:06}": {"format": "shorts", "published_at": "2026-01-01"} for i in range(130)}
    for i in range(25, 130):
        videos[f"video{i:06}"]["published_at"] = "2026-10-01"
    views = {id: index for index, id in enumerate(videos) if index != 0}
    selected, scope = select_video_cohort(videos, views, date(2026, 10, 18))
    assert len(selected) == MAX_ANALYSIS_VIDEOS
    assert "video000001" in selected and "video000129" in selected  # Old low and high cases.
    assert "video000000" not in selected  # Missing public views are not a zero-view ranking.
    assert scope["excluded_videos"] == 30 and scope["performance_extremes_per_format"] == 5


def grow_channel(prepared, count):
    template = prepared.db.get(YouTubeVideo, VIDEO_ID)
    native = prepared.db.scalars(select(VideoDailyStat).where(VideoDailyStat.video_id == VIDEO_ID)).all()
    for index in range(1, count):
        id = f"v{index:010}"
        prepared.db.add(YouTubeVideo(id=id, channel_id=1, title="題材の分析対象 " * 10 + str(index),
            published_at=CLOCK - timedelta(days=index % 90), duration_seconds=60,
            format="shorts", format_source="youtube_analytics", metadata_updated_at=CLOCK, availability="available",
            public_statistics=deepcopy(template.public_statistics), public_observed_at=CLOCK))
        for row in native:
            prepared.db.add(VideoDailyStat(channel_id=1, video_id=id, sync_run_id=row.sync_run_id, kind=row.kind,
                dimension_key=id + row.dimension_key, period_start=row.period_start, period_end=row.period_end,
                values=deepcopy(row.values), missing_reasons=deepcopy(row.missing_reasons), dimensions=deepcopy(row.dimensions),
                observed_at=CLOCK, expires_at=row.expires_at, definition_version=row.definition_version))
    prepared.db.commit()
    run = prepared.db.scalar(select(SyncRun))
    end = run.last_report_date
    run.requested_start = end - timedelta(days=59)
    # Full 60-day channel trend and 246 x 60 video rows, rather than a sparse toy payload.
    template_row = native[0]
    all_ids = [VIDEO_ID, *(f"v{index:010}" for index in range(1, count))]
    present = {(row.video_id, row.kind, row.period_start) for row in prepared.db.scalars(select(VideoDailyStat))}
    additions = []
    for offset in range((end - run.requested_start).days + 1):
        day = end - timedelta(days=offset)
        for id in [None, *all_ids]:
            kind = "video_day" if id else "daily"
            if (id, kind, day) in present:
                continue
            additions.append(dict(channel_id=1, video_id=id, sync_run_id=template_row.sync_run_id, kind=kind,
                dimension_key=f"{day}:{id or ''}:", period_start=day, period_end=day,
                values=deepcopy(template_row.values), missing_reasons=deepcopy(template_row.missing_reasons),
                dimensions={"day": str(day)}, observed_at=CLOCK, expires_at=template_row.expires_at,
                definition_version=template_row.definition_version))
    prepared.db.execute(insert(VideoDailyStat), additions)
    prepared.db.commit()


def test_three_times_82_videos_fit_complete_prompt_and_keep_valid_evidence(prepared):
    grow_channel(prepared, 246)
    ctx = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_growth", CLOCK)
    assert ctx.payload["input_scope"]["eligible_videos"] == 246
    assert len(ctx.videos) <= MAX_ANALYSIS_VIDEOS
    assert len(analysis_prompt(ctx.payload)) <= ANALYSIS_PROMPT_BUDGET_CHARS < MAX_ANALYSIS_PROMPT_CHARS
    assert "evidence_groups" not in ctx.payload and "evidence" not in ctx.payload
    assert len([r for r in ctx.payload["channel_reports"] if r["kind"] == "daily"]) == 60
    assert validate_review(valid_review(ctx), ctx).findings


def test_short_requested_daily_window_still_keeps_previous_native_28_days(prepared):
    run = prepared.db.scalar(select(SyncRun))
    run.requested_start = run.last_report_date
    prepared.db.commit()
    ctx = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_period", CLOCK)
    assert {"current", "previous"} <= {row["kind"] for row in ctx.payload["channel_reports"]}


def test_budget_removes_oldest_first_and_all_its_evidence_but_keeps_daily_trends(prepared, monkeypatch):
    grow_channel(prepared, 5)
    before = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_budget", CLOCK)
    budget = len(render_analysis_prompt(before.payload)) - 100
    monkeypatch.setattr(inputs, "fit_analysis_budget", lambda payload: fit_analysis_budget(payload, budget=budget))
    after = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_budget", CLOCK)
    oldest = min(before.videos, key=lambda id: (before.videos[id]["published_at"], id))
    assert after.payload["budget_omissions"]["removed_video_ids"][0] == oldest
    assert len(render_analysis_prompt(after.payload)) <= budget
    assert oldest not in after.videos
    assert all(item["video_id"] != oldest for item in after.evidence.values())
    assert after.payload["channel_reports"] == before.payload["channel_reports"]
    assert not any(oldest in ids for ids in after.payload["format_videos"].values())
    again = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_budget", CLOCK + timedelta(minutes=1))
    assert after.fingerprint == again.fingerprint


def test_saved_result_discloses_sampling_even_if_codex_does_not(client, prepared):
    id = client.post(URL, json={}).json()["id"]
    saved = execute(prepared, id)
    assert saved.status == "success"
    assert "本を分析" in saved.review["limitations"][0]
    assert saved.validation.report["inputCompression"]["scope"] == saved.input_snapshot["input_scope"]
    assert len(saved.review["limitations"]) <= 10


def test_compression_note_preserves_all_existing_limitations(client, prepared):
    class TenLimitations(FixedGenerator):
        def analyze(self, context):
            output = super().analyze(context)
            output["limitations"] = [f"未確認事項{i}" for i in range(10)]
            return output

    id = client.post(URL, json={}).json()["id"]
    saved = execute(prepared, id, TenLimitations)
    assert saved.status == "success" and len(saved.review["limitations"]) == 10
    assert all(f"未確認事項{i}" in "\n".join(saved.review["limitations"]) for i in range(10))


def test_oversized_production_payload_is_trimmed_without_losing_channel_reports(prepared):
    ctx = inputs.build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_large", CLOCK)
    original = deepcopy(ctx.payload["channel_reports"])
    ctx.payload["videos"][0]["production"] = {"id": "production:large", "value": {"reason": "長い記録" * 100000}}
    fit_analysis_budget(ctx.payload)
    assert not ctx.payload["videos"] and ctx.payload["budget_omissions"]["removed_videos"] == 1
    assert ctx.payload["channel_reports"] == original
    assert len(analysis_prompt(ctx.payload)) < ANALYSIS_PROMPT_BUDGET_CHARS
