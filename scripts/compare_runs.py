from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
SAME_OVERLAP_THRESHOLD = 0.8
SELECTED_CLIP_FIELDS = [
    "id",
    "type",
    "start",
    "end",
    "duration",
    "rule_score",
    "ai_score",
    "final_score",
    "title",
    "overlay_title",
    "selection_reason",
    "below_quality_threshold",
    "quality_warning",
    "openai_score_source",
    "openai_fallback_used",
    "used_ai_score",
    "openai_scored",
    "openai_not_scored_reason",
]


@dataclass(frozen=True)
class OutputPaths:
    json_path: Path | None
    markdown_path: Path | None


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def job_output_dir(job_id: str, *, root: Path = ROOT) -> Path:
    return root / "storage" / "outputs" / job_id


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _bool(value: Any) -> bool:
    return value is True


def _selected_clip_items(selected_payload: dict[str, Any]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for key, default_type in (("normalClips", "normal"), ("shorts", "short")):
        for raw in selected_payload.get(key, []):
            if not isinstance(raw, dict):
                continue
            clip = {field: raw.get(field) for field in SELECTED_CLIP_FIELDS}
            clip["id"] = str(raw.get("id", ""))
            clip["type"] = str(raw.get("type") or default_type)
            clip["start"] = _number(raw.get("start"))
            clip["end"] = _number(raw.get("end"))
            clip["duration"] = _number(raw.get("duration"))
            clip["rule_score"] = _number(raw.get("rule_score"))
            clip["ai_score"] = _number(raw.get("ai_score"))
            clip["final_score"] = _number(raw.get("final_score"))
            clip["below_quality_threshold"] = _bool(raw.get("below_quality_threshold"))
            clip["openai_fallback_used"] = _bool(raw.get("openai_fallback_used"))
            clip["used_ai_score"] = _bool(raw.get("used_ai_score"))
            clip["openai_scored"] = _bool(raw.get("openai_scored"))
            clips.append(clip)
    return clips


def _count_by_type(clips: Sequence[dict[str, Any]], clip_type: str) -> int:
    return sum(1 for clip in clips if clip.get("type") == clip_type)


def _selected_counts(clips: Sequence[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "normal": summary.get("selected_normal_count", _count_by_type(clips, "normal")),
        "short": summary.get("selected_short_count", _count_by_type(clips, "short")),
        "total": len(clips),
    }


def _requested_counts(summary: dict[str, Any], candidate_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "normal": summary.get("requested_normal_count", candidate_summary.get("requested_normal_count")),
        "short": summary.get("requested_short_count", candidate_summary.get("requested_short_count")),
    }


def _render_failure_count(output_dir: Path, rejection_summary: dict[str, Any]) -> int | None:
    render_failures = read_json(output_dir / "render_failures.json", None)
    if isinstance(render_failures, list):
        return len(render_failures)
    value = rejection_summary.get("render_failure_count")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_job(job_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    output_dir = job_output_dir(job_id, root=root)
    selected = read_json(output_dir / "selected_clips.json")
    if not isinstance(selected, dict):
        raise RuntimeError(f"selected_clips.json not found or invalid for {job_id}: {output_dir}")

    selected_summary = read_json(output_dir / "selected_clips_summary.json", {})
    candidate_summary = read_json(output_dir / "candidate_summary.json", {})
    openai_summary = read_json(output_dir / "openai_scoring_summary.json", None)
    transcript_summary = read_json(output_dir / "transcript_summary.json", None)
    rejection_summary = read_json(output_dir / "rejection_summary.json", {})
    clips = _selected_clip_items(selected)
    return {
        "job_id": job_id,
        "output_dir": str(output_dir),
        "selected_clips": clips,
        "selected_counts": _selected_counts(clips, selected_summary if isinstance(selected_summary, dict) else {}),
        "requested_counts": _requested_counts(
            selected_summary if isinstance(selected_summary, dict) else {},
            candidate_summary if isinstance(candidate_summary, dict) else {},
        ),
        "selected_clips_summary": selected_summary if isinstance(selected_summary, dict) else {},
        "candidate_summary": candidate_summary if isinstance(candidate_summary, dict) else {},
        "openai_scoring_summary": openai_summary if isinstance(openai_summary, dict) else None,
        "transcript_summary": transcript_summary if isinstance(transcript_summary, dict) else None,
        "rejection_summary": rejection_summary if isinstance(rejection_summary, dict) else {},
        "render_failures_count": _render_failure_count(
            output_dir,
            rejection_summary if isinstance(rejection_summary, dict) else {},
        ),
    }


def overlap_seconds(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_start = _number(left.get("start"))
    left_end = _number(left.get("end"))
    right_start = _number(right.get("start"))
    right_end = _number(right.get("end"))
    if left_start is None or left_end is None or right_start is None or right_end is None:
        return 0.0
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def overlap_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    overlap = overlap_seconds(left, right)
    left_duration = _number(left.get("duration")) or 0.0
    right_duration = _number(right.get("duration")) or 0.0
    denominator = min(left_duration, right_duration)
    if denominator <= 0:
        return 0.0
    return round(overlap / denominator, 6)


def _score_delta(high_clip: dict[str, Any], low_clip: dict[str, Any], field: str) -> float | None:
    high_score = _number(high_clip.get(field))
    low_score = _number(low_clip.get(field))
    if high_score is None or low_score is None:
        return None
    return round(high_score - low_score, 6)


def _mean(values: Sequence[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 6)


def _best_overlap_rows(low_clips: Sequence[dict[str, Any]], high_clips: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for high_clip in high_clips:
        candidates = [
            (overlap_ratio(low_clip, high_clip), low_clip)
            for low_clip in low_clips
            if low_clip.get("type") == high_clip.get("type")
        ]
        ratio, low_clip = max(candidates, key=lambda item: item[0], default=(0.0, None))
        if ratio <= 0:
            low_clip = None
        rows.append(
            {
                "high_quality_clip_id": high_clip.get("id"),
                "high_quality_type": high_clip.get("type"),
                "low_cost_clip_id": low_clip.get("id") if low_clip else None,
                "overlap_ratio": ratio,
                "same_time_range": ratio >= SAME_OVERLAP_THRESHOLD,
                "exact_id_match": bool(low_clip and low_clip.get("id") == high_clip.get("id")),
                "score_differences": {
                    "rule_score": _score_delta(high_clip, low_clip, "rule_score") if low_clip else None,
                    "ai_score": _score_delta(high_clip, low_clip, "ai_score") if low_clip else None,
                    "final_score": _score_delta(high_clip, low_clip, "final_score") if low_clip else None,
                },
                "low_cost_clip": _clip_report_item(low_clip) if low_clip else None,
                "high_quality_clip": _clip_report_item(high_clip),
            }
        )
    return rows


def _greedy_same_time_matches(low_clips: Sequence[dict[str, Any]], high_clips: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for low_clip in low_clips:
        for high_clip in high_clips:
            if low_clip.get("type") != high_clip.get("type"):
                continue
            ratio = overlap_ratio(low_clip, high_clip)
            if ratio >= SAME_OVERLAP_THRESHOLD:
                pairs.append((ratio, low_clip, high_clip))
    matches: list[dict[str, Any]] = []
    used_low: set[str] = set()
    used_high: set[str] = set()
    for ratio, low_clip, high_clip in sorted(pairs, key=lambda item: item[0], reverse=True):
        low_id = str(low_clip.get("id"))
        high_id = str(high_clip.get("id"))
        if low_id in used_low or high_id in used_high:
            continue
        used_low.add(low_id)
        used_high.add(high_id)
        matches.append(
            {
                "low_cost_clip_id": low_id,
                "high_quality_clip_id": high_id,
                "type": high_clip.get("type"),
                "overlap_ratio": ratio,
                "exact_id_match": low_id == high_id,
                "score_differences": {
                    "rule_score": _score_delta(high_clip, low_clip, "rule_score"),
                    "ai_score": _score_delta(high_clip, low_clip, "ai_score"),
                    "final_score": _score_delta(high_clip, low_clip, "final_score"),
                },
            }
        )
    return matches


def _clip_report_item(clip: dict[str, Any] | None) -> dict[str, Any] | None:
    if clip is None:
        return None
    return {
        "id": clip.get("id"),
        "type": clip.get("type"),
        "start": clip.get("start"),
        "end": clip.get("end"),
        "duration": clip.get("duration"),
        "rule_score": clip.get("rule_score"),
        "ai_score": clip.get("ai_score"),
        "final_score": clip.get("final_score"),
        "title": clip.get("title"),
        "overlay_title": clip.get("overlay_title"),
        "selection_reason": clip.get("selection_reason"),
        "below_quality_threshold": clip.get("below_quality_threshold"),
        "quality_warning": clip.get("quality_warning"),
        "openai_score_source": clip.get("openai_score_source"),
        "openai_fallback_used": clip.get("openai_fallback_used"),
        "used_ai_score": clip.get("used_ai_score"),
        "openai_scored": clip.get("openai_scored"),
        "openai_not_scored_reason": clip.get("openai_not_scored_reason"),
    }


def _count_openai_field(clips: Sequence[dict[str, Any]], field: str) -> int:
    return sum(1 for clip in clips if _bool(clip.get(field)))


def _count_not_scored(clips: Sequence[dict[str, Any]]) -> int:
    return sum(
        1
        for clip in clips
        if not _bool(clip.get("used_ai_score"))
        and not _bool(clip.get("openai_fallback_used"))
        and str(clip.get("openai_score_source") or "") in {"not_scored", ""}
    )


def _count_backfill(clips: Sequence[dict[str, Any]]) -> int:
    return sum(
        1
        for clip in clips
        if _bool(clip.get("below_quality_threshold")) or str(clip.get("selection_reason") or "").startswith("backfill")
    )


def _count_fulfillment(job: dict[str, Any]) -> dict[str, Any]:
    selected = job["selected_counts"]
    requested = job["requested_counts"]
    return {
        "normal": {
            "selected": selected.get("normal"),
            "requested": requested.get("normal"),
            "fulfilled": _fulfilled(selected.get("normal"), requested.get("normal")),
        },
        "short": {
            "selected": selected.get("short"),
            "requested": requested.get("short"),
            "fulfilled": _fulfilled(selected.get("short"), requested.get("short")),
        },
    }


def _fulfilled(selected: Any, requested: Any) -> bool | None:
    try:
        selected_int = int(selected)
        requested_int = int(requested)
    except (TypeError, ValueError):
        return None
    return selected_int >= requested_int


def build_comparison_report(low_cost_job_id: str, high_quality_job_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    low_job = load_job(low_cost_job_id, root=root)
    high_job = load_job(high_quality_job_id, root=root)
    low_clips = low_job["selected_clips"]
    high_clips = high_job["selected_clips"]
    same_time_matches = _greedy_same_time_matches(low_clips, high_clips)
    overlap_rows = _best_overlap_rows(low_clips, high_clips)
    exact_ids = {str(clip.get("id")) for clip in low_clips} & {str(clip.get("id")) for clip in high_clips}
    final_score_differences = [match["score_differences"]["final_score"] for match in same_time_matches]
    rule_score_differences = [match["score_differences"]["rule_score"] for match in same_time_matches]
    ai_score_differences = [match["score_differences"]["ai_score"] for match in same_time_matches]

    high_openai_summary = high_job.get("openai_scoring_summary") or {}
    summary_metrics = {
        "same_selected_clips_count": len(same_time_matches),
        "different_selected_clips_count": max(0, len(high_clips) - len(same_time_matches)),
        "exact_selected_clip_id_match_count": len(exact_ids),
        "low_cost_only_selected_clips_count": max(0, len(low_clips) - len(same_time_matches)),
        "high_quality_selected_clips_count": len(high_clips),
        "low_cost_selected_clips_count": len(low_clips),
        "average_score_difference": _mean(final_score_differences),
        "average_final_score_difference": _mean(final_score_differences),
        "average_rule_score_difference": _mean(rule_score_differences),
        "average_ai_score_difference": _mean(ai_score_differences),
        "high_quality_clips_using_ai_score": _count_openai_field(high_clips, "used_ai_score"),
        "high_quality_clips_using_fallback": _count_openai_field(high_clips, "openai_fallback_used"),
        "high_quality_clips_not_scored": _count_not_scored(high_clips),
        "low_cost_backfill_count": _count_backfill(low_clips),
        "high_quality_backfill_count": _count_backfill(high_clips),
        "low_cost_count_fulfillment": _count_fulfillment(low_job),
        "high_quality_count_fulfillment": _count_fulfillment(high_job),
        "low_cost_render_failures": low_job.get("render_failures_count"),
        "high_quality_render_failures": high_job.get("render_failures_count"),
        "high_quality_openai_summary_counts": {
            "selected_ai_score_count": high_openai_summary.get("selected_ai_score_count"),
            "selected_fallback_score_count": high_openai_summary.get("selected_fallback_score_count"),
            "selected_not_scored_count": high_openai_summary.get("selected_not_scored_count"),
            "candidates_sent_to_openai": high_openai_summary.get("candidates_sent_to_openai"),
            "candidates_sent_preselection": high_openai_summary.get("candidates_sent_preselection"),
            "candidates_sent_as_finalists": high_openai_summary.get("candidates_sent_as_finalists"),
        },
    }
    return {
        "comparison": {
            "low_cost_job_id": low_cost_job_id,
            "high_quality_job_id": high_quality_job_id,
            "same_overlap_threshold": SAME_OVERLAP_THRESHOLD,
        },
        "summary_metrics": summary_metrics,
        "jobs": {
            "low_cost": _job_report_item(low_job),
            "high_quality": _job_report_item(high_job),
        },
        "selected_clip_comparisons": overlap_rows,
        "same_time_range_matches": same_time_matches,
    }


def _job_report_item(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "output_dir": job["output_dir"],
        "selected_counts": job["selected_counts"],
        "requested_counts": job["requested_counts"],
        "count_fulfillment": _count_fulfillment(job),
        "render_failures_count": job.get("render_failures_count"),
        "selected_clips": [_clip_report_item(clip) for clip in job["selected_clips"]],
        "candidate_summary": job.get("candidate_summary"),
        "selected_clips_summary": job.get("selected_clips_summary"),
        "openai_scoring_summary": job.get("openai_scoring_summary"),
        "transcript_summary": job.get("transcript_summary"),
    }


def _markdown_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("|", "\\|")
    if len(text) > 90:
        return f"{text[:87]}..."
    return text


def _clip_range(clip: dict[str, Any] | None) -> str:
    if not clip:
        return ""
    start = clip.get("start")
    end = clip.get("end")
    if start is None or end is None:
        return ""
    return f"{float(start):.3f}-{float(end):.3f}"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary_metrics"]
    comparison = report["comparison"]
    lines = [
        "# AutoClipper Run Comparison",
        "",
        f"- low_cost job: `{comparison['low_cost_job_id']}`",
        f"- high_quality job: `{comparison['high_quality_job_id']}`",
        f"- same-overlap threshold: `{comparison['same_overlap_threshold']}`",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in (
        "same_selected_clips_count",
        "different_selected_clips_count",
        "exact_selected_clip_id_match_count",
        "average_score_difference",
        "high_quality_clips_using_ai_score",
        "high_quality_clips_using_fallback",
        "high_quality_clips_not_scored",
        "low_cost_backfill_count",
        "high_quality_backfill_count",
        "low_cost_render_failures",
        "high_quality_render_failures",
    ):
        lines.append(f"| `{key}` | {_markdown_value(summary.get(key))} |")

    lines.extend(["", "## Count Fulfillment", "", "| Run | Normal | Short |", "| --- | --- | --- |"])
    for run_name in ("low_cost", "high_quality"):
        fulfillment = summary[f"{run_name}_count_fulfillment"]
        normal = fulfillment["normal"]
        short = fulfillment["short"]
        lines.append(
            f"| {run_name} | {_markdown_value(normal['selected'])}/{_markdown_value(normal['requested'])} "
            f"fulfilled={_markdown_value(normal['fulfilled'])} | "
            f"{_markdown_value(short['selected'])}/{_markdown_value(short['requested'])} "
            f"fulfilled={_markdown_value(short['fulfilled'])} |"
        )

    lines.extend(
        [
            "",
            "## Selected Clip Comparison",
            "",
            "| Type | High Quality Clip | HQ Range | Low Cost Match | LC Range | Overlap | HQ final | LC final | AI source | Fallback | Backfill | Title |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in report["selected_clip_comparisons"]:
        high_clip = row["high_quality_clip"]
        low_clip = row["low_cost_clip"]
        lines.append(
            "| "
            f"{_markdown_value(high_clip.get('type'))} | "
            f"`{_markdown_value(high_clip.get('id'))}` | "
            f"{_clip_range(high_clip)} | "
            f"`{_markdown_value(low_clip.get('id') if low_clip else None)}` | "
            f"{_clip_range(low_clip)} | "
            f"{_markdown_value(row.get('overlap_ratio'))} | "
            f"{_markdown_value(high_clip.get('final_score'))} | "
            f"{_markdown_value(low_clip.get('final_score') if low_clip else None)} | "
            f"{_markdown_value(high_clip.get('openai_score_source'))} | "
            f"{_markdown_value(high_clip.get('openai_fallback_used'))} | "
            f"{_markdown_value(high_clip.get('selection_reason'))} | "
            f"{_markdown_value(high_clip.get('title'))} |"
        )

    openai = report["jobs"]["high_quality"].get("openai_scoring_summary") or {}
    lines.extend(["", "## High Quality OpenAI Summary", "", "| Field | Value |", "| --- | ---: |"])
    for key in (
        "model",
        "candidate_limit",
        "finalist_scoring_limit",
        "candidates_sent_preselection",
        "candidates_sent_as_finalists",
        "candidates_sent_to_openai",
        "successful_scores",
        "failed_scores",
        "fallback_scores",
        "selected_ai_score_count",
        "selected_fallback_score_count",
        "selected_not_scored_count",
    ):
        lines.append(f"| `{key}` | {_markdown_value(openai.get(key))} |")
    lines.append("")
    return "\n".join(lines)


def output_paths(
    *,
    low_cost_job_id: str,
    high_quality_job_id: str,
    output: Path | None,
    output_format: str,
    root: Path = ROOT,
) -> OutputPaths:
    json_enabled = output_format in {"json", "both"}
    markdown_enabled = output_format in {"markdown", "both"}
    if output is None:
        output_dir = root / "storage" / "outputs" / "comparisons" / f"{low_cost_job_id}_vs_{high_quality_job_id}"
        return OutputPaths(
            json_path=output_dir / "comparison_report.json" if json_enabled else None,
            markdown_path=output_dir / "comparison_report.md" if markdown_enabled else None,
        )
    if output.suffix:
        if output_format == "json":
            return OutputPaths(json_path=output, markdown_path=None)
        if output_format == "markdown":
            return OutputPaths(json_path=None, markdown_path=output)
        return OutputPaths(
            json_path=output.with_suffix(".json"),
            markdown_path=output.with_suffix(".md"),
        )
    return OutputPaths(
        json_path=output / "comparison_report.json" if json_enabled else None,
        markdown_path=output / "comparison_report.md" if markdown_enabled else None,
    )


def write_report(report: dict[str, Any], paths: OutputPaths) -> list[Path]:
    written: list[Path] = []
    if paths.json_path is not None:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(paths.json_path)
    if paths.markdown_path is not None:
        paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        paths.markdown_path.write_text(render_markdown(report), encoding="utf-8")
        written.append(paths.markdown_path)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare low_cost and high_quality AutoClipper job artifacts.")
    parser.add_argument("--low-cost-job-id", required=True)
    parser.add_argument("--high-quality-job-id", required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run(args: argparse.Namespace) -> int:
    report = build_comparison_report(args.low_cost_job_id, args.high_quality_job_id)
    paths = output_paths(
        low_cost_job_id=args.low_cost_job_id,
        high_quality_job_id=args.high_quality_job_id,
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
        print(f"COMPARE RUNS FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
