from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.intelligence.choice_policy_schema import ChoicePolicyValues, changed_values
from app.intelligence.choice_policy_engine import update_choice_policies
from app.intelligence.choice_policy_runtime import freeze_job_policy, record_policy_choices, choose_title_suggestion
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion, ChoicePolicyDecision
from app.intelligence.production_aggregation import build_production_aggregates, save_production_aggregates
from app.intelligence.models import SyncRun, YouTubeVideo
from app.intelligence.policy import expire_youtube_data
from app.intelligence.evaluation_rules import GOALS
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_intelligence import environment as environment
from test_choice_evaluation import seed, add_video, CLOCK
from test_channel_analysis import prepared as prepared


def setup_groups(e, *, count=5, source="automatic", option="blur_background", target_views=1400000):
    seed(e)
    for index in range(1, count * 2 + 1):
        v, r = add_video(e, index, views=1000000 if index <= count else target_views,
                         source="automatic" if index <= count else source)
        v.duration_seconds = 60
        if index > count:
            r.choiceHistory[0].values = {"shortLayout": option}
            write_json_atomic(e.paths.production_record(r.recordId), r.model_dump(mode="json"))
    e.db.commit()


def evaluate(e, id="analysis_policy", stamp=CLOCK):
    payload = build_production_aggregates(e.db, e.paths, e.config, 1, stamp)
    save_production_aggregates(e.db, 1, payload, stamp)
    e.db.commit()
    return update_choice_policies(e.db, SimpleNamespace(id=id, channel_id=1, review={"goals": GOALS}), stamp)


@pytest.mark.parametrize("bad", [{"prompt": "x"}, {"quality.min": 0}, {"framing.new_mode": 1}, {"weights": {"new": 1}}])
def test_policy_allowlist_rejects_code_prompts_gates_new_options(bad):
    with pytest.raises(ValueError):
        ChoicePolicyValues.model_validate(bad)
    base = ChoicePolicyValues().model_dump()
    with pytest.raises(ValueError):
        changed_values(base, "ranking.opening", 1.1001)
    with pytest.raises(ValueError):
        changed_values(base, "framing.new_mode", 1.01)
    assert changed_values(base, "ranking.opening", 1.1)["weights"]["ranking.opening"] == 1.1


def test_approved_observation_rule_versions_one_item_and_deduplicates(environment):
    e = environment
    setup_groups(e)
    result = evaluate(e)[0]
    head = e.db.scalar(select(ChoicePolicyHead))
    old, new = (e.db.get(ChoicePolicyVersion, id) for id in (result.from_id, result.to_id))
    assert result.action == "update" and new.previous_id == old.id == result.from_id
    assert head.current_id == new.id and new.values["weights"]["framing.blur_background"] == 1.1
    assert sum(v != old.values["weights"][k] for k, v in new.values["weights"].items()) == 1
    assert result.evidence["before"]["count"] == result.evidence["after"]["count"] == 5
    assert result.evidence["after"]["median"] == 1400000 and result.evidence["after"]["rate"] == 1
    assert result.evidence["causal_effect"] == "unconfirmed"
    assert result.evidence["before"]["observed_at"] and result.evidence["after"]["evidence_ids"]
    assert evaluate(e) == []
    waiting = evaluate(e, "analysis_next", CLOCK + timedelta(minutes=1))[0]
    assert waiting.action == "hold" and waiting.reason == "VERSION_30_DAY_PENDING"
    assert len(list(e.db.scalars(select(ChoicePolicyVersion)))) == 2


@pytest.mark.parametrize("kwargs,reason", [({"count": 4}, "INSUFFICIENT_OR_UNCONFIRMED"),
    ({"source": "manual"}, "MIXED_PROVENANCE"), ({"source": "unrecorded"}, "MIXED_PROVENANCE"),
    ({"source": "fallback"}, "INSUFFICIENT_OR_UNCONFIRMED"),
    ({"target_views": 1199999}, "INSUFFICIENT_OR_UNCONFIRMED"),
    ({"option": "unvalidated_mode"}, "INSUFFICIENT_OR_UNCONFIRMED")])
