from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.boundary_refinement import refine_candidate_boundaries, refine_selected_candidates
from app.candidates.merge_boundaries import Candidate
from app.video.scene_detect import SceneSegment


def make_candidate(
    candidate_id: str,
    candidate_type: str,
    start: float,
    end: float,
    text: str = "selected transcript",
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text=text,
        rule_score=80.0,
        final_score=80.0,
    )


def test_start_inside_transcript_segment_adjusts_to_segment_start() -> None:
    candidate = make_candidate("normal_1", "normal", 10.5, 40.0)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=20.0, text="自然な開始")],
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 60,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
        },
        timeline_duration=60,
    )

    assert refined.start == 10.0
    assert refined.end == 40.0
    assert refined.original_start == 10.5
    assert refined.refined_start == 10.0
    assert refined.boundary_refined is True
    assert "start_to_transcript_segment_start" in str(refined.boundary_refinement_reason)


def test_end_inside_transcript_segment_adjusts_to_segment_end() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 19.5)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=20.0, text="自然な終わり")],
        settings={
            "shortMinDuration": 15,
            "shortMaxDuration": 30,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
        },
        timeline_duration=40,
    )

    assert refined.start == 0.0
    assert refined.end == 20.0
    assert refined.original_end == 19.5
    assert refined.refined_end == 20.0
    assert refined.boundary_refined is True
    assert "end_to_transcript_segment_end" in str(refined.boundary_refinement_reason)


def test_leading_and_trailing_padding_are_applied_within_bounds() -> None:
    candidate = make_candidate("short_1", "short", 10.5, 39.5)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=40.0, text="padding target")],
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 60,
            "boundaryLeadingPaddingSeconds": 0.5,
            "boundaryTrailingPaddingSeconds": 0.25,
            "maxBoundaryExpansionSeconds": 5,
        },
        timeline_duration=80,
    )

    assert refined.start == 9.5
    assert refined.end == 40.25
    assert refined.duration == 30.75
    assert refined.boundary_expansion_seconds == 1.75
    assert "leading_padding" in str(refined.boundary_refinement_reason)
    assert "trailing_padding" in str(refined.boundary_refinement_reason)


def test_padding_uses_adjacent_silence_intervals_when_available() -> None:
    candidate = make_candidate("short_1", "short", 10.5, 39.5)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=40.0, text="padding target")],
        silence_segments=[
            SilenceSegment(start=9.0, end=10.0, duration=1.0),
            SilenceSegment(start=40.0, end=41.0, duration=1.0),
        ],
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 60,
            "boundaryLeadingPaddingSeconds": 0.5,
            "boundaryTrailingPaddingSeconds": 0.25,
            "maxBoundaryExpansionSeconds": 5,
        },
        timeline_duration=80,
    )

    assert refined.start == 9.5
    assert refined.end == 40.25
    assert "leading_padding_in_silence" in str(refined.boundary_refinement_reason)
    assert "trailing_padding_in_silence" in str(refined.boundary_refinement_reason)


def test_max_duration_is_respected_unless_expansion_is_allowed() -> None:
    candidate = make_candidate("normal_1", "normal", 10.5, 60.5)
    transcript = [TranscriptSegment(start=8.0, end=62.0, text="max duration target")]

    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=transcript,
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 50,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
            "maxBoundaryExpansionSeconds": 5,
        },
        timeline_duration=90,
    )
    allowed = refine_candidate_boundaries(
        candidate,
        transcript_segments=transcript,
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 50,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
            "maxBoundaryExpansionSeconds": 5,
            "allowBoundaryExpansionBeyondMaxDuration": True,
        },
        timeline_duration=90,
    )

    assert refined.duration <= 50
    assert allowed.start == 8.0
    assert allowed.end == 62.0
    assert allowed.duration > 50


def test_min_duration_is_preserved() -> None:
    candidate = make_candidate("short_1", "short", 10.5, 30.5)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=31.0, text="minimum duration target")],
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 30,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
        },
        timeline_duration=60,
    )

    assert refined.duration >= 20


def test_weak_continuation_can_expand_to_previous_segment() -> None:
    candidate = make_candidate("short_1", "short", 12.0, 35.0)
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[
            TranscriptSegment(start=9.5, end=11.0, text="前の文です。"),
            TranscriptSegment(start=12.0, end=20.0, text="だから続きを話します。"),
        ],
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 40,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
            "maxBoundaryExpansionSeconds": 3,
        },
        timeline_duration=60,
    )

    assert refined.start == 9.5
    assert "weak_continuation_expanded_start" in str(refined.boundary_refinement_reason)


def test_refinement_updates_transcript_and_silence_metadata() -> None:
    candidate = make_candidate("normal_1", "normal", 10.5, 40.0, text="old text")
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[
            TranscriptSegment(start=10.0, end=20.0, text="first text"),
            TranscriptSegment(start=20.0, end=40.0, text="second text"),
        ],
        silence_segments=[SilenceSegment(start=30.0, end=35.0, duration=5.0)],
        scene_segments=[SceneSegment(start=10.0, end=40.0)],
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 60,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
        },
        timeline_duration=60,
    )

    assert refined.transcript_text == "first text second text"
    assert refined.transcript_char_count == len("first text second text")
    assert refined.speech_seconds == 30.0
    assert refined.silence_ratio == 0.166667
    assert refined.original_start == 10.5
    assert refined.refined_start == 10.0


def test_refine_selected_candidates_handles_short_and_normal() -> None:
    candidates = [
        make_candidate("normal_1", "normal", 10.5, 40.0),
        make_candidate("short_1", "short", 50.5, 80.0),
    ]

    refined = refine_selected_candidates(
        candidates,
        transcript_segments=[
            TranscriptSegment(start=10.0, end=20.0, text="normal text"),
            TranscriptSegment(start=50.0, end=60.0, text="short text"),
        ],
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 60,
            "shortMinDuration": 20,
            "shortMaxDuration": 60,
            "boundaryLeadingPaddingSeconds": 0,
            "boundaryTrailingPaddingSeconds": 0,
        },
        timeline_duration=100,
    )

    assert [candidate.start for candidate in refined] == [10.0, 50.0]
    assert all(candidate.boundary_refined is True for candidate in refined)


def test_refinement_can_be_disabled_without_changing_boundaries_or_text() -> None:
    candidate = make_candidate("short_1", "short", 10.5, 30.5, text="original text")
    refined = refine_candidate_boundaries(
        candidate,
        transcript_segments=[TranscriptSegment(start=10.0, end=31.0, text="replacement text")],
        settings={
            "enableBoundaryRefinement": False,
            "shortMinDuration": 20,
            "shortMaxDuration": 40,
        },
        timeline_duration=60,
    )

    assert refined.start == 10.5
    assert refined.end == 30.5
    assert refined.transcript_text == "original text"
    assert refined.boundary_refined is False
    assert refined.boundary_refinement_reason == "disabled"
    assert refined.boundary_expansion_seconds == 0.0
