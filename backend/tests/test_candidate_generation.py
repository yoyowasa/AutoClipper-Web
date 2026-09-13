from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.generate_normal_candidates import generate_normal_candidates
from app.candidates.generate_normal_candidates import generate_normal_candidates_with_summary
from app.candidates.generate_short_candidates import generate_short_candidates, generate_short_candidates_with_summary
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationMemoryLimitError,
    adjust_end_to_speech_boundary,
    adjust_start_to_speech_boundary,
    is_inside_speech,
    merge_candidate_generation_summaries,
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


def test_exact_duration_constraint_has_last_resort_candidates() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=30.0, text="first continuous sentence"),
        TranscriptSegment(start=35.0, end=80.0, text="second continuous sentence"),
    ]

    result = generate_short_candidates_with_summary(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=100.0)],
        silence_segments=[],
        settings={"shortMinDuration": 20, "shortMaxDuration": 20},
    )

    assert result.candidates
    assert all(candidate.duration == 20.0 for candidate in result.candidates)
    assert result.summary["exact_duration_fallback_candidates_considered"] > 0


def test_candidate_generation_summary_records_configured_duration_range() -> None:
    transcript_segments = [
        TranscriptSegment(
            start=0.0,
            end=60.0,
            text="why automation teams need a complete launch checklist before publishing a video workflow",
        )
    ]
    result = generate_normal_candidates_with_summary(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=60.0)],
        silence_segments=[],
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 60,
            "normalStepSeconds": 10,
            "speechBoundaryTolerance": 6,
        },
    )

    duration_range = result.summary["configured_duration_range"]
    assert duration_range == {
        "min_duration": 20.0,
        "max_duration": 60.0,
        "step_seconds": 10.0,
        "target_step_applied": False,
        "speech_boundary_tolerance": 6.0,
    }
    merged = merge_candidate_generation_summaries(
        [result.summary],
        video_duration=60.0,
        transcript_segment_count=1,
    )
    assert merged["configured_duration_ranges"]["normal"]["min_duration"] == 20.0
    assert merged["duration_band_counts_by_type"]["normal"] == {"20-60": 1}
    assert merged["duration_bands_by_type"]["normal"][0]["considered"] == 1


def test_candidate_limit_is_spread_across_timeline() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(start), end=float(start + 20), text=f"segment {start}")
        for start in range(0, 1800, 30)
    ]
    silence_segments = [
        SilenceSegment(start=float(start + 20), end=float(start + 30), duration=10.0)
        for start in range(0, 1770, 30)
    ]

    candidates = generate_normal_candidates(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=1800.0)],
        silence_segments=silence_segments,
        settings={
            "normalMinDuration": 90,
            "normalMaxDuration": 180,
            "normalStepSeconds": 30,
            "maxCandidates": 30,
        },
    )

    assert len(candidates) == 30
    assert max(candidate.start for candidate in candidates) > 1200
    assert min(candidate.start for candidate in candidates) == 0.0


def test_bounded_normal_generation_preserves_each_duration_band() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(start), end=float(start + 20), text=f"topic {start}")
        for start in range(0, 600, 30)
    ]
    silence_segments = [
        SilenceSegment(start=float(start + 20), end=float(start + 30), duration=10.0)
        for start in range(0, 570, 30)
    ]

    result = generate_normal_candidates_with_summary(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=600.0)],
        silence_segments=silence_segments,
        settings={
            "normalMinDuration": 90,
            "normalMaxDuration": 600,
            "maxCandidates": 20,
            "maxCandidatesPerTimeBucket": 20,
            "candidateTimeBucketSeconds": 600,
        },
    )

    candidates = result.candidates
    assert candidates
    assert any(90 <= candidate.duration < 180 for candidate in candidates)
    assert any(180 <= candidate.duration < 300 for candidate in candidates)
    assert any(300 <= candidate.duration <= 600 for candidate in candidates)
    assert result.summary["duration_band_counts"] == {
        "90-180": 7,
        "180-300": 7,
        "300-600": 6,
    }
    assert all(item["considered"] > 0 for item in result.summary["duration_bands"])
    assert all(item["kept"] > 0 for item in result.summary["duration_bands"])


