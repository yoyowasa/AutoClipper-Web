from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.generate_normal_candidates import generate_normal_candidates
from app.candidates.generate_short_candidates import generate_short_candidates
from app.candidates.merge_boundaries import (
    Candidate,
    adjust_end_to_speech_boundary,
    adjust_start_to_speech_boundary,
    is_inside_speech,
    merge_boundaries,
    transcript_text_for_range,
)
from app.video.scene_detect import SceneSegment


def test_merge_boundaries_combines_transcript_scene_and_silence() -> None:
    boundaries = merge_boundaries(
        transcript_segments=[TranscriptSegment(start=5.0, end=15.0, text="hello")],
        scene_segments=[SceneSegment(start=0.0, end=30.0)],
        silence_segments=[SilenceSegment(start=15.0, end=20.0, duration=5.0)],
    )

    assert boundaries == [0.0, 5.0, 15.0, 17.5, 20.0, 30.0]


def test_adjust_boundaries_away_from_inside_speech_when_within_tolerance() -> None:
    transcript_segments = [TranscriptSegment(start=10.0, end=50.0, text="speech")]

    assert adjust_start_to_speech_boundary(25.0, transcript_segments, tolerance=20.0) == 10.0
    assert adjust_end_to_speech_boundary(35.0, transcript_segments, tolerance=20.0) == 50.0
    assert adjust_start_to_speech_boundary(35.0, transcript_segments, tolerance=5.0) == 35.0


def test_transcript_text_for_range_uses_overlapping_segments() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=5.0, text="outside"),
        TranscriptSegment(start=10.0, end=20.0, text="first"),
        TranscriptSegment(start=20.0, end=30.0, text="second"),
        TranscriptSegment(start=40.0, end=50.0, text="later"),
    ]

    assert transcript_text_for_range(transcript_segments, 15.0, 35.0) == "first second"


def test_generate_short_candidates_default_duration_bounds() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=10.0, text="intro"),
        TranscriptSegment(start=12.0, end=30.0, text="hook"),
        TranscriptSegment(start=35.0, end=55.0, text="point"),
        TranscriptSegment(start=60.0, end=85.0, text="close"),
    ]
    candidates = generate_short_candidates(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=100.0)],
        silence_segments=[
            SilenceSegment(start=10.0, end=12.0, duration=2.0),
            SilenceSegment(start=30.0, end=35.0, duration=5.0),
            SilenceSegment(start=55.0, end=60.0, duration=5.0),
        ],
        settings={"shortCount": 1},
    )

    assert len(candidates) > 1
    assert all(candidate.type == "short" for candidate in candidates)
    assert all(20.0 <= candidate.duration <= 75.0 for candidate in candidates)
    assert all(candidate.transcript_text for candidate in candidates)
    assert_candidate_shape(candidates[0])


def test_generate_normal_candidates_default_duration_bounds() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=60.0, text="part 1"),
        TranscriptSegment(start=65.0, end=120.0, text="part 2"),
        TranscriptSegment(start=130.0, end=240.0, text="part 3"),
        TranscriptSegment(start=250.0, end=360.0, text="part 4"),
        TranscriptSegment(start=370.0, end=500.0, text="part 5"),
        TranscriptSegment(start=510.0, end=700.0, text="part 6"),
    ]
    candidates = generate_normal_candidates(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=720.0)],
        silence_segments=[
            SilenceSegment(start=60.0, end=65.0, duration=5.0),
            SilenceSegment(start=120.0, end=130.0, duration=10.0),
            SilenceSegment(start=240.0, end=250.0, duration=10.0),
            SilenceSegment(start=360.0, end=370.0, duration=10.0),
            SilenceSegment(start=500.0, end=510.0, duration=10.0),
        ],
        settings={"normalClipCount": 1},
    )

    assert len(candidates) > 1
    assert all(candidate.type == "normal" for candidate in candidates)
    assert all(90.0 <= candidate.duration <= 600.0 for candidate in candidates)
    assert all(candidate.transcript_text for candidate in candidates)
    assert_candidate_shape(candidates[0])


def test_generate_normal_candidates_can_use_shorter_configured_duration() -> None:
    transcript_segments = [
        TranscriptSegment(
            start=0.0,
            end=60.0,
            text="why automation teams need a complete launch checklist before publishing a video workflow",
        )
    ]
    scene_segments = [SceneSegment(start=0.0, end=60.0)]

    default_candidates = generate_normal_candidates(
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=[],
    )
    configured_candidates = generate_normal_candidates(
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=[],
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 60,
        },
    )

    assert default_candidates == []
    assert configured_candidates
    assert all(20.0 <= candidate.duration <= 60.0 for candidate in configured_candidates)
    assert all(candidate.type == "normal" for candidate in configured_candidates)


def test_generate_short_candidates_avoid_cutting_inside_speech_when_possible() -> None:
    transcript_segments = [TranscriptSegment(start=10.0, end=50.0, text="single speech block")]
    candidates = generate_short_candidates(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=100.0)],
        silence_segments=[SilenceSegment(start=25.0, end=26.0, duration=1.0)],
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 75,
            "speechBoundaryTolerance": 20,
        },
    )

    assert any(candidate.start == 10.0 and candidate.end == 50.0 for candidate in candidates)
    assert all(not is_inside_speech(candidate.start, transcript_segments) for candidate in candidates)
    assert all(not is_inside_speech(candidate.end, transcript_segments) for candidate in candidates)


def test_generators_return_empty_when_duration_is_too_short() -> None:
    transcript_segments = [TranscriptSegment(start=0.0, end=10.0, text="too short")]
    scene_segments = [SceneSegment(start=0.0, end=10.0)]

    assert generate_short_candidates(transcript_segments, scene_segments, []) == []
    assert generate_normal_candidates(transcript_segments, scene_segments, []) == []


def assert_candidate_shape(candidate: Candidate) -> None:
    assert candidate.id.startswith(f"cand_{candidate.type}_")
    assert candidate.start >= 0
    assert candidate.end > candidate.start
    assert candidate.duration == round(candidate.end - candidate.start, 3)
    assert candidate.transcript_text
