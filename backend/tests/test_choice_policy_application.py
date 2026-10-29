import json
from app.intelligence.choice_policy_schema import ChoicePolicyValues
from app.intelligence.choice_policy_runtime import freeze_job_policy, inherit_rendered_policy_evidence, record_policy_choices
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion
from app.intelligence.models import Channel, ChannelConnection
from app.jobs.automatic_visual_decisions import decide_visuals
from app.candidates.select_candidates import CandidateSelection, parse_selection_settings, _rank_key
from app.clip_allocation import allocate_selection
from app.production_records import write_production_record
from app.production_choices import ProductionChoice
from app.storage.json_io import write_json_atomic
from test_automatic_visual_decisions import visual_example, resolver
from test_production_records import example as example
from test_clip_allocation import candidate


def settings_for(**weights):
    values = ChoicePolicyValues().model_dump()
    values["weights"].update(weights)
    return {"_choicePolicies": {"short": {"id": "policy_test", **values}}}


def test_framing_style_and_emphasis_priorities_preserve_caps_and_manual_values():
    doc, clip, _selection, _segments, settings, video = visual_example()
    settings.update(settings_for(**{"framing.subject_tracking_crop": 1.1, "effects.number": 1.1,
                                   "text_style.subtitle.bold": 1.1}))
    seen = []
    def crop(*args, **kw):
        seen.append(kw)
        return resolver(*args, **kw)
    decide_visuals(doc, clip, settings=settings, video=video, source="synthetic", crop_resolver=crop)
    assert seen[0]["preferred_strategy"] == "subject_tracking_crop"
    assert clip.subtitle_style.bold and clip.subtitle_style.font_size == 220
    effects = next(c for c in doc.choice_history if c.kind == "effects")
    assert effects.values["emphasisNumberWeight"] == 1.1
    assert all(s.style.font_size <= 220 for s in clip.subtitle_styles)
    clip.manual_decision_fields = ["framing", "subtitle_style", "subtitle_styles"]
    before = clip.subtitle_style.model_dump(), [s.model_dump() for s in clip.subtitle_styles]
    decide_visuals(doc, clip, settings=settings, video=video, source="synthetic", crop_resolver=crop)
    assert "preferred_strategy" not in seen[-1]
    assert before == (clip.subtitle_style.model_dump(), [s.model_dump() for s in clip.subtitle_styles])


def test_ranking_weights_change_order_without_changing_quality_scores_or_known_mode():
    strong = candidate("strong", "short", score=80, selection_reason="codex_direct", opening_score=0)
    opening = candidate("opening", "short", score=59, start=60, selection_reason="codex_direct", opening_score=15)
    selection = CandidateSelection(shorts=[strong, opening])
    settings = {"clipAllocationMode": "ai", "totalClipCount": 1, "audienceFamiliarity": "unknown"}
    assert allocate_selection(selection, settings).shorts[0].id == "strong"
    learned = {**settings, **settings_for(**{"ranking.opening": 1.1})}
    assert allocate_selection(selection, learned).shorts[0].id == "opening"
    assert allocate_selection(selection, {**learned, "audienceFamiliarity": "known"}).shorts[0].id == "strong"
    a = candidate("a", "short", score=40, opening_score=0)
    b = candidate("b", "short", score=39, opening_score=15)
    assert _rank_key(a) > _rank_key(b)
    parsed = parse_selection_settings(learned)
    assert _rank_key(b, parsed) > _rank_key(a, parsed)
    assert (a.final_score, b.final_score) == (40, 39)


def test_allocation_priority_preserves_minimum_counts_and_hard_failures():
    normal = candidate("normal", "normal", score=95)
    short = candidate("short", "short", score=90)
    pool = CandidateSelection(normal_clips=[normal], shorts=[short])
    settings = {"clipAllocationMode": "ai", "totalClipCount": 1, **settings_for(**{"allocation.short": 1.1})}
    assert allocate_selection(pool, settings).shorts[0].id == "short"
    assert allocate_selection(pool, {**settings, "minNormalClipCount": 1}).normal_clips[0].id == "normal"
    short.hard_gate_passed = False
    assert allocate_selection(pool, settings).normal_clips[0].id == "normal"


