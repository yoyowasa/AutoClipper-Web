from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import inspect, select

from app.intelligence.analysis_input import build_analysis_input
from app.intelligence.analysis_validation import validate_review
from app.intelligence.hint_validation import hint_issue
from app.intelligence.models import ProductionAggregate, ProductionLink, VideoDailyStat, YouTubeVideo
from app.intelligence.performance_hints import load_performance_hints
from app.intelligence.performance_schema import PerformanceHint
from app.intelligence.policy import expire_youtube_data
from app.intelligence.production_aggregation import (
    aggregate_analysis_input, build_production_aggregates, first7_observations, save_production_aggregates,
)
from app.intelligence.production_dimensions import attributes
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_intelligence import environment as environment, VIDEO_ID
from test_channel_analysis import CLOCK, URL, execute, prepared as prepared, valid_review
from test_production_links import record


def seed_links(prepared, count=5):
    template = prepared.db.get(YouTubeVideo, VIDEO_ID)
    native = prepared.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "first7"))
    for index in range(count):
        id = VIDEO_ID if index == 0 else f"video{index + 1:06}"
        if index:
            prepared.db.add(YouTubeVideo(id=id, channel_id=1, title=f"動画{index}", published_at=template.published_at,
                duration_seconds=60, format="shorts", format_source="youtube_analytics", availability="available",
                metadata_updated_at=CLOCK, public_observed_at=CLOCK, public_statistics=template.public_statistics))
        values = {"views": 10 * (index + 1), "averageViewPercentage": 80 + index,
                  "averageViewDuration": 20 + index, "likes": None, "subscribersGained": 0}
        if index == 0:
            native.values = values
        else:
            prepared.db.add(VideoDailyStat(channel_id=1, video_id=id, sync_run_id=native.sync_run_id, kind="first7",
                dimension_key=f":{id}:shorts", period_start=native.period_start, period_end=native.period_end,
                dimensions={"creatorContentType": "shorts"}, values=values, missing_reasons={"likes": "UNAVAILABLE"},
                observed_at=CLOCK, expires_at=CLOCK + timedelta(days=365)))
        item = record(prepared.paths, id=f"exp_hint_{index}")
        item.characterPresetName = "テストキャラ"
        item.selection.openingScore = 12
        write_json_atomic(prepared.paths.production_record(item.recordId), item.model_dump(mode="json"))
        prepared.db.add(ProductionLink(record_family_id=item.recordId, record_id=item.recordId,
                                       youtube_video_id=id, mode="manual"))
    prepared.db.commit()


def all_group(payload):
    return next(group for group in payload["groups"] if group["dimension"] == "all" and group["format"] == "short")


def hint_for(group, **overrides):
    return {"character_preset_name": "テストキャラ", "format": "short", "target": "selection",
            "text": "過去の観測では題材が伝わる冒頭が候補です。効果は未検証のため比較してください。",
            "evidence_groups": [{"group_id": group["id"], "count": group["count"]}], "video_ids": group["video_ids"][:5],
            "confidence": "low", **overrides}


def test_zero_links_has_only_insufficient_groups_and_no_hints(client, prepared):
    payload = build_production_aggregates(prepared.db, prepared.paths, prepared.config, 1, CLOCK)
    assert payload["linked_videos"] == 0 and payload["groups"]
    assert all(not group["sufficient"] and group["count"] == 0 for group in payload["groups"])
    response = client.get("/api/intelligence/channels/1/production-aggregates")
    assert response.status_code == 200 and "独自集計" in response.json()["label"]
    assert response.headers["cache-control"] == "no-store"
    run = execute(prepared, client.post(URL, json={}).json()["id"])
    assert run.status == "success" and run.review["performance_hints"] == []
    assert prepared.db.get(ProductionAggregate, 1).payload["linked_videos"] == 0


@pytest.mark.parametrize("count,sufficient", [(4, False), (5, True)])
def test_native_medians_relative_values_missing_and_zero_baseline(prepared, count, sufficient):
    seed_links(prepared, count)
    payload = build_production_aggregates(prepared.db, prepared.paths, prepared.config, 1, CLOCK)
    group = all_group(payload)
    assert group["count"] == count and group["sufficient"] == sufficient
    views = group["metrics"]["views"]
    assert views["median"] == 10 * (count + 1) / 2 and views["relative_to_channel_median"] == 1
    assert group["metrics"]["likes"]["median"] is None and group["metrics"]["likes"]["count"] == 0
    assert group["metrics"]["subscribersGained"]["relative_to_channel_median"] is None
    assert group["metrics"]["subscribersGained"]["missing_reason"] == "BASELINE_ZERO"
    assert group["metrics"]["averageViewPercentage"]["median"] == 80 + (count - 1) / 2


