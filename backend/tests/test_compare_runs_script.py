import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compare_runs  # noqa: E402
import e2e_compare_quality  # noqa: E402


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_job_artifacts(
    root: Path,
    job_id: str,
    *,
    selected: dict[str, object],
    selected_summary: dict[str, object],
    candidate_summary: dict[str, object] | None = None,
    openai_summary: dict[str, object] | None = None,
    transcript_summary: dict[str, object] | None = None,
    render_failures: list[dict[str, object]] | None = None,
) -> Path:
    output_dir = root / "storage" / "outputs" / job_id
    write_json(output_dir / "selected_clips.json", selected)
    write_json(output_dir / "selected_clips_summary.json", selected_summary)
    write_json(output_dir / "candidate_summary.json", candidate_summary or {})
    write_json(output_dir / "rejection_summary.json", {"render_failure_count": len(render_failures or [])})
    write_json(output_dir / "render_failures.json", render_failures or [])
    if openai_summary is not None:
        write_json(output_dir / "openai_scoring_summary.json", openai_summary)
    if transcript_summary is not None:
        write_json(output_dir / "transcript_summary.json", transcript_summary)
    return output_dir


def test_compare_runs_builds_metrics_and_writes_reports(tmp_path: Path) -> None:
    low_selected = {
        "normalClips": [
            {
                "id": "low_normal_1",
                "type": "normal",
                "start": 0.0,
                "end": 100.0,
                "duration": 100.0,
                "rule_score": 62.0,
                "final_score": 60.0,
                "title": "Low normal",
                "selection_reason": "above_quality_threshold",
                "below_quality_threshold": False,
            }
        ],
        "shorts": [
            {
                "id": "low_short_1",
                "type": "short",
                "start": 200.0,
                "end": 250.0,
                "duration": 50.0,
                "rule_score": 50.0,
                "final_score": 50.0,
                "selection_reason": "backfill_below_quality_threshold",
                "below_quality_threshold": True,
            }
        ],
    }
    high_selected = {
        "normalClips": [
            {
                "id": "high_normal_1",
                "type": "normal",
                "start": 5.0,
                "end": 105.0,
                "duration": 100.0,
                "rule_score": 70.0,
                "ai_score": 80.0,
                "final_score": 80.0,
                "title": "High normal",
                "overlay_title": "AI normal",
                "selection_reason": "above_quality_threshold",
                "below_quality_threshold": False,
                "used_ai_score": True,
                "openai_scored": True,
                "openai_fallback_used": False,
                "openai_score_source": "finalist_on_demand",
            }
        ],
        "shorts": [
            {
                "id": "high_short_1",
                "type": "short",
                "start": 500.0,
                "end": 550.0,
                "duration": 50.0,
                "rule_score": 75.0,
                "final_score": 65.0,
                "title": "High fallback short",
                "selection_reason": "above_quality_threshold",
                "below_quality_threshold": False,
                "used_ai_score": False,
                "openai_scored": False,
                "openai_fallback_used": True,
                "openai_score_source": "fallback_rule_score",
            }
        ],
    }
    write_job_artifacts(
        tmp_path,
        "job_low",
        selected=low_selected,
        selected_summary={
            "selected_normal_count": 1,
            "selected_short_count": 1,
            "requested_normal_count": 1,
            "requested_short_count": 1,
        },
        candidate_summary={"total_candidates": 20},
        transcript_summary={"segment_count": 10, "total_text_length": 400},
    )
    write_job_artifacts(
        tmp_path,
        "job_high",
        selected=high_selected,
        selected_summary={
            "selected_normal_count": 1,
            "selected_short_count": 1,
            "requested_normal_count": 1,
            "requested_short_count": 1,
        },
        candidate_summary={"total_candidates": 20},
        openai_summary={
            "model": "gpt-test",
            "candidate_limit": 20,
            "finalist_scoring_limit": 3,
            "candidates_sent_preselection": 2,
            "candidates_sent_as_finalists": 2,
            "candidates_sent_to_openai": 4,
            "successful_scores": 4,
            "failed_scores": 0,
            "fallback_scores": 1,
            "selected_ai_score_count": 1,
            "selected_fallback_score_count": 1,
            "selected_not_scored_count": 0,
        },
        transcript_summary={"segment_count": 10, "total_text_length": 400},
    )

    report = compare_runs.build_comparison_report("job_low", "job_high", root=tmp_path)

    assert report["summary_metrics"]["same_selected_clips_count"] == 1
    assert report["summary_metrics"]["different_selected_clips_count"] == 1
    assert report["summary_metrics"]["exact_selected_clip_id_match_count"] == 0
    assert report["summary_metrics"]["average_score_difference"] == 20.0
    assert report["summary_metrics"]["high_quality_clips_using_ai_score"] == 1
    assert report["summary_metrics"]["high_quality_clips_using_fallback"] == 1
    assert report["summary_metrics"]["high_quality_clips_not_scored"] == 0
    assert report["summary_metrics"]["low_cost_backfill_count"] == 1
    assert report["summary_metrics"]["high_quality_count_fulfillment"]["normal"]["fulfilled"] is True
    assert report["selected_clip_comparisons"][0]["same_time_range"] is True
    assert report["selected_clip_comparisons"][1]["same_time_range"] is False

    paths = compare_runs.output_paths(
        low_cost_job_id="job_low",
        high_quality_job_id="job_high",
        output=tmp_path / "reports",
        output_format="both",
        root=tmp_path,
    )
    written = compare_runs.write_report(report, paths)
    assert paths.json_path in written
    assert paths.markdown_path in written
    assert paths.json_path is not None
    assert paths.markdown_path is not None
    assert json.loads(paths.json_path.read_text(encoding="utf-8"))["summary_metrics"]["same_selected_clips_count"] == 1
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "# AutoClipper Run Comparison" in markdown
    assert "high_normal_1" in markdown
    assert "fallback_rule_score" in markdown


