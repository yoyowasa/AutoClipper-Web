import json
from pathlib import Path

from app.audio.silence_detect import SilenceSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import (
    CandidateSelectionSettings,
    select_and_write_candidates,
    select_candidates,
)
from app.scoring.quality_gate import QualityGateSettings, evaluate_hard_gate, evaluate_quality_gate


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


def test_hard_gate_does_not_reject_low_final_score() -> None:
    candidate = make_candidate(
        "low_score",
        "normal",
        0.0,
        60.0,
        "Complete but low scoring normal candidate.",
        final_score=35.0,
    )
    result = evaluate_hard_gate(candidate, settings=QualityGateSettings(min_final_score=60.0))

    assert result.passed is True
    assert "low_final_score" not in result.reasons


def test_fill_requested_backfills_below_min_final_score_with_metadata() -> None:
    candidates = [
        make_candidate("normal_low_best", "normal", 0.0, 60.0, "Complete low score one.", final_score=45.0),
        make_candidate("normal_low_next", "normal", 70.0, 130.0, "Complete low score two.", final_score=35.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 1,
            "shortCount": 0,
            "minFinalScore": 60.0,
            "selectionPolicy": "fill_requested",
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal_low_best"]
    selected = selection.normal_clips[0]
    assert selected.hard_gate_passed is True
    assert selected.below_quality_threshold is True
    assert selected.quality_warning == "below_min_final_score"
    assert selected.selection_reason == "backfill_below_quality_threshold"
    assert selection.hard_gate_passed_count == 2
    assert selection.hard_gate_rejected_count == 0
    assert selection.selected_above_threshold_count == 0
    assert selection.selected_below_threshold_backfill_count == 1
    assert selection.rejected_candidates == []


def test_missing_selection_policy_defaults_to_strict_quality() -> None:
    candidate = make_candidate(
        "normal_low_default_strict",
        "normal",
        0.0,
        60.0,
        "Complete but low scoring normal candidate.",
        final_score=45.0,
    )

    selection = select_candidates(
        [candidate],
        settings={
            "normalClipCount": 1,
            "shortCount": 0,
            "minFinalScore": 60.0,
        },
    )

    assert selection.selection_policy == "strict_quality"
    assert selection.normal_clips == []
    assert selection.unfilled_requested_counts == {"normal": 1, "short": 0}
    assert selection.rejected_candidates[0].reasons == ["low_final_score"]


def test_strict_quality_preserves_low_score_rejection() -> None:
    candidates = [
        make_candidate("normal_low", "normal", 0.0, 60.0, "Complete low score.", final_score=45.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 1,
            "shortCount": 0,
            "minFinalScore": 60.0,
            "selectionPolicy": "strict_quality",
        },
    )

    assert selection.normal_clips == []
    assert selection.rejected_candidates[0].candidate_id == "normal_low"
    assert selection.rejected_candidates[0].reasons == ["low_final_score"]
    assert selection.selection_policy == "strict_quality"


def test_normal_selection_requires_distinct_topic_keys() -> None:
    same_topic_best = make_candidate(
        "normal_art_best",
        "normal",
        0.0,
        180.0,
        "美学とは何かを説明します。",
        final_score=95.0,
    ).model_copy(update={"topic_key": "topic_art"})
    same_topic_duplicate = make_candidate(
        "normal_art_duplicate",
        "normal",
        240.0,
        420.0,
        "美学の具体例を続けて説明します。",
        final_score=94.0,
    ).model_copy(update={"topic_key": "topic_art"})
    other_topic = make_candidate(
        "normal_history",
        "normal",
        600.0,
        780.0,
        "文化財を残す理由と歴史を説明します。",
        final_score=90.0,
    ).model_copy(update={"topic_key": "topic_history"})

    selection = select_candidates(
        [same_topic_best, same_topic_duplicate, other_topic],
        settings={
            "normalClipCount": 2,
            "shortCount": 0,
            "selectionPolicy": "strict_quality",
            "minFinalScore": 60.0,
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == [
        "normal_art_best",
        "normal_history",
    ]
    duplicate = next(
        rejection
        for rejection in selection.rejected_candidates
        if rejection.candidate_id == "normal_art_duplicate"
    )
    assert duplicate.reasons == ["duplicate_topic"]
    assert duplicate.details["topicKey"] == "topic_art"


def test_normal_selection_rejects_near_duplicate_ranges_even_when_topic_keys_differ() -> None:
    candidates = [
        make_candidate(
            "normal_art_wide",
            "normal",
            2788.16,
            2915.16,
            "キュビズムと美術の説明です。",
            final_score=95.0,
        ).model_copy(update={"topic_key": "topic_2788160"}),
        make_candidate(
            "normal_art_nested",
            "normal",
            2839.64,
            2934.58,
            "別の質問を起点にした同じ美術説明です。",
            final_score=94.0,
        ).model_copy(update={"topic_key": "topic_2839640"}),
        make_candidate(
            "normal_history",
            "normal",
            3550.3,
            3728.6,
            "展覧会を二周する理由と具体例です。",
            final_score=90.0,
        ).model_copy(update={"topic_key": "topic_3550300"}),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 0,
            "selectionPolicy": "strict_quality",
            "maxOverlapRatio": 0.8,
            "minFinalScore": 60.0,
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == [
        "normal_art_wide",
        "normal_history",
    ]
    rejection = next(
        item
        for item in selection.rejected_candidates
        if item.candidate_id == "normal_art_nested"
    )
    assert rejection.reasons == ["high_overlap"]
    assert rejection.details["overlapRatio"] > 0.5


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


def test_normal_and_short_do_not_block_each_other_by_overlap_by_default() -> None:
    candidates = [
        make_candidate("normal", "normal", 0.0, 120.0, "Complete normal clip.", final_score=90.0),
        make_candidate("short", "short", 10.0, 50.0, "Complete short clip.", final_score=88.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 1,
            "shortCount": 1,
            "maxOverlapRatio": 0.5,
            "minFinalScore": 60.0,
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal"]
    assert [candidate.id for candidate in selection.shorts] == ["short"]
    assert selection.cross_type_overlap_dedupe is False
    assert selection.cross_type_overlap_rejected_count == 0


def test_cross_type_overlap_dedupe_can_block_cross_type_candidates() -> None:
    candidates = [
        make_candidate("normal", "normal", 0.0, 120.0, "Complete normal clip.", final_score=90.0),
        make_candidate("short", "short", 10.0, 50.0, "Complete short clip.", final_score=88.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 1,
            "shortCount": 1,
            "maxOverlapRatio": 0.5,
            "minFinalScore": 60.0,
            "crossTypeOverlapDedupe": True,
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal"]
    assert selection.shorts == []
    assert selection.cross_type_overlap_dedupe is True
    assert selection.cross_type_overlap_rejected_count == 1
    assert selection.rejected_candidates[0].reasons == ["cross_type_high_overlap"]


def test_fill_requested_relaxes_overlap_when_needed() -> None:
    candidates = [
        make_candidate("normal_best", "normal", 0.0, 120.0, "Complete normal one.", final_score=92.0),
        make_candidate("normal_overlap", "normal", 5.0, 125.0, "Complete normal two.", final_score=91.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 0,
            "maxOverlapRatio": 0.8,
            "minFinalScore": 60.0,
            "selectionPolicy": "fill_requested",
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal_best", "normal_overlap"]
    relaxed = selection.normal_clips[1]
    assert relaxed.selection_reason == "backfill_overlap_relaxed"
    assert relaxed.overlap_relaxed is True
    assert relaxed.overlap_ratio_used is not None
    assert relaxed.overlap_ratio_used >= 0.8
    assert selection.overlap_relaxed_count == 1
    assert selection.unfilled_requested_counts["normal"] == 0


def test_strict_quality_does_not_relax_overlap() -> None:
    candidates = [
        make_candidate("normal_best", "normal", 0.0, 120.0, "Complete normal one.", final_score=92.0),
        make_candidate("normal_overlap", "normal", 5.0, 125.0, "Complete normal two.", final_score=91.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 0,
            "maxOverlapRatio": 0.8,
            "minFinalScore": 60.0,
            "selectionPolicy": "strict_quality",
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal_best"]
    assert selection.overlap_relaxed_count == 0
    assert selection.unfilled_requested_counts["normal"] == 1
    assert selection.rejected_candidates[0].candidate_id == "normal_overlap"
    assert selection.rejected_candidates[0].reasons == ["high_overlap"]


def test_fill_requested_keeps_hard_gate_failures_rejected() -> None:
    candidates = [
        make_candidate("empty", "normal", 0.0, 120.0, "", final_score=95.0),
        make_candidate("valid", "normal", 130.0, 250.0, "Complete valid normal clip.", final_score=80.0),
    ]

    selection = select_candidates(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 0,
            "minFinalScore": 60.0,
            "selectionPolicy": "fill_requested",
        },
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["valid"]
    assert selection.rejected_candidates[0].candidate_id == "empty"
    assert "no_transcript_text" in selection.rejected_candidates[0].reasons
    assert selection.hard_gate_rejected_count == 1


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
    assert payload["normalClips"][0]["hard_gate_passed"] is True
    assert payload["normalClips"][0]["below_quality_threshold"] is False
    assert payload["normalClips"][0]["selection_reason"] == "above_quality_threshold"
    assert payload["shorts"][0]["id"] == "short"
    assert payload["rejectedCandidates"] == []