def test_channel_baseline_includes_unlinked_videos_and_ignores_daily_averages(prepared):
    seed_links(prepared)
    native = prepared.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "first7"))
    prepared.db.add(YouTubeVideo(id="unlinked001", channel_id=1, format="shorts", availability="available"))
    prepared.db.flush()
    prepared.db.add(VideoDailyStat(channel_id=1, video_id="unlinked001", sync_run_id=native.sync_run_id, kind="first7",
        dimension_key="unlinked", period_start=native.period_start, period_end=native.period_end,
        dimensions={"creatorContentType": "shorts"}, values={"views": 1000}, observed_at=CLOCK,
        expires_at=CLOCK + timedelta(days=365)))
    prepared.db.commit()
    views = all_group(build_production_aggregates(prepared.db, prepared.paths, prepared.config, 1, CLOCK))["metrics"]["views"]
    assert views["baseline_count"] == 6 and views["baseline_median"] == 35
    assert views["median"] == 30 and views["relative_to_channel_median"] == pytest.approx(30 / 35)


def test_hints_validate_derived_ids_counts_scope_video_ids_and_limit(prepared):
    seed_links(prepared)
    ctx = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_hints", CLOCK)
    group = all_group(ctx.payload["production_aggregates"])
    output = valid_review(ctx)
    good = hint_for(group)
    invalid = []
    for field, value in [("format", "normal"), ("video_ids", ["invented001"] * 5)]:
        invalid.append({**good, field: value})
    invalid.append({**good, "evidence_groups": [{"group_id": group["id"], "count": 99}]})
    invalid.append({**good, "evidence_groups": [{"group_id": "aggregate:unknown", "count": 5}]})
    output["performance_hints"] = [good, *invalid]
    diagnostics = {}
    result = validate_review(output, ctx, diagnostics=diagnostics)
    assert len(result.performance_hints) == 1 and diagnostics["excludedHints"] == 4
    assert {"HINT_SCOPE_MISMATCH", "HINT_VIDEO_UNKNOWN", "HINT_COUNT_MISMATCH", "HINT_GROUP_UNKNOWN"} <= diagnostics["reasonCounts"].keys()
    groups = {group["id"]: {**group, "sufficient": False}}
    assert hint_issue(PerformanceHint.model_validate(good), groups, ctx.videos, Counter()) == "HINT_INSUFFICIENT_DATA"
    output["performance_hints"] = [good] * 6
    assert len(validate_review(output, ctx).performance_hints) == 5


def test_hints_are_saved_retrieved_off_expired_and_unlinked(client, prepared, monkeypatch):
    seed_links(prepared)
    from app.intelligence import performance_hints
    monkeypatch.setattr(performance_hints, "now", lambda: CLOCK)
    from test_channel_analysis import FixedGenerator

    class WithHint(FixedGenerator):
        def analyze(self, context):
            result = super().analyze(context)
            group = all_group(context.payload["production_aggregates"])
            result["performance_hints"] = [hint_for(group)]
            return result

    run = execute(prepared, client.post(URL, json={}).json()["id"], WithHint)
    settings = {"characterPresetName": "テストキャラ"}
    hints = load_performance_hints(prepared.db, settings, stamp=CLOCK)
    assert hints[0]["analysisId"] == run.id and hints[0]["target"] == "selection"
    assert not load_performance_hints(prepared.db, {**settings, "usePerformanceHints": False}, stamp=CLOCK)
    assert not load_performance_hints(prepared.db, settings, stamp=run.expires_at + timedelta(seconds=1))
    prepared.db.delete(prepared.db.scalar(select(ProductionLink)))
    prepared.db.commit()
    assert not load_performance_hints(prepared.db, settings, stamp=CLOCK)


def test_aggregate_table_expiry_and_old_review_compatibility(client, prepared):
    assert "production_aggregates" in inspect(prepared.db.get_bind()).get_table_names()
    payload = build_production_aggregates(prepared.db, prepared.paths, prepared.config, 1, CLOCK)
    save_production_aggregates(prepared.db, 1, payload, CLOCK)
    prepared.db.commit()
    cached = prepared.db.get(ProductionAggregate, 1)
    assert (cached.expires_at - CLOCK).days <= 1096
    expire_youtube_data(prepared.db, prepared.config, clock=cached.expires_at + timedelta(seconds=1))
    assert prepared.db.get(ProductionAggregate, 1) is None


