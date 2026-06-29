from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from compare_runs import build_comparison_report, output_paths, write_report


ROOT = Path(__file__).resolve().parents[1]
JOB_ID_PATTERN = re.compile(r"\b(?:created job|job):\s*(job_[A-Za-z0-9]+)\b")


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run low_cost and high_quality E2E on the same video and compare outputs.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--normal-count", type=non_negative_int, default=2)
    parser.add_argument("--short-count", type=non_negative_int, default=3)
    parser.add_argument("--normal-min-duration", type=positive_float, default=90.0)
    parser.add_argument("--normal-max-duration", type=positive_float, default=600.0)
    parser.add_argument("--short-min-duration", type=positive_float, default=20.0)
    parser.add_argument("--short-max-duration", type=positive_float, default=75.0)
    parser.add_argument("--selection-policy", choices=["fill_requested", "strict_quality"], default="fill_requested")
    parser.add_argument("--openai-candidate-limit", type=non_negative_int, default=20)
    parser.add_argument("--openai-finalist-scoring-limit", type=non_negative_int, default=7)
    parser.add_argument("--openai-model", default="gpt-5.5")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _base_e2e_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "e2e_real_video.py"),
        "--video",
        str(args.video),
        "--backend-url",
        args.backend_url,
        "--timeout",
        str(args.timeout),
        "--normal-count",
        str(args.normal_count),
        "--short-count",
        str(args.short_count),
        "--normal-min-duration",
        str(args.normal_min_duration),
        "--normal-max-duration",
        str(args.normal_max_duration),
        "--short-min-duration",
        str(args.short_min_duration),
        "--short-max-duration",
        str(args.short_max_duration),
        "--selection-policy",
        args.selection_policy,
    ]


def build_low_cost_command(args: argparse.Namespace) -> list[str]:
    return [
        *_base_e2e_command(args),
        "--mode",
        "low_cost",
        "--use-openai-scoring",
        "false",
    ]


def build_high_quality_command(args: argparse.Namespace) -> list[str]:
    return [
        *_base_e2e_command(args),
        "--mode",
        "high_quality",
        "--use-openai-scoring",
        "true",
        "--openai-candidate-limit",
        str(args.openai_candidate_limit),
        "--openai-model",
        args.openai_model,
        "--openai-fallback-to-rule-score",
        "true",
        "--ensure-selected-openai-scored",
        "true",
        "--openai-finalist-scoring-limit",
        str(args.openai_finalist_scoring_limit),
    ]


def extract_job_id(output: str) -> str:
    matches = JOB_ID_PATTERN.findall(output)
    if not matches:
        raise RuntimeError("could not find job id in E2E output")
    return matches[-1]


def run_command(command: Sequence[str]) -> str:
    print(f"running: {' '.join(command)}")
    process = subprocess.Popen(
        list(command),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)
    return_code = process.wait()
    output = "".join(output_lines)
    if return_code != 0:
        raise RuntimeError(f"command failed with exit code {return_code}: {' '.join(command)}")
    return output


def run(args: argparse.Namespace) -> int:
    low_output = run_command(build_low_cost_command(args))
    low_job_id = extract_job_id(low_output)
    print(f"low_cost job id: {low_job_id}")

    high_output = run_command(build_high_quality_command(args))
    high_job_id = extract_job_id(high_output)
    print(f"high_quality job id: {high_job_id}")

    report = build_comparison_report(low_job_id, high_job_id)
    paths = output_paths(
        low_cost_job_id=low_job_id,
        high_quality_job_id=high_job_id,
        output=args.output,
        output_format=args.format,
    )
    written = write_report(report, paths)
    print(
        "comparison summary: "
        f"same={report['summary_metrics']['same_selected_clips_count']} "
        f"different={report['summary_metrics']['different_selected_clips_count']} "
        f"high_quality_ai={report['summary_metrics']['high_quality_clips_using_ai_score']} "
        f"fallback={report['summary_metrics']['high_quality_clips_using_fallback']} "
        f"not_scored={report['summary_metrics']['high_quality_clips_not_scored']}"
    )
    for path in written:
        print(f"report: {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"E2E QUALITY COMPARISON FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
