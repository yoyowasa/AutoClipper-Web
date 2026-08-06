from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.generate_heatmap_candidates import generate_heatmap_candidates_with_summary
from app.jobs.runner import _heatmap_summary_for_selection_mode
from app.video.heatmap import HeatmapSegment


def _transcript(duration: int = 240) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start=float(start),
            end=float(min(start + 20, duration)),
            text=f"complete spoken section {start}",
        )
        for start in range(0, duration, 20)
    ]


def test_heatmap_interval_candidates_use_ranked_json_seeds_and_duration_settings() -> None:
    segments = [
        HeatmapSegment(start_time=20.0, end_time=38.0, value=0.2),
        HeatmapSegment(start_time=150.0, end_time=168.0, value=1.0),
    ]

    result = generate_heatmap_candidates_with_summary(
        "normal",
        heatmap_segments=segments,
        transcript_segments=_transcript(),
        video_duration=240.0,
        requested_count=1,
        settings={
            "normalMinDuration": 90,
            "normalMaxDuration": 120,
            "normalStepSeconds": 30,
        },
    )

    assert result.candidates
    assert all(candidate.generation_source == "heatmap_interval" for candidate in result.candidates)
    assert all(90 <= candidate.duration <= 120 for candidate in result.candidates)
    best = max(result.candidates, key=lambda candidate: candidate.heatmap_direct_score or 0)
    assert best.start < 168
    assert best.end > 150
    assert best.heatmap_seed_start == 150.0
    assert best.heatmap_seed_end == 168.0
    assert best.heatmap_seed_value == 1.0
    assert best.heatmap_direct_score is not None
    assert result.summary["strategy"] == "heatmap_intervals"
    assert result.summary["positive_seed_count"] == 2
    assert result.summary["mode_fallback_used"] is False


def test_heatmap_interval_candidates_shift_at_media_edge_without_breaking_minimum() -> None:
    result = generate_heatmap_candidates_with_summary(
        "short",
        heatmap_segments=[HeatmapSegment(start_time=0.0, end_time=10.0, value=1.0)],
        transcript_segments=_transcript(60),
        video_duration=60.0,
        requested_count=1,
        settings={
            "shortMinDuration": 20,
            "shortMaxDuration": 30,
            "shortStepSeconds": 10,
        },
    )

    assert result.candidates
    assert min(candidate.start for candidate in result.candidates) == 0.0
    assert all(20 <= candidate.duration <= 30 for candidate in result.candidates)
    assert result.summary["edge_shifted_count"] > 0


def test_heatmap_interval_candidates_do_not_treat_zero_values_as_ranked_intervals() -> None:
    result = generate_heatmap_candidates_with_summary(
        "short",
        heatmap_segments=[HeatmapSegment(start_time=10.0, end_time=20.0, value=0.0)],
        transcript_segments=_transcript(60),
        video_duration=60.0,
        requested_count=1,
    )

    assert result.candidates == []
    assert result.summary["positive_seed_count"] == 0


def test_heatmap_interval_candidates_keep_separate_peaks_when_one_peak_is_dense() -> None:
    dense_peak = [
        HeatmapSegment(
            start_time=100.0 + index,
            end_time=101.0 + index,
            value=1.0 - (index * 0.005),
        )
        for index in range(16)
    ]
    segments = [
        *dense_peak,
        HeatmapSegment(start_time=600.0, end_time=610.0, value=0.9),
    ]

    result = generate_heatmap_candidates_with_summary(
        "normal",
        heatmap_segments=segments,
        transcript_segments=_transcript(800),
        video_duration=800.0,
        requested_count=2,
        settings={
            "normalMinDuration": 90,
            "normalMaxDuration": 90,
            "normalStepSeconds": 30,
        },
    )

    assert any(candidate.heatmap_seed_start == 600.0 for candidate in result.candidates)
    assert result.summary["seed_time_bucket_count"] == 2


def test_heatmap_interval_mode_rejects_positive_segments_outside_video() -> None:
    summary, should_fail = _heatmap_summary_for_selection_mode(
        {"status": "applied", "fallback_reason": None},
        [HeatmapSegment(start_time=300.0, end_time=310.0, value=1.0)],
        {
            "heatmapIntervalMode": True,
            "normalClipCount": 1,
            "normalClipTimeRanges": [{"startSeconds": 10, "endSeconds": 100}],
            "shortCount": 1,
            "shortClipTimeRanges": [],
        },
        video_duration=240.0,
    )

    assert should_fail is True
    assert summary["interval_mode_applied"] is False
    assert summary["positive_segment_count"] == 1
    assert summary["usable_positive_segment_count"] == 0
    assert summary["interval_mode_unavailable_reason"] == (
        "heatmap_has_no_positive_segments_in_video"
    )