def test_insufficient_unconfirmed_or_mixed_data_is_held(environment, kwargs, reason):
    setup_groups(environment, **kwargs)
    result = evaluate(environment)[0]
    assert result.action == "hold" and result.reason == reason
    assert len(list(environment.db.scalars(select(ChoicePolicyVersion)))) == 1


def test_new_jobs_freeze_version_and_keep_manual_and_legacy_paths(environment):
    e = environment
    setup_groups(e)
    updated = evaluate(e)[0]
    for automatic, eligible, expected in [(True, True, True), (False, True, False), (True, False, False)]:
        job = SimpleNamespace(settings_json={"_choicePolicyEligible": eligible, "characterPresetName": "キャラ",
            "automationMode": "auto" if automatic else "manual", "workflowMode": "automatic"})
        freeze_job_policy(e.db, job)
        assert bool(job.settings_json.get("_choicePolicies")) == expected
        if expected:
            assert job.settings_json["_choicePolicies"]["short"]["id"] == updated.to_id
            e.db.get(ChoicePolicyHead, updated.policy_id).current_id = updated.from_id
            e.db.commit()
            freeze_job_policy(e.db, job)
            assert job.settings_json["_choicePolicies"]["short"]["id"] == updated.to_id
            _, record = add_video(e, 99)
            record_policy_choices(record.choiceHistory, job.settings_json, clip_id="clip", format="short")
            assert record.choiceHistory[0].policyVersion == updated.to_id
            record.choiceHistory[0].source = "manual"
            record.choiceHistory[0].policyVersion = "manual-v1"
            record_policy_choices(record.choiceHistory, job.settings_json, clip_id="clip", format="short")
            assert record.choiceHistory[0].policyVersion == "manual-v1"


def test_30_day_regression_rolls_back_and_7_day_only_warns(environment, monkeypatch):
    import test_choice_evaluation as fixture
    from app.intelligence.models import VideoDailyStat
    e = environment
    setup_groups(e)
    updated = evaluate(e)[0]
    future = CLOCK + timedelta(days=60)
    monkeypatch.setattr(fixture, "CLOCK", future)
    e.db.get(SyncRun, "sync_eval").last_report_date = future.date() - timedelta(days=1)
    for v in e.db.scalars(select(YouTubeVideo)):
        v.metadata_updated_at = future
    for index in range(11, 16):
        v, record = add_video(e, index, views=None, policy=updated.to_id)
        record.choiceHistory[0].implementationVersion = "choice-v1"
        write_json_atomic(e.paths.production_record(record.recordId), record.model_dump(mode="json"))
        v.duration_seconds = 60
        for row in e.db.scalars(select(VideoDailyStat).where(VideoDailyStat.video_id == v.id, VideoDailyStat.kind == "first7")):
            row.values = {"views": 100}
    e.db.commit()
    early = evaluate(e, "analysis_early", future)[0]
    assert early.action == "warning" and early.reason == "EARLY_7_DAY_DECLINE"
    assert e.db.get(ChoicePolicyHead, updated.policy_id).current_id == updated.to_id
    for row in e.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind == "first30", VideoDailyStat.video_id >= "video000011")):
        row.values, row.missing_reasons = {"views": 800000}, {}
    e.db.commit()
    rolled = evaluate(e, "analysis_regression", future + timedelta(minutes=1))[0]
    assert rolled.action == "rollback" and rolled.reason == "REGRESSION_30_DAY"
    assert rolled.to_id == updated.from_id and rolled.from_id == updated.to_id
    assert e.db.get(ChoicePolicyHead, updated.policy_id).current_id == updated.from_id
    expire_youtube_data(e.db, e.config, clock=rolled.evidence_expires_at)
    assert e.db.get(ChoicePolicyDecision, rolled.id).evidence is None
    assert e.db.get(ChoicePolicyVersion, updated.to_id).values


