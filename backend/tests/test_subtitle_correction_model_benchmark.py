import argparse
import json
from pathlib import Path

import pytest

from app.audio.benchmark_subtitle_correction import (
    BenchmarkProfile,
    apply_manual_review_to_report,
    apply_aliases,
    build_baseline_comparisons,
    estimated_actual_cost_usd,
    load_target_indices,
    manual_review_metrics,
    parse_profile,
    render_markdown,
    resolve_lowest_reasoning_from_probe,
    timestamp_preservation,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment


def test_profile_parser_supports_default_none_and_lowest() -> None:
    assert parse_profile("gpt-5.5:default") == BenchmarkProfile("gpt-5.5", "default")
    assert parse_profile("gpt-5.4-mini:none") == BenchmarkProfile("gpt-5.4-mini", "none")
    assert parse_profile("gpt-5-mini:lowest") == BenchmarkProfile("gpt-5-mini", "lowest")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_profile("gpt-5-mini:auto")


def test_cost_estimate_uses_cached_input_and_reasoning_in_output() -> None:
    summary = {
        "input_tokens": 1_000_000,
        "cached_tokens": 200_000,
        "output_tokens": 100_000,
        "reasoning_tokens": 60_000,
    }

    assert estimated_actual_cost_usd(summary, "gpt-5.4-mini") == pytest.approx(1.065)
    assert estimated_actual_cost_usd(summary, "unknown") is None


def test_baseline_comparison_reports_usage_and_change_overlap() -> None:
    runs = [
        {
            "profile": "gpt-5.5:default",
            "summary": {"input_tokens": 100, "output_tokens": 300, "processing_seconds": 20},
            "estimated_actual_cost_usd": 1.0,
            "changes": [{"index": 1}, {"index": 2}, {"index": 3}],
        },
        {
            "profile": "gpt-5.5:none",
            "summary": {"input_tokens": 100, "output_tokens": 100, "processing_seconds": 10},
            "estimated_actual_cost_usd": 0.4,
            "changes": [{"index": 2}, {"index": 4}],
        },
    ]

    comparison = build_baseline_comparisons(runs)[0]

    assert comparison["shared_changed_indices"] == 1
    assert comparison["baseline_only_changed_indices"] == 2
    assert comparison["candidate_only_changed_indices"] == 1
    assert comparison["output_token_reduction_percent"] == pytest.approx(66.666667)
    assert comparison["total_token_reduction_percent"] == 50
    assert comparison["cost_reduction_percent"] == 60
    assert comparison["processing_time_reduction_percent"] == 50


def test_targets_and_probe_resolution_are_loaded_from_artifacts(tmp_path: Path) -> None:
    targets_path = tmp_path / "targets.json"
    probe_path = tmp_path / "probe.json"
    targets_path.write_text(json.dumps({"target_indices": [2, 0, 2]}), encoding="utf-8")
    probe_path.write_text(
        json.dumps({"lowest_reasoning_resolutions": {"gpt-5-mini": "minimal"}}),
        encoding="utf-8",
    )

    assert load_target_indices(targets_path, segment_count=3) == [0, 2]
    assert resolve_lowest_reasoning_from_probe(probe_path, "gpt-5-mini") == "minimal"


def test_alias_review_and_timestamp_metrics_are_explicit() -> None:
    source = [TranscriptSegment(start=0.0, end=1.0, text="オープンAI", confidence=0.8)]
    same = [TranscriptSegment(start=0.0, end=1.0, text="OpenAI", confidence=0.8)]
    changed_time = [TranscriptSegment(start=0.1, end=1.0, text="OpenAI", confidence=0.8)]
    review = {
        "gpt-5_5_none": {
            "useful_corrections": [0],
            "harmful_corrections": [],
        }
    }

    assert apply_aliases("オープンAIです", [("オープンAI", "OpenAI")]) == "OpenAIです"
    assert timestamp_preservation(source, same)["timestamps_preserved"] is True
    assert timestamp_preservation(source, changed_time)["timestamp_mismatch_count"] == 1
    metrics = manual_review_metrics("gpt-5_5_none", review)
    assert metrics["reviewed"] is True
    assert metrics["useful_corrections"] == 1
    assert metrics["missed_corrections"] == 0


def test_manual_review_can_be_applied_without_rerunning_api() -> None:
    report = {
        "phase": "benchmark",
        "runs": [
            {
                "profile_label": "gpt-5_5_none",
                "quality": {"manual_review": {"reviewed": False}},
            }
        ],
    }
    review = {
        "gpt-5_5_none": {
            "useful_corrections": [2, 14],
            "missed_corrections": [8],
            "harmful_corrections": [],
        }
    }

    updated = apply_manual_review_to_report(report, review)

    assert updated["manual_review_applied"] is True
    assert updated["runs"][0]["quality"]["manual_review"]["useful_corrections"] == 2
    assert report["runs"][0]["quality"]["manual_review"]["reviewed"] is False


def test_probe_markdown_separates_reasoning_and_visible_tokens() -> None:
    report = {
        "phase": "probe",
        "runs": [
            {
                "requested_profile": "gpt-5.5:none",
                "attempts": [
                    {
                        "reasoning_effort": "none",
                        "success": True,
                        "summary": {
                            "api_call_count": 1,
                            "input_tokens": 100,
                            "output_tokens": 30,
                            "reasoning_tokens": 20,
                            "visible_output_tokens": 10,
                        },
                    }
                ],
            }
        ],
    }

    markdown = render_markdown(report)

    assert "gpt-5.5:none" in markdown
    assert "| 100 | 30 | 20 | 10 |" in markdown
