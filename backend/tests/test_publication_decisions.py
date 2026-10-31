from datetime import UTC, datetime, timedelta
import json
import pytest
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, CandidateRejection
from app.publication.models import PublicationPolicy, POLICY_SETTING
from app.publication.evaluate import evaluate_candidate, policy_for
from app.publication.pipeline import apply_publication_decisions
from app.publication.storage import read_report, summary
from app.storage.paths import StoragePaths


def candidate(id="one", *, score=80, text=None, **updates):
    return Candidate(
        id=id,
        type="normal",
        title="具体的な題材",
        start=0,
        end=90,
        duration=90,
        transcript_text=("具体的な事実を説明します。" * 20 if text is None else text),
        final_score=score,
        selection_reason="codex_direct",
        hard_gate_passed=True,
        hard_gate_evidence={"passed": True, "reasons": []},
        boundary_refined=False,
    ).model_copy(update=updates)


def settings(**kwargs):
    return {POLICY_SETTING: PublicationPolicy().model_dump(by_alias=True), "normalClipCount": 2, "shortCount": 0, **kwargs}


@pytest.mark.parametrize("score,decision", [(64.99, "skip"), (65, "publish"), (80, "publish"), (None, "unknown")])
def test_score_threshold_and_missing_are_distinct(score, decision):
    value = evaluate_candidate(candidate(score=score), policy=PublicationPolicy(), settings=settings(), source_duration=300)
    assert value.decision == decision
    assert value.policy_version == "weak-material-v1"
    assert value.evidence.score == score
    if score is None:
        assert value.reasons == ["SCORE_MISSING"]


@pytest.mark.parametrize("count,decision", [(44, "skip"), (45, "publish")])
def test_textual_density_boundary(count, decision):
    value = evaluate_candidate(candidate(text="字" * count), policy=PublicationPolicy(), settings=settings(), source_duration=300)
    assert value.decision == decision
    assert value.evidence.characters_per_second == count / 90


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"transcript_text": ""}, "TRANSCRIPT_MISSING"),
        ({"hard_gate_passed": None}, "QUALITY_EVIDENCE_MISSING"),
        ({"hard_gate_passed": False}, "EXISTING_GATE_REJECTED"),
        ({"end": 301, "duration": 301}, "RANGE_INVALID"),
        ({"selection_reason": None}, "SELECTION_REASON_MISSING"),
    ],
)
def test_missing_or_invalid_evidence_is_neither_publish_nor_skip(change, reason):
    value = evaluate_candidate(candidate(**change), policy=PublicationPolicy(), settings=settings(), source_duration=300)
    assert value.decision == "unknown" and value.reasons == [reason]


def apply(tmp_path, items, *, raw=None, selection=None, scored=None):
    selection = selection or CandidateSelection(normalClips=items, requestedNormalCount=len(items))
    return apply_publication_decisions(
        selection, scored or items, settings=raw or settings(), paths=StoragePaths(tmp_path), job_id="job_test", source_duration=300
    )


def test_strong_candidates_preserve_count_order_and_values(tmp_path):
    items = [candidate("one"), candidate("two", start=100, end=190)]
    result = apply(tmp_path, items)
    assert result.normal_clips == items and result.deferred_candidates == []
    assert all(d.decision == "publish" for d in result.publication_decisions)
    assert read_report(StoragePaths(tmp_path), "job_test").selected_count == 2


def test_skip_is_not_backfilled_even_when_minimum_count_is_unmet(tmp_path):
    items = [candidate("weak", score=62), candidate("strong", start=100, end=190)]
    reserve = candidate("unused-strong", start=200, end=290)
    raw = settings(clipAllocationMode="ai", totalClipCount=2, minNormalClipCount=2)
    selected = CandidateSelection(normalClips=items, requestedTotal=2, selectedTotal=2, selectedByType={"normal": 2, "short": 0})
    result = apply(tmp_path, items, raw=raw, selection=selected, scored=[*items, reserve])
    assert [c.id for c in result.normal_clips] == ["strong"]
    assert [c.id for c in result.deferred_candidates] == ["weak"]
    assert result.selected_total == 1 and result.minimum_shortfall["normal"] == 1
    assert result.shortfall_reasons["weak_material_skip"] == 1
    report = read_report(StoragePaths(tmp_path), "job_test")
    assert report.outcome == "partial"
    assert "unused-strong" not in [d.candidate_id for d in report.decisions]
    assert report.choice_history[0].kind == "publication_decision"
    assert "transcript_text" not in json.dumps(report.model_dump(mode="json"))


def test_all_weak_and_all_unknown_have_different_outcomes(tmp_path):
    apply(tmp_path, [candidate(score=62)])
    assert read_report(StoragePaths(tmp_path), "job_test").outcome == "no_publication"
    apply(tmp_path, [candidate(score=None)])
    assert read_report(StoragePaths(tmp_path), "job_test").outcome == "needs_review"
    assert summary(StoragePaths(tmp_path), "job_test")["decisions"][0]["decision"] == "unknown"


@pytest.mark.parametrize("raw", [{}, settings(workflowMode="manual")])
def test_legacy_and_manual_workflows_are_not_opted_in(tmp_path, raw):
    original = CandidateSelection(normalClips=[candidate(score=1)])
    result = apply(tmp_path, original.normal_clips, raw=raw or {"workflowMode": "automatic"}, selection=original)
    assert result == original
    assert not StoragePaths(tmp_path).publication_decisions("job_test").exists()


