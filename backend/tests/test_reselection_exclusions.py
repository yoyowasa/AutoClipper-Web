from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import CodexSelectionConstraints, build_codex_initial_selection_request
from app.candidates.merge_boundaries import Candidate
from app.candidates.used_ranges import (
    PREVIOUS_PROPOSALS_SETTING,
    near_duplicate_of_previous,
    with_reselection_exclusions,
    used_ranges,
)
from app.jobs.pipeline_common import (
    _is_repeated_normal_proposal,
    _unused_candidates,
)
from app.candidates.manual_ranges import MANUAL_SELECTION_REASON


def test_reselection_excludes_previous_rounds_from_codex_and_local_candidates():
    original = {"excludePreviousSelection": True, "_usedSourceRanges": [(80, 90)],
                "shortClipSelectionPreset": "funny", "shortClipGuidance": "笑えるやり取り"}
    plan = SimpleNamespace(settings={"_reselectionExcludedRanges": [[10, 20]]},
                           clips=[SimpleNamespace(start=30, end=40)])
    settings = with_reselection_exclusions(original, plan)
    assert used_ranges(settings) == [(10, 20), (30, 40), (80, 90)]
    assert original["_usedSourceRanges"] == [(80, 90)]
    segments = [TranscriptSegment(start=start, end=start+5, text=f"scene {start}")
                for start in (10, 30, 50, 80)]
    request = build_codex_initial_selection_request(
        job_id="reselect", transcript_segments=segments, heatmap_segments=[],
        video_duration=100, settings=settings,
    )
    assert [segment.start for segment in request.transcript] == [50]
    assert request.constraints.short.preset == "funny"
    assert "笑えるやり取り" in request.constraints.short.guidance
    candidates = [Candidate(id=str(s.start), type="short", start=s.start, end=s.end,
                            duration=5, transcript_text=s.text) for s in segments]
    assert [c.start for c in _unused_candidates(candidates, settings)] == [50]
    next_plan = SimpleNamespace(settings=settings, clips=[SimpleNamespace(start=50, end=55)])
    again = with_reselection_exclusions(original, next_plan)
    assert used_ranges(again) == [(10, 20), (30, 40), (50, 55), (80, 90)]


def test_reselection_exclusions_can_be_disabled_without_losing_export_history():
    settings = {"excludePreviousSelection": False, "_usedSourceRanges": [(80, 90)]}
    plan = SimpleNamespace(settings={"_reselectionExcludedRanges": [[10, 20]]},
                           clips=[SimpleNamespace(start=30, end=40)])
    result = with_reselection_exclusions(settings, plan)
    assert used_ranges(result) == [(80, 90)]
    assert result[PREVIOUS_PROPOSALS_SETTING] == [(10, 20), (30, 40)]
    assert with_reselection_exclusions(settings, None) == settings


def test_reselection_off_avoids_almost_unchanged_clip_but_allows_longer_edit():
    settings = {"excludePreviousSelection": False}
    plan = SimpleNamespace(settings={"_reselectionExcludedRanges": [[11122.41, 11452.19]]},
                           clips=[])
    result = with_reselection_exclusions(settings, plan)
    assert near_duplicate_of_previous(11122.41, 11461.73, result)
    assert not near_duplicate_of_previous(11122.41, 11722.41, result)
    request = build_codex_initial_selection_request(
        job_id="reselect", transcript_segments=[
            TranscriptSegment(start=11122, end=11130, text="過去候補"),
            TranscriptSegment(start=11600, end=11610, text="別の話題"),
        ], heatmap_segments=[], video_duration=12202,
        settings={**result, "normalClipCount": 1, "shortCount": 0,
                  "normalMinDuration": 300, "normalMaxDuration": 600},
    )
    assert [item.start for item in request.transcript] == [11122, 11600]
    assert request.constraints.normal_candidate_count == 3
    assert "11122.41-11452.19" in request.constraints.normal.context_guidance


@pytest.mark.parametrize("user_length", [0, 950, 1000])
def test_past_ranges_are_bounded_without_cutting_user_guidance_or_filter_history(user_length):
    ranges = [(i * 1000, i * 1000 + 300 + i) for i in range(39)]
    user_guidance = "指" * user_length
    settings = {
        PREVIOUS_PROPOSALS_SETTING: ranges, "excludePreviousSelection": False,
        "normalClipGuidance": user_guidance, "shortClipGuidance": "短い指示",
        "_usedSourceRanges": [(1, 2)],
    }
    request = build_codex_initial_selection_request(
        job_id="many-ranges", transcript_segments=[TranscriptSegment(start=10, end=20, text="字幕")],
        heatmap_segments=[], video_duration=40000, settings=settings,
    )
    normal = request.constraints.normal
    assert normal.guidance == user_guidance
    assert request.constraints.short.guidance == "短い指示"
    assert len(normal.guidance) <= 1000
    assert len(normal.context_guidance) <= 1000
    intervals = normal.context_guidance.split("長い順）: ", 1)[1].split("（ほか", 1)[0].split(", ")
    assert intervals == [f"{i * 1000}-{i * 1000 + 300 + i}" for i in range(38, 23, -1)]
    assert "ほか24件" in normal.context_guidance
    assert settings[PREVIOUS_PROPOSALS_SETTING] == ranges
    assert len(settings[PREVIOUS_PROPOSALS_SETTING]) == 39
    assert _is_repeated_normal_proposal(
        Candidate(id="omitted", type="normal", start=0, end=300, duration=300, transcript_text="字幕"), settings,
    )
    restored = type(request).model_validate_json(request.model_dump_json(by_alias=True))
    assert restored.constraints.normal == normal


