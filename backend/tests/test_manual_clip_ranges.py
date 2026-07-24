import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.manual_ranges import (
    MANUAL_SELECTION_REASON,
    automatic_selection_settings,
    build_manual_candidates,
    merge_manual_candidates_into_selection,
    validate_manual_ranges_for_duration,
)
from app.candidates.select_candidates import CandidateSelection
from app.schemas import ClipTimeRange, JobSettings


def test_job_settings_accepts_complete_manual_ranges_and_disables_unused_openai() -> None:
    settings = JobSettings.model_validate(
        {
            "normalClipCount": 0,
            "shortCount": 2,
            "shortClipTimeRanges": [
                {"startSeconds": 65, "endSeconds": 82},
                {"startSeconds": 120.5, "endSeconds": 145},
            ],
            "useOpenAIScoring": True,
        }
    )

    assert len(settings.short_clip_time_ranges) == 2
    assert settings.use_openai_scoring is False


def test_automatic_settings_keep_recommendations_only_for_unlocked_output_type() -> None:
    mixed = automatic_selection_settings(
        {
            "normalClipCount": 1,
            "shortCount": 2,
            "useOpenAIScoring": True,
        },
        manual_normal=True,
        manual_short=False,
    )
    manual_only = automatic_selection_settings(
        {
            "normalClipCount": 0,
            "shortCount": 2,
            "useOpenAIScoring": True,
        },
        manual_normal=False,
        manual_short=True,
    )

    assert mixed["normalClipCount"] == 0
    assert mixed["shortCount"] == 2
    assert mixed["useOpenAIScoring"] is True
    assert manual_only["useOpenAIScoring"] is False
    assert manual_only["ensureSelectedOpenAIScored"] is False


@pytest.mark.parametrize(
    "ranges",
    [
        [{"startSeconds": 10, "endSeconds": None}],
        [{"startSeconds": 10, "endSeconds": 10}],
        [
            {"startSeconds": 10, "endSeconds": 20},
            {"startSeconds": 10, "endSeconds": 20},
        ],
    ],
)
def test_job_settings_rejects_incomplete_invalid_or_duplicate_manual_ranges(
    ranges: list[dict[str, float | None]],
) -> None:
    with pytest.raises(ValidationError):
        JobSettings.model_validate(
            {
                "normalClipCount": 0,
                "shortCount": len(ranges),
                "shortClipTimeRanges": ranges,
            }
        )


def test_build_manual_candidates_preserves_exact_boundaries_and_transcript() -> None:
    result = build_manual_candidates(
        "short",
        [
            ClipTimeRange(startSeconds=10, endSeconds=25),
            ClipTimeRange(startSeconds=30, endSeconds=45),
        ],
        [
            TranscriptSegment(start=5, end=14, text="前半"),
            TranscriptSegment(start=14, end=22, text="対象字幕"),
            TranscriptSegment(start=32, end=40, text="二本目"),
        ],
    )

    assert [(candidate.start, candidate.end) for candidate in result.candidates] == [
        (10.0, 25.0),
        (30.0, 45.0),
    ]
    assert result.candidates[0].transcript_text == "前半 対象字幕"
    assert result.candidates[0].selection_reason == MANUAL_SELECTION_REASON
    assert result.candidates[0].boundary_refinement_reason == "manual_time_range_locked"
    assert result.summary["strategy"] == "manual_time_ranges"


def test_validate_manual_ranges_rejects_end_beyond_video() -> None:
    with pytest.raises(ValueError, match="beyond video duration"):
        validate_manual_ranges_for_duration(
            {
                "shortClipTimeRanges": [
                    {"startSeconds": 40, "endSeconds": 61},
                ]
            },
            video_duration=60,
        )


def test_merge_manual_candidates_replaces_only_the_manual_output_type() -> None:
    manual = build_manual_candidates(
        "short",
        [ClipTimeRange(startSeconds=10, endSeconds=25)],
        [TranscriptSegment(start=10, end=25, text="指定字幕")],
    ).candidates
    automatic = CandidateSelection(
        normalClips=[],
        shorts=[],
        requestedNormalCount=1,
        requestedShortCount=0,
    )

    merged = merge_manual_candidates_into_selection(
        automatic,
        settings={"normalClipCount": 1, "shortCount": 1},
        manual_normal_candidates=[],
        manual_short_candidates=manual,
    )

    assert merged.normal_clips == []
    assert merged.shorts == manual
    assert merged.requested_normal_count == 1
    assert merged.requested_short_count == 1
    assert merged.unfilled_requested_counts["short"] == 0
