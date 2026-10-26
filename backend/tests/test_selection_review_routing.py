"""Mandatory selection checks and subtitle-only risk hand-off (no live services)."""
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import CodexInitialSelectionResult
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, record_candidate_hard_gates
from app.clip_allocation import allocate_selection
from app.jobs.automation import AUTOMATION_POLICY_SETTING, SUBTITLE_ONLY_AUTO_POLICY
from app.jobs.clip_plan_runner import _codex_selection_with_diverse_refined_shorts
from app.jobs.quality_gate import QualityGateDecision, evaluate_selection_quality_gate, load_quality_gate_decision
from app.jobs.subtitle_review import build_subtitle_review, load_subtitle_review
from app.models import Job
from test_subtitle_only_auto import setup_auto
from test_guarded_quality_gate_integration import guarded_client as guarded_client

SETTINGS = {"automationMode": "auto", AUTOMATION_POLICY_SETTING: SUBTITLE_ONLY_AUTO_POLICY,
            "normalClipCount": 0, "shortCount": 1, "shortMinDuration": 0, "shortMaxDuration": 75,
            "enableBoundaryRefinement": False}


def candidate(**changes):
    return Candidate.model_validate({"id": "short", "type": "short", "start": 5, "end": 39, "duration": 34,
        "title": "確認する題材", "transcript_text": "歴史と固有名詞の説明です。", "final_score": 90,
        "selection_reason": "codex_direct", **changes})


def evaluate(clip, settings=None):
    return evaluate_selection_quality_gate(job_id="test", selection=CandidateSelection(shorts=[clip]),
        transcript_segments=[TranscriptSegment(start=clip.start, end=clip.end, text=clip.transcript_text)],
        settings=settings or SETTINGS, source_duration=120, mode=(settings or SETTINGS)["automationMode"])


@pytest.mark.parametrize("allocation", [False, True])
def test_codex_final_pool_checks_shorts_before_diversity_and_allocation(allocation):
    good = candidate()
    bad = candidate(id="silent", start=50, end=84, transcript_text="無音の候補です。", final_score=99)
    result = CodexInitialSelectionResult(candidates=[bad, good],
        selection=CandidateSelection(shorts=[bad], requestedShortCount=1), summary={})
    settings = {**SETTINGS, **({"clipAllocationMode": "ai", "totalClipCount": 1} if allocation else {})}
    selection, pool, _ = _codex_selection_with_diverse_refined_shorts(result, settings=settings,
        transcript_segments=[], silence_segments=[SilenceSegment(start=50, end=84, duration=34)], scene_segments=[], timeline_duration=120)
    selection = allocate_selection(selection, settings)
    assert [c.id for c in selection.shorts] == [good.id]
    assert selection.shorts[0].hard_gate_passed is True
    assert selection.shorts[0].hard_gate_evidence["passed"] is True
    rejected = next(c for c in pool if c.id == bad.id)
    assert rejected.hard_gate_passed is False
    assert "max_silence_ratio" in rejected.hard_gate_evidence["reasons"]
    assert any("max_silence_ratio" in c.reasons for c in selection.rejected_candidates)


