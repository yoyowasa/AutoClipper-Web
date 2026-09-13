import pytest

from app.candidates.merge_boundaries import Candidate
from app.candidates.short_diversity import (
    ShortDiversityMetadata,
    ShortDiversitySettings,
    select_diverse_shorts,
)


def _candidate(
    candidate_id: str,
    start: float,
    end: float,
    text: str,
    *,
    candidate_type: str = "short",
    refined_start: float | None = None,
    refined_end: float | None = None,
    risk_flags: list[str] | None = None,
    hook_text: str | None = None,
    hook_scene_start: float | None = None,
    hook_scene_end: float | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,
        start=start,
        end=end,
        duration=end - start,
        transcript_text=text,
        refined_start=refined_start,
        refined_end=refined_end,
        risk_flags=risk_flags or [],
        hook_text=hook_text,
        hook_scene_start=hook_scene_start,
        hook_scene_end=hook_scene_end,
    )


def test_rejects_more_than_one_second_overlap_and_backfills_in_rank_order() -> None:
    first = _candidate("short_1", 0, 20, "最初の見せ場です")
    shifted_duplicate = _candidate("short_2", 18.5, 38.5, "別の字幕です")
    replacement = _candidate("short_3", 50, 70, "次の独立した見せ場です")

    result = select_diverse_shorts(
        [first, shifted_duplicate, replacement],
        requested_count=2,
    )

    assert [item.id for item in result.selected] == ["short_1", "short_3"]
    assert len(result.rejected) == 1
    assert result.rejected[0].candidate_id == "short_2"
    assert result.rejected[0].duplicate_of == "short_1"
    assert result.rejected[0].reasons == ("time_overlap_over_limit",)
    assert result.unfilled_count == 0


def test_allows_exactly_one_second_overlap() -> None:
    result = select_diverse_shorts(
        [
            _candidate("short_1", 0, 20, "最初の見せ場です"),
            _candidate("short_2", 19, 39, "別の見せ場です"),
        ],
        requested_count=2,
    )

    assert [item.id for item in result.selected] == ["short_1", "short_2"]
    assert result.rejected == ()


def test_uses_refined_range_for_final_overlap_check() -> None:
    result = select_diverse_shorts(
        [
            _candidate(
                "short_1",
                0,
                20,
                "最初の見せ場です",
                refined_start=0,
                refined_end=22,
            ),
            _candidate(
                "short_2",
                21,
                41,
                "別の見せ場です",
                refined_start=20.5,
                refined_end=41,
            ),
        ],
        requested_count=2,
    )

    assert [item.id for item in result.selected] == ["short_1"]
    assert result.rejected[0].overlap_seconds == 1.5


def test_ignores_normal_candidates_even_when_they_overlap() -> None:
    short = _candidate("short_1", 10, 30, "同じ字幕", candidate_type="short")
    normal = _candidate("normal_1", 0, 100, "同じ字幕", candidate_type="normal")

    result = select_diverse_shorts([normal, short], requested_count=1)

    assert result.selected == (short,)
    assert result.rejected == ()


def test_rejects_high_text_similarity_and_backfills() -> None:
    first = _candidate("short_1", 0, 20, "これは本当に驚いた出来事でした")
    same_text = _candidate("short_2", 40, 60, "これは本当に驚いた出来事でした。")
    replacement = _candidate("short_3", 80, 100, "まったく別の話題へ移ります")

    result = select_diverse_shorts(
        [first, same_text, replacement],
        requested_count=2,
    )

    assert [item.id for item in result.selected] == ["short_1", "short_3"]
    assert "high_text_similarity" in result.rejected[0].reasons


def test_rejects_shared_evidence_from_explicit_metadata() -> None:
    candidates = [
        _candidate("short_1", 0, 20, "最初の説明"),
        _candidate("short_2", 40, 60, "別表現の説明"),
    ]
    metadata = {
        "short_1": ShortDiversityMetadata(
            evidence_segment_ids=("seg_1", "seg_2"),
        ),
        "short_2": {"evidenceSegmentIds": ["seg_1", "seg_2", "seg_3"]},
    }

    result = select_diverse_shorts(
        candidates,
        requested_count=2,
        metadata_by_candidate_id=metadata,
    )

    assert [item.id for item in result.selected] == ["short_1"]
    assert "high_evidence_similarity" in result.rejected[0].reasons
    assert result.rejected[0].evidence_similarity == 1.0