def test_title_hook_api_records_latest_hint_and_off_removes_it(client, prepared, monkeypatch):
    from app.intelligence import performance_hints
    from app.jobs.queue import get_enqueue_title_hook_suggestions
    from app.main import app
    from app.models import Job, Video
    from app.candidates.merge_boundaries import Candidate
    from app.candidates.select_candidates import CandidateSelection
    from app.audio.transcribe_faster_whisper import TranscriptSegment
    from app.jobs.subtitle_review import build_subtitle_review, write_subtitle_review, subtitle_review_output_path
    from app.jobs.title_hook_suggestions import load_title_hook_suggestion_input, title_hook_suggestion_input_path
    from test_channel_analysis import FixedGenerator

    seed_links(prepared)
    monkeypatch.setattr(performance_hints, "now", lambda: CLOCK)

    class WithTitleHint(FixedGenerator):
        def analyze(self, context):
            output = super().analyze(context)
            output["performance_hints"] = [hint_for(all_group(context.payload["production_aggregates"]), target="title_hook")]
            return output

    run = execute(prepared, client.post(URL, json={}).json()["id"], WithTitleHint)
    assert run.status == "success"
    source = prepared.paths.uploads / "hints-source.mp4"
    source.write_bytes(b"mock-source")
    prepared.db.add(Video(id="vid_hints", original_filename="hints.mp4", stored_path=str(source), duration=120))
    prepared.db.flush()
    job = Job(id="job_hints", video_id="vid_hints", status="awaiting_subtitle_review",
              settings_json={"characterPresetName": "テストキャラ", "usePerformanceHints": True})
    prepared.db.add(job)
    prepared.db.commit()
    candidate = Candidate(id="short_hint", type="short", start=0, end=30, duration=30, title="題材", transcript_text="科学の題材")
    document = build_subtitle_review(job.id, CandidateSelection(normalClips=[], shorts=[candidate]),
                                      [TranscriptSegment(start=0, end=30, text="科学の題材")])
    directory = prepared.paths.job_outputs(job.id)
    write_subtitle_review(document, subtitle_review_output_path(directory))
    app.dependency_overrides[get_enqueue_title_hook_suggestions] = lambda: lambda *args: None
    url = f"/api/jobs/{job.id}/subtitle-review/clips/{candidate.id}/title-hook-suggestions"
    body = {"segments": [{"segmentId": segment.id, "text": segment.text} for segment in document.segments]}
    assert client.post(url, json=body).status_code == 200
    path = title_hook_suggestion_input_path(directory, candidate.id)
    request = load_title_hook_suggestion_input(path)
    assert request.performance_hints[0]["analysisId"] == run.id
    previous_hash = request.input_hash
    job.settings_json = {**job.settings_json, "usePerformanceHints": False}
    prepared.db.commit()
    assert client.post(url, json=body).status_code == 200
    assert not load_title_hook_suggestion_input(path).performance_hints
    assert load_title_hook_suggestion_input(path).input_hash != previous_hash


def test_derived_input_and_hint_lifetime_follow_source_expiry(prepared):
    seed_links(prepared)
    row = prepared.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "first7"))
    row.expires_at = CLOCK + timedelta(hours=1)
    prepared.db.commit()
    ctx = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_expiry", CLOCK)
    assert ctx.expires_at == CLOCK + timedelta(hours=1)


def test_unknown_format_with_conflicting_first7_partitions_is_not_guessed(prepared):
    seed_links(prepared)
    prepared.db.get(YouTubeVideo, VIDEO_ID).format = "unknown"
    row = prepared.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "first7", VideoDailyStat.video_id == VIDEO_ID))
    prepared.db.add(VideoDailyStat(channel_id=1, video_id=VIDEO_ID, sync_run_id=row.sync_run_id, kind="first7",
        dimension_key="conflicting", period_start=row.period_start, period_end=row.period_end,
        dimensions={"creatorContentType": "videoOnDemand"}, values={"views": 30},
        observed_at=CLOCK, expires_at=CLOCK + timedelta(days=100)))
    prepared.db.commit()
    assert VIDEO_ID not in first7_observations(prepared.db, 1, prepared.config, CLOCK)


def test_large_derived_groups_are_bounded_and_omissions_are_reported():
    import json

    groups = [{"id": f"aggregate:{index}", "sufficient": True, "count": 5, "video_ids": ["video000001"] * 5,
               "value": "長い属性" * 2000} for index in range(100)]
    payload = {"groups": groups, "source": "independent_aggregation", "label": "独自集計", "linked_videos": 5}
    compact = aggregate_analysis_input(payload)
    assert len(compact["groups"]) < 40
    assert compact["omitted_sufficient_groups"] == 100 - len(compact["groups"])
    assert len(json.dumps(compact, ensure_ascii=False, separators=(",", ":"))) < 81_000


def test_disabled_policy_and_absent_hints_clear_transient_settings(client, prepared):
    from app.intelligence.performance_hints import attach_performance_hints

    settings = {"characterPresetName": "テストキャラ", "_performanceHints": [{"text": "古い一時データ"}]}
    assert "_performanceHints" not in attach_performance_hints(prepared.db, settings)
    prepared.config.youtube_derived_allowed = False
    assert client.get("/api/intelligence/channels/1/production-aggregates").status_code == 409
    assert not load_performance_hints(prepared.db, settings, config=prepared.config)


@pytest.mark.parametrize("seconds,expected", [(29.9, "<30"), (30, "30-45"), (45, "45-60"), (60, "60-75"), (75, "60-75"), (76, ">75")])
def test_short_bands_use_body_not_hook_length(tmp_path, seconds, expected):
    from app.storage.paths import StoragePaths
    item = record(StoragePaths(tmp_path))
    item.bodyDurationSeconds = seconds
    item.completedDurationSeconds = seconds + 3
    assert attributes(item)["duration"] == expected