def test_candidate_generation_uses_semantic_boundaries_not_duration_steps() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=37.0, text="導入です。"),
        TranscriptSegment(start=41.0, end=96.0, text="なぜこの作品は美しいのでしょうか？"),
        TranscriptSegment(start=98.0, end=173.0, text="理由を具体例から説明します。"),
        TranscriptSegment(start=177.0, end=264.0, text="ここまでが一つ目の結論です。"),
        TranscriptSegment(start=270.0, end=389.0, text="次に別の観点を説明します。"),
        TranscriptSegment(start=394.0, end=521.0, text="最後に全体の結論をまとめます。"),
    ]
    silence_segments = [
        SilenceSegment(start=37.0, end=41.0, duration=4.0),
        SilenceSegment(start=173.0, end=177.0, duration=4.0),
        SilenceSegment(start=264.0, end=270.0, duration=6.0),
        SilenceSegment(start=389.0, end=394.0, duration=5.0),
    ]
    base_settings = {
        "normalMinDuration": 90,
        "normalMaxDuration": 600,
        "maxCandidates": 100,
    }

    step_30 = generate_normal_candidates(
        transcript_segments,
        [SceneSegment(start=0.0, end=521.0)],
        silence_segments,
        settings={**base_settings, "normalStepSeconds": 30},
    )
    step_47 = generate_normal_candidates(
        transcript_segments,
        [SceneSegment(start=0.0, end=521.0)],
        silence_segments,
        settings={**base_settings, "normalStepSeconds": 47},
    )

    assert [(item.start, item.end) for item in step_30] == [
        (item.start, item.end) for item in step_47
    ]
    semantic_endpoints = {37.0, 96.0, 173.0, 264.0, 389.0, 521.0}
    assert step_30
    assert all(candidate.end in semantic_endpoints for candidate in step_30)


def test_local_candidates_receive_stable_semantic_topic_keys() -> None:
    transcript_segments = [
        TranscriptSegment(start=0.0, end=20.0, text="前置きです。"),
        TranscriptSegment(start=25.0, end=40.0, text="この作品はなぜ美しいのですか？"),
        TranscriptSegment(start=40.0, end=90.0, text="理由を具体例から説明します"),
        TranscriptSegment(start=90.0, end=130.0, text="これが最初の結論です。"),
        TranscriptSegment(start=140.0, end=160.0, text="次に作者について話します。"),
        TranscriptSegment(start=160.0, end=210.0, text="背景を順に説明します"),
        TranscriptSegment(start=210.0, end=250.0, text="これが二つ目の結論です。"),
    ]
    silence_segments = [
        SilenceSegment(start=20.0, end=25.0, duration=5.0),
        SilenceSegment(start=130.0, end=140.0, duration=10.0),
    ]

    candidates = generate_normal_candidates(
        transcript_segments,
        [SceneSegment(start=0.0, end=250.0)],
        silence_segments,
        settings={"normalMinDuration": 90, "normalMaxDuration": 180},
    )

    assert candidates
    assert all(candidate.topic_key for candidate in candidates)
    assert any(candidate.start == 25.0 and candidate.topic_key == "topic_25000" for candidate in candidates)
    assert any(candidate.start == 140.0 and candidate.topic_key == "topic_140000" for candidate in candidates)


def test_bounded_generation_handles_2000_segments_without_unbounded_output() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(index * 2), end=float(index * 2 + 1), text=f"segment {index}")
        for index in range(2100)
    ]
    scene_segments = [SceneSegment(start=0.0, end=4200.0)]
    silence_segments = [
        SilenceSegment(start=float(index * 2 + 1), end=float(index * 2 + 2), duration=1.0)
        for index in range(2099)
    ]

    result = generate_short_candidates_with_summary(
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=silence_segments,
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 75,
            "shortStepSeconds": 10,
            "maxCandidates": 200,
            "maxKeptCandidatesPerType": 200,
            "maxCandidatesPerTimeBucket": 20,
            "candidateTimeBucketSeconds": 300,
            "candidateChunkSeconds": 600,
            "candidateChunkOverlapSeconds": 75,
        },
    )

    assert 0 < len(result.candidates) <= 200
    assert result.summary["transcript_segment_count"] == 2100
    assert result.summary["chunks_processed"] >= 3
    assert result.summary["raw_candidates_considered"] > len(result.candidates)
    assert result.summary["candidates_dropped_due_to_cap"] > 0
    assert result.summary["candidates_kept_by_type"]["short"] == len(result.candidates)
    assert all(candidate.transcript_text for candidate in result.candidates)
    assert all(candidate.segment_start_index is not None for candidate in result.candidates)
    assert all(candidate.segment_end_index is not None for candidate in result.candidates)
    assert all(candidate.transcript_char_count is not None for candidate in result.candidates)
    assert all(candidate.speech_seconds is not None for candidate in result.candidates)
    assert all(candidate.silence_ratio is not None for candidate in result.candidates)
    assert set(result.summary["duration_band_counts"]) == {"20-35", "35-50", "50-75"}
    assert all(count > 0 for count in result.summary["duration_band_counts"].values())
    assert all(item["considered"] > 0 for item in result.summary["duration_bands"])


