from app.jobs.runner import _heatmap_summary_for_selection_mode
from app.video.heatmap import HeatmapSegment


def _automatic_settings() -> dict[str, object]:
    return {
        "heatmapIntervalMode": True,
        "normalClipCount": 1,
        "normalClipTimeRanges": [],
        "shortCount": 1,
        "shortClipTimeRanges": [],
    }


def test_heatmap_reference_is_available_without_becoming_a_boundary_source() -> None:
    summary, should_fail = _heatmap_summary_for_selection_mode(
        {"status": "applied", "fallback_reason": None},
        [HeatmapSegment(start_time=150.0, end_time=168.0, value=1.0)],
        _automatic_settings(),
        video_duration=240.0,
    )

    assert should_fail is False
    assert summary["interval_mode_requested"] is True
    assert summary["interval_mode_applied"] is True
    assert summary["selection_behavior"] == "content_with_heatmap_reference"
    assert summary["usable_positive_segment_count"] == 1


def test_heatmap_reference_outside_video_falls_back_to_content_candidates() -> None:
    summary, should_fail = _heatmap_summary_for_selection_mode(
        {"status": "applied", "fallback_reason": None},
        [HeatmapSegment(start_time=300.0, end_time=310.0, value=1.0)],
        _automatic_settings(),
        video_duration=240.0,
    )

    assert should_fail is False
    assert summary["interval_mode_requested"] is True
    assert summary["interval_mode_applied"] is False
    assert summary["positive_segment_count"] == 1
    assert summary["usable_positive_segment_count"] == 0
    assert summary["selection_behavior"] == "content_only"
    assert summary["interval_mode_unavailable_reason"] == (
        "heatmap_has_no_positive_segments_in_video"
    )