def test_hard_gate_exception_records_failure_not_a_pass(monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("do not persist input values")
    monkeypatch.setattr("app.candidates.select_candidates.evaluate_hard_gate", broken)
    checked, rejected = record_candidate_hard_gates([candidate()], settings=SETTINGS, silence_segments=[])
    assert checked[0].hard_gate_passed is False
    assert rejected[0].reasons == ["hard_gate_evaluation_failed"]
    assert rejected[0].details["errorType"] == "ValueError"
    assert "do not persist" not in str(rejected)


@pytest.mark.parametrize("flag", ["historical_claims_require_review", "proper_noun_caption_review",
                                   "factual_claims_require_review", "subtitle_accuracy_review", "transcript_accuracy_review"])
def test_subtitle_flags_keep_unknown_and_go_to_subtitles(flag):
    clip = candidate(hard_gate_passed=True, risk_flags=[flag])
    decision = evaluate(clip)
    assert decision.outcome == "unknown" and decision.route == "subtitle_review"
    assert next(c for c in decision.checks if c.code == "selection.risk_flags").outcome == "unknown"
    assert QualityGateDecision.model_validate_json(decision.model_dump_json()).route == "subtitle_review"
    review = build_subtitle_review("test", CandidateSelection(shorts=[clip]),
        [TranscriptSegment(start=5, end=39, text=clip.transcript_text)], render_settings=SETTINGS)
    warning = review.clips[0].selection_warnings[0]
    assert warning.code == flag and warning.message and warning.scope == "clip"
    assert (warning.start, warning.end) == (5, 39)
    assert not review.clips[0].confirmed


@pytest.mark.parametrize("flag", ["abrupt_start", "range_out_of_bounds", "duplicate_moment", "new_unknown_flag"])
def test_other_and_mixed_flags_still_stop_at_selection(flag):
    decision = evaluate(candidate(hard_gate_passed=True, risk_flags=["proper_noun_caption_review", flag]))
    assert decision.outcome == "unknown" and decision.route == "clip_review"


@pytest.mark.parametrize("change", [{"duration": 80, "end": 85}, {"start": 100, "end": 134}, {"title": ""}, {"hard_gate_passed": False}])
def test_selection_failure_wins_over_subtitle_warning(change):
    decision = evaluate(candidate(hard_gate_passed=True, risk_flags=["proper_noun_caption_review"]).model_copy(update=change))
    assert decision.outcome == "fail" and decision.route == "clip_review"


def test_unrecorded_check_is_processing_failure_for_new_auto_only():
    decision = evaluate(candidate())
    assert decision.outcome == "unknown" and decision.route == "failed"
    assert decision.checks[4].reason_code == "candidate_hard_gate_not_recorded"
    old = {**SETTINGS, AUTOMATION_POLICY_SETTING: "auto-human-subtitle-review-v1"}
    assert evaluate(candidate(), old).route == "clip_review"
    assert evaluate(candidate(hard_gate_passed=True, risk_flags=["proper_noun_caption_review"]), old).route == "clip_review"
    assert evaluate(candidate(hard_gate_passed=True, risk_flags=["proper_noun_caption_review"]),
                    {**SETTINGS, "automationMode": "guarded"}).route == "clip_review"


def test_route_cannot_ignore_unknown_selection_risk():
    decision = evaluate(candidate(hard_gate_passed=True, risk_flags=["abrupt_start"]))
    with pytest.raises(ValidationError, match="route must match"):
        QualityGateDecision.model_validate({**decision.model_dump(), "route": "subtitle_review"})


@pytest.mark.parametrize("risk,expected", [("proper_noun_caption_review", "awaiting_subtitle_review"),
                                         ("abrupt_start", "awaiting_clip_review")])
def test_pipeline_real_gate_routes_before_review_and_delivers_warning(guarded_client, monkeypatch, tmp_path, risk, expected):
    import app.jobs.runner as runner
    import app.jobs.pipeline_common as pipeline
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "evaluate_selection_quality_gate", evaluate_selection_quality_gate)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.settings_json = {**job.settings_json, "normalClipTimeRanges": [], "shortClipTimeRanges": [],
            "initialSelectionProvider": "codex", "normalClipCount": 0, "shortCount": 1,
            "shortMinDuration": 0, "enableBoundaryRefinement": False}
        db.commit()
    c = candidate(risk_flags=[risk])
    def select(**kwargs):
        return CodexInitialSelectionResult(candidates=[c], selection=CandidateSelection(shorts=[c], requestedShortCount=1),
                                          summary={"status": "completed", "fallbackUsed": False,
                                                   "requestedNormalCount": 0, "requestedShortCount": 1})
    statuses = runner.run_autoclipper_job(data.job_id, session_factory=data.factory, paths=data.storage,
                                         dependencies=replace(data.deps, codex_initial_selector=select))
    assert statuses[-1] == expected
    decision = load_quality_gate_decision(data.storage.job_outputs(data.job_id) / "quality_gate/selection.json")
    assert decision.outcome == "unknown"
    if expected == "awaiting_subtitle_review":
        assert "awaiting_clip_review" not in statuses
        review = load_subtitle_review(data.review_path)
        assert review.clips[0].selection_warnings[0].code == risk
        assert not review.clips[0].confirmed
        response = data.client.get(f"/api/jobs/{data.job_id}/subtitle-review")
        assert response.status_code == 200
        assert response.json()["clips"][0]["selectionWarnings"][0]["code"] == risk
    assert not data.calls and not data.renders


@pytest.mark.parametrize("failure", ["evaluation", "write"])
def test_gate_failure_stops_new_auto_without_manual_selection(monkeypatch, tmp_path, failure):
    import app.jobs.pipeline_common as pipeline
    if failure == "evaluation":
        def broken(**kwargs):
            raise ValueError("private error detail")
        monkeypatch.setattr(pipeline, "evaluate_selection_quality_gate", broken)
    else:
        monkeypatch.setattr(pipeline, "_try_write_quality_gate_decision", lambda *args: None)
    clip = candidate(hard_gate_passed=True)
    decision, _ = pipeline._evaluate_selection_quality_gate_for_mode(
        job_id="test", job_dir=tmp_path, selection=CandidateSelection(shorts=[clip]),
        transcript_segments=[TranscriptSegment(start=5, end=39, text=clip.transcript_text)],
        settings=SETTINGS, source_duration=120, mode="auto")
    assert decision.route == "failed" and decision.outcome == "unknown"
    assert decision.checks[0].reason_code == (
        "selection_gate_evaluation_failed" if failure == "evaluation" else "selection_gate_record_unavailable")
    assert "private error detail" not in decision.model_dump_json()
