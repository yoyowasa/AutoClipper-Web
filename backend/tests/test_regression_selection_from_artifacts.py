from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "regression_selection_from_artifacts.py"
SPEC = importlib.util.spec_from_file_location("regression_selection_from_artifacts", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
regression = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = regression
SPEC.loader.exec_module(regression)


def _candidate(
    candidate_id: str,
    candidate_type: str,
    start: float,
    duration: float,
    *,
    text: str = "質問です。例えばこうです。だから結論です。",
    topic_key: str | None = None,
):
    return regression.Candidate(
        id=candidate_id,
        type=candidate_type,
        start=start,
        end=start + duration,
        duration=duration,
        transcript_text=text,
        topic_key=topic_key,
    )


def test_duration_distribution_reports_bands_and_legacy_convergence() -> None:
    candidates = [
        _candidate("n1", "normal", 0.0, 150.0),
        _candidate("n2", "normal", 200.0, 150.4),
        _candidate("n3", "normal", 400.0, 220.0),
        _candidate("n4", "normal", 700.0, 420.0),
    ]

    result = regression._duration_distribution(candidates, regression.NORMAL_DURATION_BANDS)

    assert result["durationBandCounts"] == {"90-180": 2, "180-300": 1, "300-600": 1}
    assert result["missingDurationBands"] == []
    assert result["legacyTargetNearCount"] == 2
    assert result["legacyTargetNearShare"] == 0.5


def test_selection_summary_reports_topic_diversity_and_thank_density() -> None:
    selection = regression.CandidateSelection(
        normalClips=[
            _candidate(
                "n1",
                "normal",
                100.0,
                120.0,
                text="ありがとう。美術とは何かを説明します。",
                topic_key="topic-1",
            ),
            _candidate("n2", "normal", 400.0, 180.0, topic_key="topic-2"),
        ],
        requestedNormalCount=2,
        requestedShortCount=0,
    )

    result = regression._selection_summary(selection)

    assert result["normalTopicKeysPresent"] is True
    assert result["normalTopicKeysDistinct"] is True
    assert result["normalPairwiseOverlap"] == {
        "pairs": [
            {
                "leftId": "n1",
                "rightId": "n2",
                "overlapSeconds": 0.0,
                "overlapRatioOfShorter": 0.0,
            }
        ],
        "maxOverlapRatioOfShorter": 0.0,
    }
    assert result["normal"][0]["thankCount"] == 1
    assert result["normal"][0]["thankPerMinute"] == 0.5
    assert result["normalDurationSpreadSeconds"] == 60.0


def test_expected_range_summary_requires_minimum_overlap() -> None:
    candidates = [_candidate("n1", "normal", 100.0, 120.0, topic_key="topic-1")]
    expected = regression.ExpectedRange(label="art", start=180.0, end=300.0)

    result = regression._expected_range_summary(candidates, [expected], 30.0)

    assert result["hitCount"] == 1
    assert result["ranges"][0]["overlaps"] == [
        {"candidateId": "n1", "overlapSeconds": 40.0}
    ]


def test_output_path_cannot_be_inside_source_artifacts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "job_test"
    artifact_dir.mkdir()

    with pytest.raises(ValueError, match="inside the source artifact"):
        regression._validate_output_path(artifact_dir / "report.json", artifact_dir)

    assert regression._validate_output_path(tmp_path / "report.json", artifact_dir) == (
        tmp_path / "report.json"
    ).resolve()


@pytest.mark.parametrize(
    ("raw", "label", "start", "end"),
    [
        ("art=2034.4:2517.8", "art", 2034.4, 2517.8),
        ("2611.3:2884.5", "expected", 2611.3, 2884.5),
    ],
)
def test_parse_expected_range(raw: str, label: str, start: float, end: float) -> None:
    parsed = regression.parse_expected_range(raw)

    assert parsed.label == label
    assert parsed.start == start
    assert parsed.end == end


def test_regression_fails_when_requested_types_select_nothing() -> None:
    candidate_metrics = {
        candidate_type: {
            "missingDurationBands": [],
            "dominantRoundedSecondShare": 0.1,
        }
        for candidate_type in ("normal", "short")
    }
    selection_summary = {
        "normal": [],
        "normalTopicKeysPresent": True,
        "normalTopicKeysDistinct": True,
        "normalPairwiseOverlap": {"maxOverlapRatioOfShorter": 0.0},
        "selectedBelowThresholdBackfillCount": 0,
        "requestedCounts": {"normal": 2, "short": 5},
        "selectedCounts": {"normal": 0, "short": 0},
    }

    result = regression._regression_checks(
        candidate_metrics=candidate_metrics,
        selection_summary=selection_summary,
        expected_range_summary={"ranges": []},
        max_duration_mode_share=0.4,
        max_normal_thank_per_minute=2.0,
        max_normal_selected_overlap_ratio=0.5,
        source_artifact_hashes_unchanged=True,
    )

    assert result["checks"]["normalSelectedWhenRequested"] is False
    assert result["checks"]["shortSelectedWhenRequested"] is False
    assert result["passed"] is False