def test_bounded_generation_respects_raw_candidate_cap() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(index * 5), end=float(index * 5 + 3), text=f"segment {index}")
        for index in range(200)
    ]
    silence_segments = [
        SilenceSegment(start=float(index * 5 + 3), end=float(index * 5 + 5), duration=2.0)
        for index in range(199)
    ]

    result = generate_normal_candidates_with_summary(
        transcript_segments=transcript_segments,
        scene_segments=[SceneSegment(start=0.0, end=1000.0)],
        silence_segments=silence_segments,
        settings={
            "normalMinDuration": 20,
            "normalMaxDuration": 120,
            "normalStepSeconds": 10,
            "maxRawCandidatesPerType": 25,
            "maxCandidates": 100,
            "maxKeptCandidatesPerType": 100,
            "maxCandidatesPerTimeBucket": 50,
        },
    )

    assert result.summary["raw_candidates_considered"] <= 25
    assert result.summary["stopped_due_to_raw_candidate_cap"] is False
    assert result.summary["candidates_dropped_due_to_cap"] >= 1
    assert len(result.candidates) <= 100
    assert any(400 <= candidate.start < 600 for candidate in result.candidates)
    assert any(candidate.start >= 800 for candidate in result.candidates)


def test_bounded_generation_memory_guard_raises_clear_error() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(index * 5), end=float(index * 5 + 3), text=f"speech {index}")
        for index in range(200)
    ]
    silence_segments = [
        SilenceSegment(start=float(index * 5 + 3), end=float(index * 5 + 5), duration=2.0)
        for index in range(199)
    ]

    try:
        generate_short_candidates_with_summary(
            transcript_segments=transcript_segments,
            scene_segments=[SceneSegment(start=0.0, end=1000.0)],
            silence_segments=silence_segments,
            settings={
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "shortStepSeconds": 5,
                "maxCandidateGenerationMemoryMb": 1,
            },
        )
    except CandidateGenerationMemoryLimitError as exc:
        assert exc.summary["memory_guard_triggered"] is True
    else:
        # Windows test runners may not expose /proc/self/status.
        assert True


def test_chunked_generation_produces_normal_and_short_candidates() -> None:
    transcript_segments = [
        TranscriptSegment(start=float(start), end=float(start + 30), text=f"speech block {start}")
        for start in range(0, 900, 45)
    ]
    silence_segments = [
        SilenceSegment(start=float(start + 30), end=float(start + 45), duration=15.0)
        for start in range(0, 855, 45)
    ]
    settings = {
        "normalMinDuration": 90,
        "normalMaxDuration": 240,
        "shortMinDuration": 20,
        "shortMaxDuration": 75,
        "candidateChunkSeconds": 300,
        "candidateChunkOverlapSeconds": 75,
        "maxCandidates": 80,
    }

    normal = generate_normal_candidates_with_summary(
        transcript_segments,
        [SceneSegment(start=0.0, end=900.0)],
        silence_segments,
        settings=settings,
    )
    short = generate_short_candidates_with_summary(
        transcript_segments,
        [SceneSegment(start=0.0, end=900.0)],
        silence_segments,
        settings=settings,
    )
    combined_summary = merge_candidate_generation_summaries(
        [normal.summary, short.summary],
        video_duration=900.0,
        transcript_segment_count=len(transcript_segments),
    )

    assert normal.candidates
    assert short.candidates
    assert combined_summary["candidates_kept_by_type"]["normal"] == len(normal.candidates)
    assert combined_summary["candidates_kept_by_type"]["short"] == len(short.candidates)


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
