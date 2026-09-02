from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import AudioFeatures
from app.candidates.manual_ranges import MANUAL_SELECTION_REASON
from app.candidates.merge_boundaries import Candidate
from app.jobs.runner import _automatic_selection_with_diverse_refined_shorts


def _candidate(
    candidate_id: str,
    start: float,
    end: float,
    text: str,
    *,
    candidate_type: str = "short",
    score: float = 90,
    selection_reason: str | None = None,
    heatmap_segment_ids: list[str] | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,
        start=start,
        end=end,
        duration=end - start,
        transcript_text=text,
        final_score=score,
        rule_score=score,
        should_use=True,
        selection_reason=selection_reason,
        heatmap_segment_ids=heatmap_segment_ids,
    )


def _audio(duration: float = 200) -> AudioFeatures:
    return AudioFeatures(
        duration=duration,
        silence_ratio=0,
        speech_density=1,
        volume_peak=0.5,
        silent_seconds=0,
        speech_seconds=duration,
    )


def _settings(**overrides: object) -> dict[str, object]:
    settings: dict[str, object] = {
        "normalClipCount": 0,
        "shortCount": 2,
        "selectionPolicy": "fill_requested",
        "shortMinDuration": 20,
        "shortMaxDuration": 75,
        "minFinalScore": 0,
        "rejectIncompleteSentence": False,
        "enableBoundaryRefinement": False,
        "heatmapIntervalMode": False,
        "crossTypeOverlapDedupe": False,
    }
    settings.update(overrides)
    return settings


def test_legacy_selection_rechecks_after_boundary_refinement_and_backfills() -> None:
    candidates = [
        _candidate("short_1", 0, 20, "一番目の独立した説明です。", score=100),
        _candidate("short_2", 20.5, 40.5, "二番目の独立した説明です。", score=95),
        _candidate("short_3", 41, 61, "三番目の別場面です。", score=90),
    ]
    transcript = [
        TranscriptSegment(start=0, end=19, text="一番目の独立した説明です。"),
        TranscriptSegment(start=19, end=22, text="境界をまたぐ短い発言です。"),
        TranscriptSegment(start=22, end=40.5, text="二番目の独立した説明です。"),
        TranscriptSegment(start=41, end=61, text="三番目の別場面です。"),
    ]

    selection, _, diversity = _automatic_selection_with_diverse_refined_shorts(
        candidates,
        transcript_segments=transcript,
        silence_segments=[],
        scene_segments=[],
        settings=_settings(enableBoundaryRefinement=True),
        timeline_duration=100,
        audio_features=_audio(100),
    )

    assert [candidate.id for candidate in selection.shorts] == ["short_1", "short_3"]
    assert [item.candidate_id for item in diversity.rejected] == ["short_2"]
    assert "time_overlap_over_limit" in diversity.rejected[0].reasons
    assert diversity.rejected[0].overlap_seconds > 1


def test_legacy_fill_requested_does_not_pad_with_duplicate_shorts() -> None:
    candidates = [
        _candidate("short_1", 0, 20, "同じ場面の発言です。", score=100),
        _candidate("short_2", 0.5, 20.5, "同じ場面の発言です。", score=95),
    ]

    selection, _, diversity = _automatic_selection_with_diverse_refined_shorts(
        candidates,
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings=_settings(),
        timeline_duration=30,
        audio_features=_audio(30),
    )

    assert [candidate.id for candidate in selection.shorts] == ["short_1"]
    assert selection.unfilled_requested_counts["short"] == 1
    assert selection.unfilled_reason_counts["short"]["insufficient_distinct_moments"] == 1
    assert diversity.unfilled_count == 1


def test_manual_short_is_not_included_in_automatic_diversity_selection() -> None:
    manual = _candidate(
        "manual_short",
        0,
        20,
        "手動指定した場面です。",
        score=100,
        selection_reason=MANUAL_SELECTION_REASON,
    )
    automatic = _candidate(
        "automatic_short",
        40,
        60,
        "自動選定した場面です。",
        score=90,
    )

    selection, refined, _ = _automatic_selection_with_diverse_refined_shorts(
        [manual, automatic],
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings=_settings(shortCount=1),
        timeline_duration=70,
        audio_features=_audio(70),
    )

    assert [candidate.id for candidate in selection.shorts] == ["automatic_short"]
    assert [candidate.id for candidate in refined] == ["automatic_short"]


def test_cross_type_overlap_setting_remains_enforced_after_refinement() -> None:
    candidates = [
        _candidate(
            "normal_1",
            0,
            100,
            "通常動画の場面です。",
            candidate_type="normal",
            score=100,
        ),
        _candidate("short_overlap", 0, 20, "通常動画と重なる場面です。", score=99),
        _candidate("short_distinct", 120, 140, "別のショート場面です。", score=90),
    ]

    selection, _, _ = _automatic_selection_with_diverse_refined_shorts(
        candidates,
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings=_settings(
            normalClipCount=1,
            shortCount=1,
            crossTypeOverlapDedupe=True,
        ),
        timeline_duration=150,
        audio_features=_audio(150),
    )

    assert [candidate.id for candidate in selection.normal_clips] == ["normal_1"]
    assert [candidate.id for candidate in selection.shorts] == ["short_distinct"]


def test_json_reference_does_not_make_same_heatmap_segment_a_duplicate() -> None:
    candidates = [
        _candidate(
            "short_1",
            0,
            20,
            "一番目の場面です。",
            score=100,
            heatmap_segment_ids=["heat_1"],
        ),
        _candidate(
            "short_2",
            30,
            50,
            "二番目の表現です。",
            score=95,
            heatmap_segment_ids=["heat_1"],
        ),
        _candidate(
            "short_3",
            49,
            69,
            "別の人気場面です。",
            score=90,
            heatmap_segment_ids=["heat_2"],
        ),
    ]

    selection, _, diversity = _automatic_selection_with_diverse_refined_shorts(
        candidates,
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings=_settings(heatmapIntervalMode=True),
        timeline_duration=80,
        audio_features=_audio(80),
    )

    assert [candidate.id for candidate in selection.shorts] == ["short_1", "short_2"]
    assert all(
        "same_heatmap_segment" not in rejection.reasons
        for rejection in diversity.rejected
    )