def test_past_guidance_merges_ranges_before_ranking():
    request = build_codex_initial_selection_request(
        job_id="merged-ranges", transcript_segments=[TranscriptSegment(start=0, end=10, text="字幕")],
        heatmap_segments=[], video_duration=1000,
        settings={PREVIOUS_PROPOSALS_SETTING: [(100, 200), (150, 400), (500, 600)]},
    )
    assert "100-400, 500-600。" in request.constraints.normal.context_guidance
    assert "ほか" not in request.constraints.normal.context_guidance


def test_reselection_keeps_individual_proposals_for_duplicate_checks_across_rounds():
    original = {"excludePreviousSelection": False}
    plan = SimpleNamespace(settings={PREVIOUS_PROPOSALS_SETTING: [(100, 430)]},
                           clips=[SimpleNamespace(start=100, end=700)])
    settings = with_reselection_exclusions(original, plan)
    assert settings[PREVIOUS_PROPOSALS_SETTING] == [(100, 430), (100, 700)]
    assert near_duplicate_of_previous(100, 430, settings)
    next_plan = SimpleNamespace(settings=settings, clips=[SimpleNamespace(start=800, end=1100)])
    next_settings = with_reselection_exclusions(original, next_plan)
    assert next_settings[PREVIOUS_PROPOSALS_SETTING] == [(100, 430), (100, 700), (800, 1100)]
    assert near_duplicate_of_previous(100, 430, next_settings)
    request = build_codex_initial_selection_request(
        job_id="full-history", transcript_segments=[TranscriptSegment(start=0, end=10, text="字幕")],
        heatmap_segments=[], video_duration=1200, settings=next_settings,
    )
    assert "100-700, 800-1100。" in request.constraints.normal.context_guidance
    assert next_settings[PREVIOUS_PROPOSALS_SETTING] == [(100, 430), (100, 700), (800, 1100)]


@pytest.mark.parametrize("previous,exclude,requested,expected", [
    ([], False, 1, 1), ([(20, 30)], True, 1, 1), ([(20, 30)], False, 1, 3),
    ([(20, 30)], False, 12, 24),
])
def test_normal_candidate_count_has_one_expected_value(previous, exclude, requested, expected):
    request = build_codex_initial_selection_request(
        job_id="pool-count", transcript_segments=[TranscriptSegment(start=0, end=10, text="字幕")],
        heatmap_segments=[], video_duration=1000,
        settings={PREVIOUS_PROPOSALS_SETTING: previous, "excludePreviousSelection": exclude,
                  "normalClipCount": requested, "shortCount": 0, "normalMinDuration": 300, "normalMaxDuration": 600},
    )
    assert request.constraints.normal_candidate_count == expected
    payload = request.constraints.model_dump(by_alias=True)
    assert payload["expandNormalReselectionPool"] is (bool(previous) and not exclude)
    assert CodexSelectionConstraints.model_validate(payload) == request.constraints
    payload["normalCandidateCount"] = requested if expected != requested else requested * 3
    with pytest.raises(ValidationError, match="configured candidate pool"):
        CodexSelectionConstraints.model_validate(payload)


@pytest.mark.parametrize("kind,reason,expected", [
    ("normal", "codex_direct", True), ("short", "codex_direct", False),
    ("normal", MANUAL_SELECTION_REASON, False), ("short", MANUAL_SELECTION_REASON, False),
])
def test_past_proposal_filter_only_applies_to_automatic_normal_candidates(kind, reason, expected):
    settings = {PREVIOUS_PROPOSALS_SETTING: [(100, 430)], "excludePreviousSelection": False}
    candidate = Candidate(
        id="repeat", type=kind, start=100, end=430, duration=330, selection_reason=reason, transcript_text="字幕",
    )
    assert _is_repeated_normal_proposal(candidate, settings) is expected
    assert not _is_repeated_normal_proposal(candidate.model_copy(update={"end": 700, "duration": 600}), settings)
