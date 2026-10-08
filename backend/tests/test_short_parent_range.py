import json

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import (
    CodexClipProposal,
    CodexInitialSelectionResponse,
    CodexInitialSelectionSummary,
    CodexSelectedTopicInput,
    _normalize_proposal_parent_range,
    _validate_proposal_moment_metadata,
    build_codex_initial_selection_request,
    convert_codex_initial_selection_response,
    write_codex_initial_selection_summary,
)
from app.candidates.short_diversity import select_diverse_shorts


def context(*, start=100.0, end=120.0, parent_start=98.0, parent_end=122.0, source=200.0):
    request = build_codex_initial_selection_request(
        job_id="job_parent", video_duration=source, heatmap_segments=[],
        transcript_segments=[TranscriptSegment(start=start, end=end, text="内容が伝わる科学の発見です。")],
        settings={"normalClipCount": 0, "shortCount": 1, "shortMinDuration": 0, "shortMaxDuration": 75},
    )
    proposal = CodexClipProposal(
        proposalId="proposal_003", type="short", topicKey="science", start=start, end=end,
        parentStart=parent_start, parentEnd=parent_end, momentKey="discovery",
        evidenceSegmentIds=[request.transcript[0].id], heatmapSegmentIds=[],
        reason="題材と結論が揃っています。", confidence=0.9, riskFlags=[],
    )
    return request, proposal


def convert(request, *proposals):
    response = CodexInitialSelectionResponse(
        version=1, promptVersion=request.prompt_version, jobId=request.job_id,
        requestId=request.request_id, inputHash=request.input_hash, threadId="thread_test",
        selectedClips=list(proposals), warnings=[],
    )
    return convert_codex_initial_selection_response(request, response)


@pytest.mark.parametrize("ratio,expected,adjusted", [
    (1.2, 1.5, True), (1.4, 1.5, True), (1.5, 1.5, False),
    (3.0, 3.0, False), (3.1, 3.0, True), (4.0, 3.0, True),
])
def test_ratio_is_clamped_and_candidate_is_retained(ratio, expected, adjusted):
    request, proposal = context(parent_start=110 - 10 * ratio, parent_end=110 + 10 * ratio)
    original = proposal.model_dump()
    result = convert(request, proposal)
    assert len(result.selection.shorts) == 1 and not result.dropped_short_candidates
    candidate = result.selection.shorts[0]
    assert (candidate.parent_end - candidate.parent_start) / candidate.duration == pytest.approx(expected)
    assert candidate.parent_start <= candidate.start < candidate.end <= candidate.parent_end
    assert candidate.start == proposal.start and candidate.end == proposal.end
    assert candidate.moment_key == proposal.moment_key
    assert candidate.evidence_segment_ids == proposal.evidence_segment_ids
    assert proposal.model_dump() == original
    assert ("parentRangeAdjustments" in result.summary) is adjusted
    if adjusted:
        record = result.summary["parentRangeAdjustments"][0]
        assert record == {
            "proposalId": proposal.proposal_id, "reason": "parent_ratio_adjusted",
            "originalParentStart": proposal.parent_start, "originalParentEnd": proposal.parent_end,
            "originalRatio": pytest.approx(ratio), "adjustedParentStart": candidate.parent_start,
            "adjustedParentEnd": candidate.parent_end, "adjustedRatio": pytest.approx(expected), "sourceLimited": False,
        }


@pytest.mark.parametrize("start,end,parent_start,parent_end,source,expected_start,expected_end", [
    (0, 20, 0, 24, 200, 0, 30), (2, 22, 0, 24, 200, 0, 30),
    (178, 198, 176, 200, 200, 170, 200), (180, 200, 176, 200, 200, 170, 200),
    (0, 20, 0, 24, 26, 0, 26), (4, 24, 2, 26, 26, 0, 26),
    (0, 10, 0, 10, 10, 0, 10),
])
def test_source_edges_and_short_video_keep_maximum_available_context(
    start, end, parent_start, parent_end, source, expected_start, expected_end,
):
    request, proposal = context(start=start, end=end, parent_start=parent_start, parent_end=parent_end, source=source)
    result = convert(request, proposal)
    candidate = result.selection.shorts[0]
    assert not result.dropped_short_candidates
    assert (candidate.parent_start, candidate.parent_end) == pytest.approx((expected_start, expected_end))
    assert 0 <= candidate.parent_start <= candidate.start < candidate.end <= candidate.parent_end <= source
    record = result.summary["parentRangeAdjustments"][0]
    assert record["sourceLimited"] is (source < (end - start) * 1.5)