def test_manual_restore_api_checks_origin_version_and_channel(client, environment):
    e = environment
    setup_groups(e)
    updated = evaluate(e)[0]
    url = f"/api/intelligence/channels/1/choice-policies/{updated.policy_id}/rollback"
    data = client.get("/api/intelligence/channels/1/choice-policies").json()[0]
    assert data["currentId"] == updated.to_id and len(data["versions"]) == 2
    assert client.post(url, json={"expectedVersion": updated.to_id}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post(url, json={"expectedVersion": "old"}).status_code == 409
    assert client.post(url, json={"expectedVersion": updated.to_id}).status_code == 204
    assert client.post(url, json={"expectedVersion": updated.to_id}).status_code == 409
    # A later analysis must not immediately undo the explicit restore.
    result = evaluate(e, "analysis_after_restore", CLOCK + timedelta(minutes=1))[0]
    assert result.action == "hold" and result.to_id == updated.from_id


def test_validated_title_options_reorder_without_changing_generated_recommendation():
    values = ChoicePolicyValues().model_dump()
    values["weights"]["title_hook.factual"] = 1.1
    settings = {"_choicePolicies": {"short": {"id": "policy_test", **values}}}
    artifact = SimpleNamespace(recommended_suggestion_id="s2", suggestions=[
        SimpleNamespace(id="s1", intent="factual"), SimpleNamespace(id="s2", intent="engagement")])
    assert choose_title_suggestion(artifact, {}, "short") == "s2"
    assert choose_title_suggestion(artifact, settings, "short") == "s1"
    assert artifact.recommended_suggestion_id == "s2"


def test_zero_links_hold_and_versions_are_immutable(environment):
    e = environment
    seed(e)
    results = evaluate(e)
    assert len(results) == 2 and all(r.action == "hold" for r in results)
    assert all(r.reason == "INSUFFICIENT_OR_UNCONFIRMED" for r in results)
    version = e.db.get(ChoicePolicyVersion, results[0].to_id)
    version.values = changed_values(version.values, "ranking.opening", 1.1)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        e.db.commit()
    e.db.rollback()


def test_concurrent_analysis_completion_cannot_make_duplicate_versions(environment):
    from concurrent.futures import ThreadPoolExecutor
    e = environment
    setup_groups(e)
    save_production_aggregates(e.db, 1, build_production_aggregates(e.db, e.paths, e.config, 1, CLOCK), CLOCK)
    e.db.commit()
    def update(_):
        with e.factory() as db:
            return len(update_choice_policies(db, SimpleNamespace(id="same_analysis", channel_id=1, review={"goals": GOALS}), CLOCK))
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(update, range(2))) == 1
    e.db.expire_all()
    assert len(list(e.db.scalars(select(ChoicePolicyVersion)))) == 2


@pytest.mark.parametrize("kind,role,old,new,key", [
    ("range", "", {"openingBand": "0-5", "audienceFamiliarity": "unknown"},
        {"openingBand": "10-15", "audienceFamiliarity": "unknown"}, "ranking.opening"),
    ("range", "", {"allocationShare": .2}, {"allocationShare": .6}, "allocation.short"),
    ("title_hook", "", {"intent": "engagement"}, {"intent": "factual"}, "title_hook.factual"),
    ("text_style", "subtitleStyle", {"bold": False}, {"bold": True}, "text_style.subtitle.bold"),
    ("effects", "", {"emphasisSignal": "reaction"}, {"emphasisSignal": "topic"}, "effects.topic"),
])
def test_all_allowed_domains_are_driven_by_observed_existing_choices(kind, role, old, new, key):
    from app.intelligence.choice_policy_evidence import option_change
    base = {"kind": kind, "role": role, "format": "short", "option_values": old}
    assert option_change(base, {**base, "option_values": new})[0] == key