def test_manual_time_ranges_and_kept_clips_are_exempt(tmp_path):
    fixed = candidate(score=1, text="", selection_reason="manual_time_range", hard_gate_passed=None)
    result = apply(tmp_path, [fixed])
    assert result.normal_clips == [fixed]
    assert result.publication_decisions[0].source == "manual"
    result = apply(tmp_path, [candidate(score=1)], raw=settings(keptClipIds=["one"]))
    assert result.publication_decisions[0].decision == "publish" and result.publication_decisions[0].source == "manual"


def test_expired_hints_are_not_evidence_and_hints_never_override_gates():
    stamp = datetime.now(UTC)

    def hint(expiry):
        return {
            "analysisId": "analysis_test",
            "generatedAt": (stamp - timedelta(days=2)).isoformat(),
            "expiresAt": expiry.isoformat(),
            "target": "selection",
            "text": "参考だけ",
            "format": "normal",
        }

    raw = settings(_performanceHints=[hint(stamp - timedelta(days=1)), hint(stamp + timedelta(days=1))])
    result = evaluate_candidate(candidate(score=62), policy=PublicationPolicy(), settings=raw, source_duration=300)
    assert result.decision == "skip" and len(result.evidence.hint_references) == 1
    assert result.evidence.hint_references[0].analysis_id == "analysis_test"


def test_existing_score_only_rejection_cannot_be_revived_by_a_lower_new_threshold(tmp_path):
    # User's existing 90-point quality threshold remains binding even though this policy uses 65.
    c = candidate(score=75)
    rejected = CandidateSelection(rejectedCandidates=[CandidateRejection(candidateId=c.id, type=c.type, reasons=["low_final_score"])])
    result = apply(tmp_path, [], raw=settings(minFinalScore=90), selection=rejected, scored=[c])
    assert result.normal_clips == [] and result.publication_decisions[0].decision == "skip"
    assert "MODEL_REJECTED" in result.publication_decisions[0].reasons


def test_reading_old_job_does_not_create_directories(tmp_path):
    assert summary(StoragePaths(tmp_path), "job_old") is None
    assert not (tmp_path / "production_records").exists()
    assert policy_for({}) is None


def test_low_codex_confidence_retention_is_opt_in_and_validates_range():
    from app.candidates.codex_initial_selection import convert_codex_initial_selection_response
    from test_codex_initial_selection import _request, _response, _settings

    old = _request()
    proposal = _response(old).selected_clips[0].model_copy(update={"confidence": 0.59})
    response = _response(old).model_copy(update={"selected_clips": [proposal]})
    assert convert_codex_initial_selection_response(old, response).weak_candidates == []
    new = _request(settings=_settings(**{POLICY_SETTING: PublicationPolicy().model_dump(by_alias=True)}))
    response = _response(new).model_copy(update={"selected_clips": [proposal]})
    kept = convert_codex_initial_selection_response(new, response)
    assert len(kept.weak_candidates) == 1 and kept.candidates == []
    assert kept.weak_candidates[0].below_quality_threshold is True
    invalid = proposal.model_copy(update={"end": 201})
    assert convert_codex_initial_selection_response(new, response.model_copy(update={"selected_clips": [invalid]})).weak_candidates == []


def test_only_model_rejection_is_weak_but_a_physical_gate_failure_is_unknown():
    c = candidate(score=59, should_use=False, hard_gate_passed=False, hard_gate_evidence={"passed": False, "reasons": ["model_rejected"]})
    decision = evaluate_candidate(c, policy=PublicationPolicy(), settings=settings(), source_duration=300)
    assert decision.decision == "skip" and "MODEL_REJECTED" in decision.reasons
    c.hard_gate_evidence["reasons"].append("max_silence_ratio")
    assert evaluate_candidate(c, policy=PublicationPolicy(), settings=settings(), source_duration=300).decision == "unknown"


def test_already_filtered_weak_candidate_is_recorded_without_refilling_requested_minimum(tmp_path):
    strong, weak = candidate("strong"), candidate("weak", score=59)
    selected = CandidateSelection(
        normalClips=[strong],
        requestedNormalCount=2,
        rejectedCandidates=[CandidateRejection(candidateId=weak.id, type="normal", reasons=["low_final_score"])],
    )
    result = apply(tmp_path, [strong], selection=selected, scored=[strong, weak])
    assert [c.id for c in result.normal_clips] == ["strong"]
    assert [c.id for c in result.deferred_candidates] == ["weak"]
    assert result.publication_withheld_counts == {"normal": 1}
    assert read_report(StoragePaths(tmp_path), "job_test").outcome == "partial"


def test_score_rejection_does_not_hide_an_additional_range_or_user_rejection(tmp_path):
    c = candidate("excluded", score=59)
    selection = CandidateSelection(
        rejectedCandidates=[
            CandidateRejection(candidateId=c.id, type=c.type, reasons=["low_final_score"]),
            CandidateRejection(candidateId=c.id, type=c.type, reasons=["rejected_by_user_no_content"]),
        ]
    )
    result = apply(tmp_path, [], selection=selection, scored=[c])
    assert not result.publication_decisions and not result.deferred_candidates
    assert not StoragePaths(tmp_path).publication_decisions("job_test").exists()