@pytest.mark.parametrize("parent_start,parent_end,code", [
    (110, 100, "codex_initial_selection_parent_range_invalid"),
    (101, 125, "codex_initial_selection_parent_not_containing_final"),
    (95, 119, "codex_initial_selection_parent_not_containing_final"),
    (0, 201, "codex_initial_selection_parent_outside_source"),
])
def test_malformed_original_parent_ranges_are_not_repaired(parent_start, parent_end, code):
    request, proposal = context(parent_start=parent_start, parent_end=parent_end)
    result = convert(request, proposal)
    assert not result.selection.shorts
    assert result.dropped_short_candidates[0].code == code
    assert "parentRangeAdjustments" not in result.summary


def test_validation_is_read_only_and_normalization_returns_a_copy():
    request, proposal = context()
    original = proposal.model_dump()
    _validate_proposal_moment_metadata(proposal)
    assert proposal.model_dump() == original
    normalized, record = _normalize_proposal_parent_range(proposal, request)
    assert normalized is not proposal and record is not None
    assert proposal.model_dump() == original
    assert (normalized.parent_start, normalized.parent_end) == (95, 125)


def test_parent_can_extend_outside_topic_window_but_final_clip_cannot():
    request, proposal = context()
    topic = CodexSelectedTopicInput(
        selectionId="topic", type="short", topicKey=proposal.topic_key, topicBlockIds=["block"],
        start=100, end=120, windowStart=99, windowEnd=121, reason="この話題の場面", confidence=0.9,
    )
    request = request.model_copy(update={"selected_topics": [topic]})
    result = convert(request, proposal)
    candidate = result.selection.shorts[0]
    assert candidate.parent_start < topic.window_start and candidate.parent_end > topic.window_end
    outside_final = proposal.model_copy(update={"start": 98, "parent_start": 95})
    result = convert(request, outside_final)
    assert result.dropped_short_candidates[0].code == "codex_initial_selection_topic_range_invalid"


@pytest.mark.parametrize("phase,filename", [("initial", "codex_initial_selection_summary.json"),
                                           ("reselection", "codex_reselection_summary.json")])
def test_adjustment_audit_survives_summary_validation_and_persistence(tmp_path, phase, filename):
    request, proposal = context()
    result = convert(request, proposal)
    summary = {**result.summary, "phase": phase}
    path = write_codex_initial_selection_summary(summary, tmp_path / filename)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["parentRangeAdjustments"] == result.summary["parentRangeAdjustments"]
    assert saved["phase"] == phase
    old_summary = {key: value for key, value in saved.items() if key != "parentRangeAdjustments"}
    restored = CodexInitialSelectionSummary.model_validate(old_summary)
    assert restored.parent_range_adjustments == []
    assert restored.model_dump(by_alias=True, mode="json") == old_summary


def test_radio_proposal_003_coordinates_are_repaired_without_changing_finished_clip():
    request, proposal = context(start=2992.08, end=3066.72, parent_start=2960.44, parent_end=3071.4, source=8235)
    result = convert(request, proposal)
    candidate = result.selection.shorts[0]
    assert (candidate.start, candidate.end) == (2992.08, 3066.72)
    assert (candidate.parent_start, candidate.parent_end) == pytest.approx((2973.42, 3085.38))
    assert result.summary["parentRangeAdjustments"][0]["originalRatio"] == pytest.approx(1.486602357985)
    assert result.summary["parentRangeAdjustments"][0]["adjustedRatio"] == pytest.approx(1.5)
    assert not result.dropped_short_candidates


def test_post_refinement_diversity_uses_adjusted_parent_ranges():
    request = build_codex_initial_selection_request(
        job_id="job_diversity", video_duration=200, heatmap_segments=[],
        transcript_segments=[TranscriptSegment(start=20, end=40, text="科学の発見を紹介します。"),
                             TranscriptSegment(start=70, end=90, text="新しい料理の失敗で爆笑しました。")],
        settings={"normalClipCount": 0, "shortCount": 2, "shortMinDuration": 0, "shortMaxDuration": 75},
    )
    proposals = [CodexClipProposal(
        proposalId=f"proposal_{n}", type="short", topicKey=f"topic_{n}", momentKey=f"moment_{n}",
        start=start, end=end, parentStart=parent_start, parentEnd=parent_end,
        evidenceSegmentIds=[request.transcript[n].id], heatmapSegmentIds=[],
        reason="独立した見どころです。", confidence=0.9 - n * 0.01, riskFlags=[],
    ) for n, (start, end, parent_start, parent_end) in enumerate([(20, 40, 0, 100), (70, 90, 10, 110)])]
    result = convert(request, *proposals)
    assert len(result.selection.shorts) == 2
    normalized = select_diverse_shorts(result.selection.shorts, requested_count=2)
    assert len(normalized.selected) == 2 and normalized.rejected == ()
    original_candidates = [candidate.model_copy(update={"parent_start": proposal.parent_start, "parent_end": proposal.parent_end})
                           for candidate, proposal in zip(result.selection.shorts, proposals, strict=True)]
    original = select_diverse_shorts(original_candidates, requested_count=2)
    assert len(original.selected) == 1
    assert "high_parent_overlap" in original.rejected[0].reasons