def test_database_job_freeze_reaches_permanent_record_without_rewriting_manual_history(example):
    db, job, export, paths = example
    db.add(Channel(id=1, external_id="UC" + "a" * 22, name="投稿先"))
    db.add(ChannelConnection(channel_id=1, status="connected"))
    db.commit()
    head = ChoicePolicyHead(id="scope", channel_id=1, character="キャラ", format="short", current_id="policy_test")
    db.add(head)
    db.flush()
    db.add(ChoicePolicyVersion(id="policy_test", policy_id=head.id, values=ChoicePolicyValues().model_dump()))
    db.commit()
    job.settings_json = {**job.settings_json, "automationMode": "auto", "workflowMode": "automatic",
                         "_choicePolicyEligible": True, "channelName": "投稿先", "audienceFamiliarity": "unknown"}
    freeze_job_policy(db, job)
    db.refresh(job)
    assert job.settings_json["_choicePolicies"]["short"]["id"] == "policy_test"
    metadata_path = paths.resolve_stored_file(export.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["choiceHistory"] = [ProductionChoice(id="auto", kind="framing", clipId=export.candidate_id,
        source="automatic", stage="applied", policyVersion="framing-implementation-v1",
        values={"shortLayout": "blur_background"}).model_dump(mode="json"),
        ProductionChoice(id="manual", kind="text_style", clipId=export.candidate_id, source="manual", stage="applied",
                         policyVersion="human").model_dump(mode="json")]
    metadata["choiceHistory"] += [c.model_dump(mode="json") for c in (
        ProductionChoice(id="range", kind="range", clipId=export.candidate_id, source="automatic", stage="applied",
            policyVersion="clip-plan-v3", values={"type": "short", "start": 100, "end": 175}),
        ProductionChoice(id="emphasis", kind="effects", clipId=export.candidate_id, source="automatic", stage="applied",
            policyVersion="confirmed-subtitle-visuals-v2",
            values={"subtitleStyles": [], "emphasisSignal": "topic", "emphasisTopicWeight": 1.1}),
        ProductionChoice(id="rendered_emphasis", kind="effects", clipId=export.candidate_id, source="default", stage="published",
            policyVersion="existing-render-decisions-v1", values={"additionalEffects": "none"}),
    )]
    write_json_atomic(metadata_path, metadata)
    record = json.loads(write_production_record(job, export, paths).read_text(encoding="utf-8"))
    auto = next(c for c in record["choiceHistory"] if c["id"] == "auto")
    manual = next(c for c in record["choiceHistory"] if c["id"] == "manual")
    assert auto["policyVersion"] == "policy_test" and auto["implementationVersion"] == "framing-implementation-v1"
    assert manual["policyVersion"] == "human" and manual["source"] == "manual"
    rendered = next(c for c in record["choiceHistory"] if c["id"] == "rendered_emphasis")
    assert rendered["source"] == "automatic" and rendered["values"]["emphasisSignal"] == "topic"
    assert rendered["values"]["emphasisTopicWeight"] == 1.1
    assert rendered["policyVersion"] == "policy_test"
    assert rendered["implementationVersion"] == "confirmed-subtitle-visuals-v2"
    range_choice = next(c for c in record["choiceHistory"] if c["id"] == "range")
    assert range_choice["values"]["openingScore"] == 12
    assert range_choice["values"]["audienceFamiliarity"] == "unknown"


def test_render_inheritance_requires_actual_match_and_preserves_explicit_provenance():
    from datetime import datetime
    t = datetime(2026, 10, 29)
    def choice(id, kind, source, stage, values, version):
        return ProductionChoice(id=id, kind=kind, source=source, stage=stage, clipId="clip", recordedAt=t,
                                policyVersion=version, values=values)
    frame = {"shortLayout": "center_crop", "framingOffsetX": .1, "framingOffsetY": 0, "framingZoom": 1}
    applied = choice("applied", "framing", "manual", "applied", frame, "human-v1")
    published = choice("published", "framing", "unrecorded", "published", dict(frame), "existing-render-decisions-v1")
    effect = choice("effects", "effects", "automatic", "applied",
                    {"subtitleStyles": [{"start": 0}], "emphasisSignal": "topic"}, "visuals-v2")
    rendered = choice("rendered", "effects", "default", "published",
                      {"subtitleStyles": []}, "existing-render-decisions-v1")
    history = [applied, published, effect, rendered]
    inherit_rendered_policy_evidence(history, {}, clip_id="clip", format="short")
    assert published.source == "unrecorded"
    inherit_rendered_policy_evidence(history, settings_for(), clip_id="clip", format="short")
    assert published.source == "manual" and published.policyVersion == "human-v1"
    assert "emphasisSignal" not in rendered.values and rendered.source == "default"
    published.source, published.policyVersion = "automatic", "existing-render-decisions-v1"
    published.values["framingOffsetX"] = .2
    inherit_rendered_policy_evidence(history, settings_for(), clip_id="clip", format="short")
    assert published.source == "automatic"
    published.policyVersion = "policy_historical"
    published.implementationVersion = "existing-render-decisions-v1"
    original = published.model_dump(mode="json")
    inherit_rendered_policy_evidence(history, settings_for(), clip_id="clip", format="short")
    record_policy_choices(history, settings_for(), clip_id="clip", format="short")
    assert published.model_dump(mode="json") == original