def test_compare_runs_output_path_suffixes(tmp_path: Path) -> None:
    both = compare_runs.output_paths(
        low_cost_job_id="job_low",
        high_quality_job_id="job_high",
        output=tmp_path / "custom.report",
        output_format="both",
        root=tmp_path,
    )
    assert both.json_path == tmp_path / "custom.json"
    assert both.markdown_path == tmp_path / "custom.md"

    json_only = compare_runs.output_paths(
        low_cost_job_id="job_low",
        high_quality_job_id="job_high",
        output=tmp_path / "custom.json",
        output_format="json",
        root=tmp_path,
    )
    assert json_only.json_path == tmp_path / "custom.json"
    assert json_only.markdown_path is None


def test_compare_runs_requires_selected_artifact(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="selected_clips.json"):
        compare_runs.load_job("job_missing", root=tmp_path)


def test_e2e_compare_quality_builds_commands_and_extracts_job_id() -> None:
    args = e2e_compare_quality.parse_args(
        [
            "--video",
            "spoken.mp4",
            "--normal-count",
            "1",
            "--short-count",
            "2",
            "--openai-candidate-limit",
            "12",
            "--openai-finalist-scoring-limit",
            "4",
        ]
    )

    low_command = e2e_compare_quality.build_low_cost_command(args)
    high_command = e2e_compare_quality.build_high_quality_command(args)

    assert "--mode" in low_command
    assert "low_cost" in low_command
    assert "--use-openai-scoring" in low_command
    assert "false" in low_command
    assert "high_quality" in high_command
    assert "--openai-candidate-limit" in high_command
    assert "12" in high_command
    assert "--openai-finalist-scoring-limit" in high_command
    assert "4" in high_command

    assert e2e_compare_quality.extract_job_id("created job: job_abc123\nREAL VIDEO E2E PASSED") == "job_abc123"
    assert e2e_compare_quality.extract_job_id("created job: job_a\njob: job_b\n") == "job_b"
    with pytest.raises(RuntimeError, match="could not find job id"):
        e2e_compare_quality.extract_job_id("no job here")
