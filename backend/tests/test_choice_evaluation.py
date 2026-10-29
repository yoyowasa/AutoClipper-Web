"""Fixed-age goals, recorded choice provenance and missing observations are independent."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.intelligence.analysis_schema import AnalysisGoals, Review, analysis_response_schema
from app.intelligence.choice_evaluation import build_choice_evaluations, evaluate_video_goal, final_choices
from app.intelligence.evaluation_rules import GOALS, initial_window
from app.intelligence.models import Channel, ChannelConnection, ProductionAggregate, ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.policy import expire_youtube_data, statistical_expiry
from app.intelligence.production_aggregation import build_production_aggregates, save_production_aggregates
from app.production_choices import ProductionChoice
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_intelligence import CHANNEL_ID, environment as environment
from test_production_links import record

CLOCK = datetime(2026, 10, 29, 12)


def seed(env):
    env.db.add(Channel(id=1, external_id=CHANNEL_ID, metadata_updated_at=CLOCK))
    env.db.add(ChannelConnection(channel_id=1, status="connected"))
    env.db.add(SyncRun(id="sync_eval", channel_id=1, status="success", queued_at=CLOCK,
                       last_report_date=CLOCK.date() - timedelta(days=1)))
    env.db.commit()


def add_video(env, index=1, *, format="shorts", age=40, views=1_000_000, source="automatic", policy="choice-v1"):
    id = f"video{index:06}"
    published = CLOCK - timedelta(days=age)
    video = YouTubeVideo(id=id, channel_id=1, title=f"題材{index}", published_at=published,
                         format=format, availability="available", metadata_updated_at=CLOCK)
    env.db.add(video)
    for days, value in ((7, 500), (30, views)):
        start, end = initial_window(published, days)
        env.db.add(VideoDailyStat(channel_id=1, video_id=id, sync_run_id="sync_eval", kind=f"first{days}",
            dimension_key=f"{id}:{days}", period_start=start, period_end=end,
            dimensions={"creatorContentType": "shorts" if format == "shorts" else "videoOnDemand"},
            values={"views": value}, missing_reasons={"views": "NO_ROWS"} if value is None else {},
            observed_at=CLOCK, expires_at=statistical_expiry(CLOCK, env.config)))
    item = record(env.paths, id=f"exp_{index}", created=(published - timedelta(hours=1)).replace(tzinfo=UTC))
    item.type = "short" if format == "shorts" else "normal"
    item.characterPresetName = "キャラ"
    item.selection.candidateId = "clip"
    item.choiceHistory = [ProductionChoice(id=f"choice_{index}", clipId="clip", kind="framing", stage="applied",
        source=source, policyVersion=policy, recordedAt=(published - timedelta(minutes=1)).replace(tzinfo=UTC),
        values={"shortLayout": "face_tracking_crop"}, selectedIds=["face_tracking_crop"])]
    write_json_atomic(env.paths.production_record(item.recordId), item.model_dump(mode="json"))
    env.db.add(ProductionLink(record_family_id=item.recordId, record_id=item.recordId, youtube_video_id=id, mode="auto"))
    env.db.commit()
    return video, item


@pytest.mark.parametrize("format,views,expected", [("long", 100000, "reached"), ("long", 99999, "below_target"),
    ("shorts", 1000000, "reached"), ("shorts", 999999, "below_target"), ("shorts", 0, "below_target"),
    ("shorts", None, "insufficient_data")])
def test_format_goals_apply_only_to_returned_first30(environment, format, views, expected):
    from sqlalchemy import select
    e = environment
    seed(e)
    video, _ = add_video(e, format=format, views=views)
    rows = list(e.db.scalars(select(VideoDailyStat)))
    goal = evaluate_video_goal(video, rows, CLOCK.date() - timedelta(days=1), CLOCK)
    assert goal.status == expected
    assert goal.target_views == (100000 if format == "long" else 1000000)
    assert goal.first30.metrics["views"].value == views
    assert goal.first7.metrics["views"].value == 500
    assert goal.evidence_ids if views is not None else not goal.evidence_ids


def test_early_and_unreturned_reports_are_unjudged_never_zero(environment):
    from sqlalchemy import select
    e = environment
    seed(e)
    video, _ = add_video(e, age=10, views=1_000_000)
    rows = list(e.db.scalars(select(VideoDailyStat)))
    pending = evaluate_video_goal(video, rows, CLOCK.date(), CLOCK)
    assert pending.status == "pending" and pending.first30.metrics["views"].value is None
    assert pending.first7.metrics["views"].value == 500
    video.published_at -= timedelta(days=30)
    missing = evaluate_video_goal(video, [], CLOCK.date(), CLOCK)
    assert missing.status == "insufficient_data" and missing.first30.metrics["views"].value is None
    assert evaluate_video_goal(video, rows, None, CLOCK).status == "insufficient_data"


def test_pacific_calendar_window_and_goal_schema():
    start, end = initial_window(datetime(2026, 10, 31, 23), 30)
    assert str(start) == "2026-11-01" and str(end) == "2026-11-30"
    assert AnalysisGoals().model_dump() == GOALS
    schema = analysis_response_schema()
    assert "goals" in schema["required"] and "goal_views" not in schema["properties"]


def test_choice_groups_preserve_source_version_observations_and_insufficiency(environment):
    e = environment
    seed(e)
    for index in range(1, 6):
        add_video(e, index, views=1_000_000 if index < 4 else 900_000)
    add_video(e, 6, source="manual")
    add_video(e, 7, source="fallback")
    add_video(e, 8, policy="choice-v2")
    add_video(e, 9, source="unrecorded", policy=None)
    add_video(e, 10, age=10)
    payload = build_choice_evaluations(e.db, e.paths, e.config, 1, CLOCK)
    groups = payload["groups"]
    group = next(g for g in groups if g["source"] == "automatic" and g["policy_version"] == "choice-v1")
    assert group["count"] == 6 and group["judged_count"] == 5
    assert group["sufficient"] and group["effect"] == "unconfirmed"
    assert group["attainment_rate"] == 3 / 5 and group["median_views"] == 1_000_000
    assert {r["video_id"] for r in group["observations"]} == set(group["video_ids"])
    for row in group["observations"]:
        assert row["record_id"] and row["choice_id"] and row["value_hash"]
        if row["evaluation"]["status"] != "pending":
            assert row["evaluation"]["evidence_ids"] and row["evaluation"]["first30"]["observedAt"]
    assert all(not g["sufficient"] and g["effect"] == "unconfirmed" for g in groups if g is not group)
    aggregate = build_production_aggregates(e.db, e.paths, e.config, 1, CLOCK)
    save_production_aggregates(e.db, 1, aggregate, CLOCK)
    e.db.commit()
    assert e.db.get(ProductionAggregate, 1).payload["choice_evaluations"] == payload
    expire_youtube_data(e.db, e.config, clock=statistical_expiry(CLOCK, e.config))
    assert e.db.get(ProductionAggregate, 1) is None


def test_final_choices_do_not_attribute_later_manual_edit_to_old_video(environment):
    e = environment
    seed(e)
    video, item = add_video(e)
    original = item.choiceHistory[0]
    after = original.model_copy(update={"id": "after", "source": "manual", "values": {"shortLayout": "blur_background"},
                                       "recordedAt": CLOCK.replace(tzinfo=UTC)})
    item.choiceHistory.append(after)
    assert final_choices(item)[0][1].source == "manual"
    assert final_choices(item, as_of=video.published_at)[0][1].source == "automatic"
    write_json_atomic(e.paths.production_record(item.recordId), item.model_dump(mode="json"))
    assert build_choice_evaluations(e.db, e.paths, e.config, 1, CLOCK)["groups"][0]["source"] == "automatic"


def test_actual_framing_options_and_exact_observation_windows_are_separate(environment):
    from sqlalchemy import select
    e = environment
    seed(e)
    video, item = add_video(e)
    _, other = add_video(e, 2)
    other.choiceHistory[0].values = {"shortLayout": "blur_background"}
    write_json_atomic(e.paths.production_record(other.recordId), other.model_dump(mode="json"))
    # A different report window with the same value/time must not be cited.
    real = e.db.scalar(select(VideoDailyStat).where(VideoDailyStat.video_id == video.id, VideoDailyStat.kind == "first30"))
    fake = VideoDailyStat(channel_id=1, video_id=video.id, sync_run_id="sync_eval", kind="first30", dimension_key="other",
        period_start=real.period_start - timedelta(days=1), period_end=real.period_end - timedelta(days=1),
        dimensions=real.dimensions, values=real.values, observed_at=CLOCK, expires_at=real.expires_at)
    e.db.add(fake)
    e.db.commit()
    groups = build_choice_evaluations(e.db, e.paths, e.config, 1, CLOCK)["groups"]
    assert len(groups) == 2 and all(group["count"] == 1 for group in groups)
    frame = next(group for group in groups if group["option_values"]["shortLayout"] == "face_tracking_crop")
    observation = frame["observations"][0]
    assert observation["values"] == item.choiceHistory[0].values
    assert observation["evaluation"]["evidence_ids"] == [f"r:{real.id}:views"]


def test_unchanged_style_does_not_replace_automatic_provenance(environment):
    e = environment
    seed(e)
    _, item = add_video(e)
    style = item.choiceHistory[0].model_copy(update={"kind": "text_style", "values": {
        "titleStyle": {"fontSize": 60}, "subtitleStyle": {"fontSize": 80}}, "id": "style"})
    resend = style.model_copy(update={"source": "manual", "id": "resend",
        "recordedAt": style.recordedAt + timedelta(seconds=1), "values": {
            "titleStyle": {"fontSize": 60}, "subtitleStyle": {"fontSize": 70}}})
    item.choiceHistory = [style, resend]
    result = dict(final_choices(item))
    assert result["text_style", "titleStyle"].source == "automatic"
    assert result["text_style", "subtitleStyle"].source == "manual"


def test_dashboard_and_aggregate_api_expose_same_goal_and_provenance(client, environment, monkeypatch):
    import app.api.channel_analysis as api
    import app.api.intelligence_dashboard as dashboard_api
    e = environment
    seed(e)
    add_video(e)
    monkeypatch.setattr(api, "now", lambda: CLOCK)
    monkeypatch.setattr(dashboard_api, "now", lambda: CLOCK)
    dashboard = client.get("/api/intelligence/channels/1/dashboard")
    aggregate = client.get("/api/intelligence/channels/1/production-aggregates")
    assert dashboard.status_code == aggregate.status_code == 200
    goal = dashboard.json()["videos"][0]["goal"]
    observation = aggregate.json()["choice_evaluations"]["groups"][0]["observations"][0]
    assert goal["status"] == "reached" and goal["target_views"] == 1000000
    assert goal == observation["evaluation"] and observation["source"] == "automatic"


def test_legacy_review_still_loads_but_new_review_needs_30_day_goals():
    from app.intelligence.analysis_validation import ReviewValidationError, validate_review
    from test_channel_analysis import valid_review
    context = SimpleNamespace(payload={"review_id": "analysis_test", "channel": {"id": 1}, "batch": {"run_id": "sync_eval"}},
        evidence={"metric": {"video_id": "video000001", "source": "youtube_analytics"}},
        videos={"video000001": {"format": "shorts"}})
    raw = valid_review(context)
    raw.pop("goals")
    raw["goal_views"] = 1000000
    assert Review.model_validate(raw).goals is None
    with pytest.raises(ReviewValidationError) as error:
        validate_review(raw, context)
    assert error.value.report["reasonCounts"]["GOALS_MISMATCH"] == 1


def test_choice_evaluation_is_bounded_analysis_evidence_and_hint_input(environment):
    import json
    from app.intelligence.analysis_input import build_analysis_input
    from app.intelligence.analysis_prompt import analysis_prompt
    from app.intelligence.analysis_validation import validate_review
    from test_channel_analysis import valid_review
    e = environment
    seed(e)
    for index in range(1, 6):
        add_video(e, index)
    context = build_analysis_input(e.db, e.paths, e.config, 1, "analysis_test", CLOCK)
    assert context.payload["goals"] == GOALS
    assert len(analysis_prompt(context.payload)) < 280000
    assert all(video["production"]["value"]["choices"] for video in context.payload["videos"])
    group = context.payload["choice_evaluations"]["groups"][0]
    assert group["id"] in context.evidence and group["count"] == 5
    raw = valid_review(context)
    raw["performance_hints"] = [{"character_preset_name": "キャラ", "format": "short", "target": "selection",
        "text": "この方針の画角は実績を確認する参考です。", "evidence_groups": [{"group_id": group["id"], "count": 5}],
        "video_ids": group["video_ids"], "confidence": "low"}]
    assert len(validate_review(raw, context).performance_hints) == 1
    group["sufficient"] = False
    report = {}
    assert validate_review(raw, context, diagnostics=report).performance_hints == []
    assert report["reasonCounts"]["HINT_INSUFFICIENT_DATA"] == 1
    # Video growth cannot repeat unbounded per-choice observations in the prompt.
    from app.intelligence.choice_evaluation import choice_evaluation_input
    payload = context.aggregates["choice_evaluations"]
    payload["groups"] *= 100
    compact = choice_evaluation_input(payload)
    assert len(compact["groups"]) <= 30 and compact["omitted_groups"] > 0
    assert len(json.dumps(compact, ensure_ascii=False)) < 45000