@pytest.mark.parametrize("failure", [False, True])
def test_successful_analysis_runs_policy_judgment_without_human_adoption(client, prepared, monkeypatch, caplog, failure):
    import app.intelligence.choice_policy_engine as engine
    from test_channel_analysis import execute, URL
    if failure:
        def fail(*args):
            raise RuntimeError("must not log generated provider text")
        monkeypatch.setattr(engine, "update_choice_policies", fail)
    response = client.post(URL, json={"syncBefore": "never"})
    assert response.status_code == 202
    result = execute(prepared, response.json()["id"])
    assert result.status == "success" and result.review
    events = list(prepared.db.scalars(select(ChoicePolicyDecision)))
    assert events and all(e.action == "hold" for e in events)
    assert all(e.reason == ("EVALUATION_FAILED" if failure else "INSUFFICIENT_OR_UNCONFIRMED") for e in events)
    assert "must not log" not in caplog.text


def test_channel_binding_is_unambiguous_and_existing_opt_out_is_respected(environment):
    from app.intelligence.models import Channel, ChannelConnection
    from app.intelligence.choice_policy_engine import identity
    e = environment
    setup_groups(e)
    updated = evaluate(e)[0]
    e.db.add(Channel(id=2, external_id="UC" + "b" * 22, name="別チャンネル"))
    e.db.flush()
    e.db.add(ChannelConnection(channel_id=2, status="connected"))
    key = identity(2, "キャラ", "short")
    e.db.add(ChoicePolicyHead(id=key, channel_id=2, character="キャラ", format="short", current_id="policy_other"))
    e.db.flush()
    e.db.add(ChoicePolicyVersion(id="policy_other", policy_id=key, values=ChoicePolicyValues().model_dump()))
    e.db.commit()
    base = {"_choicePolicyEligible": True, "automationMode": "auto", "characterPresetName": "キャラ"}
    ambiguous = SimpleNamespace(settings_json=base)
    freeze_job_policy(e.db, ambiguous)
    assert ambiguous.settings_json["_choicePolicies"] == {}
    assert ambiguous.settings_json["_choicePolicyReasons"]["short"] == "CHANNEL_AMBIGUOUS"
    named = SimpleNamespace(settings_json={**base, "channelName": "  別チャンネル  "})
    freeze_job_policy(e.db, named)
    assert named.settings_json["_choicePolicies"]["short"]["id"] == "policy_other"
    assert named.settings_json["_choicePolicies"]["short"]["id"] != updated.to_id
    missing = SimpleNamespace(settings_json={**base, "channelName": "未接続"})
    freeze_job_policy(e.db, missing)
    assert missing.settings_json["_choicePolicies"] == {}
    assert missing.settings_json["_choicePolicyReasons"]["short"] == "NO_MATCHING_POLICY"
    disabled = SimpleNamespace(settings_json={**base, "channelName": "別チャンネル", "usePerformanceHints": False})
    freeze_job_policy(e.db, disabled)
    assert disabled.settings_json["_choicePolicies"] == {}
    assert disabled.settings_json["_choicePolicyReasons"]["all"] == "LEARNING_DISABLED"


def test_exact_twenty_percent_gain_is_eligible_but_wrong_goals_are_not(environment):
    e = environment
    setup_groups(e, target_views=1200000)
    result = evaluate(e)[0]
    assert result.action == "update"
    before = len(list(e.db.scalars(select(ChoicePolicyDecision))))
    assert update_choice_policies(e.db, SimpleNamespace(
        id="wrong_goals", channel_id=1, review={"goals": {"short": 1000000}}), CLOCK) == []
    assert len(list(e.db.scalars(select(ChoicePolicyDecision)))) == before


def test_priority_evidence_cannot_cross_choice_kinds_or_unknown_fields():
    from app.intelligence.choice_policy_evidence import option_change
    for kind, field in [("effects", "openingRankWeight"), ("range", "emphasisTopicWeight"), ("range", "prompt")]:
        before = {"kind": kind, "role": "", "format": "short", "option_values": {field: 1}}
        assert option_change(before, {**before, "option_values": {field: 1.1}}) is None
    for mode in ("known", None):
        before = {"kind": "range", "role": "", "format": "short",
                  "option_values": {"openingBand": "0-5", "audienceFamiliarity": mode}}
        assert option_change(before, {**before, "option_values": {
            "openingBand": "10-15", "audienceFamiliarity": mode}}) is None
