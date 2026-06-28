import json
from pathlib import Path

from app.audio.silence_detect import SilenceSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import (
    CandidateSelectionSettings,
    select_and_write_candidates,
    select_candidates,
)
from app.scoring.quality_gate import QualityGateSettings, evaluate_quality_gate


def make_candidate(
    candidate_id: str,
    candidate_type: str,
    start: float,
    end: float,
    text: str,
    final_score: float | None = None,
    rule_score: float | None = None,
    should_use: bool | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text=text,
        final_score=final_score,
        rule_score=rule_score,
        should_use=should_use,
    )


def test_quality_gate_rejects_silence_low_speech_incomplete_and_low_score() -> None:
    candidate = make_candidate(
        "bad",
        "short",
        0.0,
        40.0,
        "because this is incomplete and",
        final_score=30.0,
    )
    result = evaluate_quality_gate(
        candidate,
        settings=QualityGateSettings(
            max_silence_ratio=0.4,
            min_speech_density=0.5,
            min_final_score=60.0,
        ),
        silence_segments=[SilenceSegment(start=0.0, end=30.0, duration=30.0)],
    )

    assert result.passed is False
    assert result.reasons == [
        "max_silence_ratio",
        "too_little_speech",
        "low_final_score",
        "incomplete_sentence",
    ]


def test_selection_refills_rejected_candidates_and_separates_types() -> None:
    candidates = [
        make_candidate("normal_best", "normal", 0.0, 120.0, "Complete normal clip.", final_score=95.0),
        make_candidate("normal_overlap", "normal", 10.0, 130.0, "Overlapping normal clip.", final_score=94.0),
        make_candidate("normal_low", "normal", 140.0, 260.0, "Low score normal clip.", final_score=20.0),
        make_candidate("normal_refill", "normal", 280.0, 400.0, "Refill normal clip.", final_score=82.0),
        make_candidate("short_best", "short", 0.0, 45.0, "Complete short one.", final_score=90.0),
        make_candidate("short_overlap", "short", 5.0, 50.0, "Overlapping short.", final_score=89.0),
        make_candidate("short_refill_1", "short", 60.0, 105.0, "Complete short two.", final_score=80.0),
        make_candidate("short_refill_2", "short", 120.0, 165.0, "Complete short three.", final_score=75.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 3,
            "maxOverlapRatio": 0.8,
            "minFinalScore": 60.0,
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal_best", "normal_refill"]
    assert [candidate.id for candidate in selection.shorts] == [
        "short_best",
        "short_refill_1",
        "short_refill_2",
    ]
    assert {rejection.candidate_id for rejection in selection.rejected_candidates} == {
        "normal_overlap",
        "short_overlap",
    }


def test_selection_does_not_fail_when_individual_candidates_fail() -> None:
    candidates = [
        make_candidate("model_rejected", "short", 0.0, 40.0, "Rejected by model.", final_score=95.0, should_use=False),
        make_candidate("incomplete", "short", 50.0, 90.0, "and incomplete", final_score=90.0),
    ]

    selection = select_candidates(
        candidates,
        settings=CandidateSelectionSettings(normal_clip_count=0, short_count=2),
    )

    assert selection.shorts == []
    assert [rejection.candidate_id for rejection in selection.rejected_candidates] == [
        "model_rejected",
        "incomplete",
    ]


def test_select_and_write_candidates_saves_selected_clips_json(tmp_path: Path) -> None:
    candidates = [
        make_candidate("normal", "normal", 0.0, 120.0, "Selected normal.", rule_score=80.0),
        make_candidate("short", "short", 130.0, 175.0, "Selected short.", rule_score=78.0),
    ]

    output_path = select_and_write_candidates(
        candidates,
        tmp_path,
        settings={"normalClipCount": 1, "shortCount": 1},
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path == tmp_path / "selected_clips.json"
    assert payload["normalClips"][0]["id"] == "normal"
    assert payload["shorts"][0]["id"] == "short"
    assert payload["rejectedCandidates"] == []