@pytest.mark.parametrize("metadata_key", ["momentKey", "parentGroup"])
def test_rejects_same_explicit_moment_or_parent_group(metadata_key: str) -> None:
    candidates = [
        _candidate("short_1", 0, 20, "最初の説明"),
        _candidate("short_2", 40, 60, "別表現の説明"),
    ]
    metadata = {
        "short_1": {metadata_key: "topic-A"},
        "short_2": {metadata_key: "TOPIC-a"},
    }

    result = select_diverse_shorts(
        candidates,
        requested_count=2,
        metadata_by_candidate_id=metadata,
    )

    assert [item.id for item in result.selected] == ["short_1"]
    expected_reason = "same_moment_key" if metadata_key == "momentKey" else "same_parent_group"
    assert expected_reason in result.rejected[0].reasons


def test_rejects_substantially_overlapping_parent_ranges() -> None:
    candidates = [
        _candidate("short_1", 20, 40, "最初の説明"),
        _candidate("short_2", 70, 90, "別表現の説明"),
        _candidate("short_3", 140, 160, "独立した説明"),
    ]
    metadata = {
        "short_1": {"parentStart": 0, "parentEnd": 100},
        "short_2": {"parentStart": 10, "parentEnd": 110},
        "short_3": {"parentStart": 120, "parentEnd": 180},
    }

    result = select_diverse_shorts(
        candidates,
        requested_count=2,
        metadata_by_candidate_id=metadata,
    )

    assert [item.id for item in result.selected] == ["short_1", "short_3"]
    assert "high_parent_overlap" in result.rejected[0].reasons
    assert result.rejected[0].parent_overlap_ratio == 0.9


def test_heatmap_segment_uniqueness_is_only_enforced_when_enabled() -> None:
    candidates = [
        _candidate("short_1", 0, 20, "最初の説明").model_copy(update={"heatmap_segment_ids": ["heat_1"]}),
        _candidate("short_2", 40, 60, "別表現の説明").model_copy(update={"heatmap_segment_ids": ["heat_1"]}),
    ]

    disabled = select_diverse_shorts(
        candidates,
        requested_count=2,
    )
    enabled = select_diverse_shorts(
        candidates,
        requested_count=2,
        settings=ShortDiversitySettings(enforce_heatmap_segment_uniqueness=True),
    )

    assert [item.id for item in disabled.selected] == ["short_1", "short_2"]
    assert [item.id for item in enabled.selected] == ["short_1"]
    assert "same_heatmap_segment" in enabled.rejected[0].reasons


def test_reads_namespaced_metadata_from_risk_flags() -> None:
    first = _candidate(
        "short_1",
        0,
        20,
        "最初の説明",
        risk_flags=["moment_key:episode-7", "evidence_segment_id:seg_1"],
    )
    duplicate = _candidate(
        "short_2",
        40,
        60,
        "別表現の説明",
        risk_flags=["momentKey:EPISODE-7", "evidenceSegmentId:seg_1"],
    )

    result = select_diverse_shorts([first, duplicate], requested_count=2)

    assert [item.id for item in result.selected] == ["short_1"]
    assert set(result.rejected[0].reasons) == {
        "high_evidence_similarity",
        "same_moment_key",
    }


def test_does_not_compare_hook_duplicate_inside_distinct_shorts() -> None:
    result = select_diverse_shorts(
        [
            _candidate(
                "short_1",
                0,
                20,
                "最初の独立した話題",
                hook_text="同じフック",
                hook_scene_start=0,
                hook_scene_end=2,
            ),
            _candidate(
                "short_2",
                40,
                60,
                "二番目の異なる話題",
                hook_text="同じフック",
                hook_scene_start=40,
                hook_scene_end=42,
            ),
        ],
        requested_count=2,
    )

    assert [item.id for item in result.selected] == ["short_1", "short_2"]
    assert result.rejected == ()


def test_reports_unfilled_count_without_padding_with_duplicates() -> None:
    candidates = [
        _candidate("short_1", 0, 20, "同じ話題です"),
        _candidate("short_2", 40, 60, "同じ話題です"),
        _candidate("normal_1", 80, 180, "通常動画", candidate_type="normal"),
    ]

    result = select_diverse_shorts(candidates, requested_count=3)

    assert [item.id for item in result.selected] == ["short_1"]
    assert result.unfilled_count == 2


def test_validates_settings_and_requested_count() -> None:
    with pytest.raises(ValueError, match="requested_count"):
        select_diverse_shorts([], requested_count=-1)
    with pytest.raises(ValueError, match="max_overlap_seconds"):
        ShortDiversitySettings(max_overlap_seconds=-0.1)
