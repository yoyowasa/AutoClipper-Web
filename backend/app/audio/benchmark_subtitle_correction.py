from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.audio.benchmark_transcription import character_error_rate, keyword_metrics, transcript_text
from app.audio.openai_transcript_correction import OpenAITranscriptCorrector
from app.audio.transcribe_faster_whisper import TranscriptSegment, segments_to_jsonable
from app.audio.transcript_postprocess import DEFAULT_TRANSCRIPT_REPLACEMENTS
from app.audio.transcript_suspicion import analyze_transcript_suspicion


DEFAULT_PROFILES = (
    "gpt-5.5:default",
    "gpt-5.5:none",
    "gpt-5.4-mini:none",
    "gpt-5-mini:lowest",
    "gpt-5.6-luna:none",
)
REASONING_EFFORTS = {"default", "none", "minimal", "low", "medium", "high", "xhigh", "max"}
RESPONSE_SCHEMAS = {"full", "changes_only"}
LOWEST_REASONING_CANDIDATES = ("none", "minimal", "low", "medium", "high")
MANUAL_REVIEW_FIELDS = (
    "useful_corrections",
    "missed_corrections",
    "harmful_corrections",
    "unnecessary_style_changes",
    "uncertain",
)


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


# Snapshot used only for reproducible benchmark estimates. Production summaries do not calculate prices.
MODEL_PRICING_2026_07_18: dict[str, ModelPricing] = {
    "gpt-5.5": ModelPricing(5.0, 0.5, 30.0),
    "gpt-5.4-mini": ModelPricing(0.75, 0.075, 4.5),
    "gpt-5-mini": ModelPricing(0.25, 0.025, 2.0),
    "gpt-5.6-luna": ModelPricing(1.0, 0.1, 6.0),
}


@dataclass(frozen=True)
class BenchmarkProfile:
    model: str
    reasoning_effort: str
    response_schema: str = "full"

    @property
    def label(self) -> str:
        suffix = "" if self.response_schema == "full" else f"_{self.response_schema}"
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{self.model}_{self.reasoning_effort}{suffix}")

    @property
    def specification(self) -> str:
        return f"{self.model}:{self.reasoning_effort}:{self.response_schema}"


def parse_profile(value: str, *, allow_lowest: bool = True) -> BenchmarkProfile:
    parts = value.split(":")
    if len(parts) not in {2, 3}:
        raise argparse.ArgumentTypeError("profile must be MODEL:REASONING[:SCHEMA]")
    model, reasoning_effort = parts[:2]
    response_schema = parts[2] if len(parts) == 3 else "full"
    allowed = REASONING_EFFORTS | ({"lowest"} if allow_lowest else set())
    if not model.strip() or reasoning_effort not in allowed or response_schema not in RESPONSE_SCHEMAS:
        values = "|".join(sorted(allowed))
        schemas = "|".join(sorted(RESPONSE_SCHEMAS))
        raise argparse.ArgumentTypeError(
            f"profile must be MODEL:REASONING[:SCHEMA] using reasoning {values} and schema {schemas}"
        )
    return BenchmarkProfile(
        model=model.strip(),
        reasoning_effort=reasoning_effort,
        response_schema=response_schema,
    )


def load_segments(path: Path) -> list[TranscriptSegment]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("segments JSON must be an array")
    return [TranscriptSegment.model_validate(item) for item in payload]


def load_target_indices(path: Path | None, *, segment_count: int) -> list[int]:
    if path is None:
        return list(range(segment_count))
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("target_indices") if isinstance(payload, Mapping) else payload
    if not isinstance(values, list):
        raise ValueError("targets JSON must be an array or contain target_indices")
    targets = sorted({int(value) for value in values})
    if any(index < 0 or index >= segment_count for index in targets):
        raise ValueError("target index is outside transcript segments")
    return targets


def parse_alias(value: str) -> tuple[str, str]:
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("canonical alias must be SOURCE=TARGET")
    return source, target


def apply_aliases(text: str, aliases: Sequence[tuple[str, str]]) -> str:
    updated = text
    for source, target in sorted(aliases, key=lambda pair: len(pair[0]), reverse=True):
        updated = updated.replace(source, target)
    return updated


def estimated_actual_cost_usd(summary: Mapping[str, Any], model: str) -> float | None:
    pricing = MODEL_PRICING_2026_07_18.get(model)
    if pricing is None:
        return None
    input_tokens = max(0, int(summary.get("input_tokens", 0) or 0))
    cached_tokens = min(input_tokens, max(0, int(summary.get("cached_tokens", 0) or 0)))
    output_tokens = max(0, int(summary.get("output_tokens", 0) or 0))
    regular_input_tokens = input_tokens - cached_tokens
    cost = (
        regular_input_tokens * pricing.input_per_million
        + cached_tokens * pricing.cached_input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000
    return round(cost, 8)


def _reduction_percent(baseline: float, candidate: float) -> float | None:
    if baseline <= 0:
        return None
    return round((1 - candidate / baseline) * 100, 6)


def build_baseline_comparisons(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not runs:
        return []
    baseline = runs[0]
    baseline_summary = baseline["summary"]
    baseline_changes = {int(change["index"]): str(change.get("after", "")) for change in baseline.get("changes", [])}
    baseline_indices = set(baseline_changes)
    baseline_total_tokens = int(baseline_summary["input_tokens"]) + int(baseline_summary["output_tokens"])
    baseline_cost = baseline.get("estimated_actual_cost_usd")
    comparisons: list[dict[str, Any]] = []
    for run in runs[1:]:
        summary = run["summary"]
        candidate_changes = {int(change["index"]): str(change.get("after", "")) for change in run.get("changes", [])}
        candidate_indices = set(candidate_changes)
        shared_indices = baseline_indices & candidate_indices
        candidate_total_tokens = int(summary["input_tokens"]) + int(summary["output_tokens"])
        candidate_cost = run.get("estimated_actual_cost_usd")
        comparisons.append(
            {
                "baseline_profile": baseline["profile"],
                "candidate_profile": run["profile"],
                "shared_changed_indices": len(shared_indices),
                "shared_changed_same_text": sum(
                    1 for index in shared_indices if baseline_changes[index] == candidate_changes[index]
                ),
                "shared_changed_different_text": sum(
                    1 for index in shared_indices if baseline_changes[index] != candidate_changes[index]
                ),
                "baseline_only_changed_indices": len(baseline_indices - candidate_indices),
                "candidate_only_changed_indices": len(candidate_indices - baseline_indices),
                "output_token_reduction_percent": _reduction_percent(
                    float(baseline_summary["output_tokens"]),
                    float(summary["output_tokens"]),
                ),
                "total_token_reduction_percent": _reduction_percent(
                    float(baseline_total_tokens),
                    float(candidate_total_tokens),
                ),
                "cost_reduction_percent": (
                    _reduction_percent(float(baseline_cost), float(candidate_cost))
                    if baseline_cost is not None and candidate_cost is not None
                    else None
                ),
                "processing_time_reduction_percent": _reduction_percent(
                    float(baseline_summary["processing_seconds"]),
                    float(summary["processing_seconds"]),
                ),
            }
        )
    return comparisons


def timestamp_preservation(
    source: Sequence[TranscriptSegment],
    corrected: Sequence[TranscriptSegment],
) -> dict[str, Any]:
    count_preserved = len(source) == len(corrected)
    mismatches: list[int] = []
    if count_preserved:
        mismatches = [
            index
            for index, (before, after) in enumerate(zip(source, corrected, strict=True))
            if before.start != after.start or before.end != after.end
        ]
    return {
        "segment_count_preserved": count_preserved,
        "segment_order_preserved": count_preserved,
        "timestamp_mismatch_count": len(mismatches) if count_preserved else abs(len(source) - len(corrected)),
        "timestamp_mismatch_indices": mismatches[:20],
        "timestamps_preserved": count_preserved and not mismatches,
    }


def load_manual_review(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles") if isinstance(payload, Mapping) else None
    if not isinstance(profiles, Mapping):
        raise ValueError("manual review JSON must contain a profiles object")
    return dict(profiles)


def load_baseline_run(
    report_path: Path,
    changes_path: Path,
    *,
    segment_count: int,
    target_segment_count: int,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, Mapping):
        raise ValueError("baseline report must be an object")
    if int(report.get("segment_count", -1)) != segment_count:
        raise ValueError("baseline report segment_count does not match the benchmark input")
    if int(report.get("target_segment_count", -1)) != target_segment_count:
        raise ValueError("baseline report target_segment_count does not match the benchmark targets")
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], Mapping):
        raise ValueError("baseline report must contain at least one run")
    changes = json.loads(changes_path.read_text(encoding="utf-8"))
    if not isinstance(changes, list):
        raise ValueError("baseline changes must be an array")
    baseline = dict(runs[0])
    baseline["changes"] = changes
    baseline.setdefault("response_schema", "full")
    baseline_summary = dict(baseline.get("summary", {}))
    baseline_summary.setdefault("response_schema", "full")
    baseline["summary"] = baseline_summary
    return baseline


def manual_review_metrics(profile_label: str, review: Mapping[str, Any]) -> dict[str, Any]:
    profile_review = review.get(profile_label)
    if not isinstance(profile_review, Mapping):
        return {field: None for field in MANUAL_REVIEW_FIELDS} | {"reviewed": False}
    return {
        field: len(profile_review.get(field, [])) if isinstance(profile_review.get(field), list) else 0
        for field in MANUAL_REVIEW_FIELDS
    } | {"reviewed": True}


def apply_manual_review_to_report(report: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    updated = dict(report)
    runs: list[dict[str, Any]] = []
    for raw_run in report.get("runs", []):
        run = dict(raw_run)
        quality = dict(run.get("quality", {}))
        quality["manual_review"] = manual_review_metrics(str(run.get("profile_label", "")), review)
        run["quality"] = quality
        runs.append(run)
    updated["runs"] = runs
    updated["manual_review_applied"] = True
    return updated


def quality_metrics(
    source: Sequence[TranscriptSegment],
    corrected: Sequence[TranscriptSegment],
    *,
    reference: str | None,
    keywords: Sequence[str],
    aliases: Sequence[tuple[str, str]],
    profile_label: str,
    manual_review: Mapping[str, Any],
) -> dict[str, Any]:
    corrected_text = transcript_text(corrected)
    normalized_reference = apply_aliases(reference, aliases) if reference is not None else None
    normalized_corrected = apply_aliases(corrected_text, aliases)
    return {
        "character_error_rate": (
            round(character_error_rate(normalized_reference, normalized_corrected), 6)
            if normalized_reference is not None
            else None
        ),
        "proper_noun_metrics": keyword_metrics(corrected_text, keywords),
        "manual_review": manual_review_metrics(profile_label, manual_review),
        "preservation": timestamp_preservation(source, corrected),
    }


def resolve_lowest_reasoning_from_probe(report_path: Path, model: str) -> str:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    resolutions = payload.get("lowest_reasoning_resolutions", {})
    value = resolutions.get(model) if isinstance(resolutions, Mapping) else None
    if value not in REASONING_EFFORTS - {"default"}:
        raise ValueError(f"probe report does not contain a valid lowest reasoning effort for {model}")
    return str(value)


def _run_correction(
    segments: Sequence[TranscriptSegment],
    profile: BenchmarkProfile,
    *,
    target_indices: Sequence[int],
    batch_size: int,
    context_segments: int,
    min_confidence: float,
    glossary: Sequence[str],
) -> Any:
    corrector = OpenAITranscriptCorrector(
        model=profile.model,
        reasoning_effort=profile.reasoning_effort,
        response_schema=profile.response_schema,
        max_retries=0,
    )
    return corrector.correct_segments(
        segments,
        target_indices=target_indices,
        batch_size=batch_size,
        context_segments=context_segments,
        min_confidence=min_confidence,
        glossary=glossary,
    )


def run_probe(
    segments: Sequence[TranscriptSegment],
    profiles: Sequence[BenchmarkProfile],
    *,
    target_index: int,
    context_segments: int,
    min_confidence: float,
    glossary: Sequence[str],
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    resolutions: dict[str, str] = {}
    for requested_profile in profiles:
        candidates = (
            LOWEST_REASONING_CANDIDATES
            if requested_profile.reasoning_effort == "lowest"
            else (requested_profile.reasoning_effort,)
        )
        attempts: list[dict[str, Any]] = []
        for reasoning_effort in candidates:
            profile = BenchmarkProfile(
                requested_profile.model,
                reasoning_effort,
                requested_profile.response_schema,
            )
            try:
                result = _run_correction(
                    segments,
                    profile,
                    target_indices=[target_index],
                    batch_size=1,
                    context_segments=context_segments,
                    min_confidence=min_confidence,
                    glossary=glossary,
                )
                attempts.append(
                    {
                        "reasoning_effort": reasoning_effort,
                        "success": True,
                        "summary": result.summary,
                    }
                )
                if requested_profile.reasoning_effort == "lowest":
                    resolutions[requested_profile.model] = reasoning_effort
                break
            except Exception as exc:
                attempts.append(
                    {
                        "reasoning_effort": reasoning_effort,
                        "success": False,
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
        runs.append(
            {
                "requested_profile": requested_profile.specification,
                "model": requested_profile.model,
                "success": bool(attempts and attempts[-1]["success"]),
                "attempts": attempts,
            }
        )
    return {
        "phase": "probe",
        "target_index": target_index,
        "segment_count": len(segments),
        "lowest_reasoning_resolutions": resolutions,
        "runs": runs,
    }


def run_benchmark(
    segments: Sequence[TranscriptSegment],
    profiles: Sequence[BenchmarkProfile],
    *,
    target_indices: Sequence[int],
    batch_size: int,
    context_segments: int,
    min_confidence: float,
    glossary: Sequence[str],
    reference: str | None,
    keywords: Sequence[str],
    aliases: Sequence[tuple[str, str]],
    manual_review: Mapping[str, Any],
    output_dir: Path,
    baseline_run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = [dict(baseline_run)] if baseline_run is not None else []
    for profile in profiles:
        result = _run_correction(
            segments,
            profile,
            target_indices=target_indices,
            batch_size=batch_size,
            context_segments=context_segments,
            min_confidence=min_confidence,
            glossary=glossary,
        )
        corrected_path = output_dir / f"{profile.label}_corrected_transcript_segments.json"
        changes_path = output_dir / f"{profile.label}_changes.json"
        corrected_path.write_text(
            json.dumps(segments_to_jsonable(result.segments), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        changes_path.write_text(json.dumps(result.changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        runs.append(
            {
                "profile": profile.specification,
                "profile_label": profile.label,
                "model": profile.model,
                "reasoning_effort": profile.reasoning_effort,
                "response_schema": profile.response_schema,
                "summary": result.summary,
                "estimated_actual_cost_usd": estimated_actual_cost_usd(result.summary, profile.model),
                "quality": quality_metrics(
                    segments,
                    result.segments,
                    reference=reference,
                    keywords=keywords,
                    aliases=aliases,
                    profile_label=profile.label,
                    manual_review=manual_review,
                ),
                "changes": result.changes,
                "corrected_transcript_path": str(corrected_path),
                "changes_path": str(changes_path),
            }
        )
    comparisons = build_baseline_comparisons(runs)
    for run in runs:
        run.pop("changes", None)
    return {
        "phase": "benchmark",
        "segment_count": len(segments),
        "target_segment_count": len(target_indices),
        "batch_size": batch_size,
        "context_segments": context_segments,
        "min_confidence": min_confidence,
        "pricing_snapshot": "2026-07-18",
        "cost_note": "Usage-based estimate; cached input pricing is included when cached_tokens is reported.",
        "baseline_reused": baseline_run is not None,
        "runs": runs,
        "baseline_comparisons": comparisons,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    if report.get("phase") == "probe":
        lines = [
            "# Subtitle Correction Model Probe",
            "",
            "| Profile | Result | Accepted reasoning | API calls | Input | Output | Reasoning | Visible |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for run in report.get("runs", []):
            attempts = run.get("attempts", [])
            successful = next((attempt for attempt in attempts if attempt.get("success")), None)
            summary = successful.get("summary", {}) if successful else {}
            lines.append(
                f"| {run['requested_profile']} | {'pass' if successful else 'fail'} | "
                f"{successful.get('reasoning_effort', '-') if successful else '-'} | "
                f"{summary.get('api_call_count', 0)} | {summary.get('input_tokens', 0)} | "
                f"{summary.get('output_tokens', 0)} | {summary.get('reasoning_tokens', 0)} | "
                f"{summary.get('visible_output_tokens', 0)} |"
            )
        return "\n".join(lines) + "\n"

    lines = [
        "# Subtitle Correction Model Benchmark",
        "",
        "| Profile | Changes | CER | Proper nouns | Useful | Missed | Harmful | Style | "
        "Input | Output | Reasoning | Visible | Cost USD | Seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report.get("runs", []):
        summary = run["summary"]
        quality = run["quality"]
        proper_nouns = quality["proper_noun_metrics"]
        review = quality.get("manual_review", {})

        def review_value(key: str) -> str:
            return "n/a" if review.get(key) is None else str(review[key])

        cer = quality["character_error_rate"]
        cost = run["estimated_actual_cost_usd"]
        lines.append(
            f"| {run['profile']} | {summary['corrected_segment_count']} | "
            f"{'n/a' if cer is None else f'{cer:.4f}'} | "
            f"{proper_nouns['matched']}/{proper_nouns['requested']} | "
            f"{review_value('useful_corrections')} | {review_value('missed_corrections')} | "
            f"{review_value('harmful_corrections')} | {review_value('unnecessary_style_changes')} | "
            f"{summary['input_tokens']} | {summary['output_tokens']} | "
            f"{summary['reasoning_tokens']} | {summary['visible_output_tokens']} | "
            f"{'n/a' if cost is None else f'{cost:.4f}'} | {summary['processing_seconds']:.3f} |"
        )
    comparisons = report.get("baseline_comparisons", [])
    if comparisons:
        def percent_text(value: Any) -> str:
            return "n/a" if value is None else f"{float(value):.3f}%"

        lines.extend(
            [
                "",
                "## Baseline comparison",
                "",
                "| Candidate | Shared changes | Baseline only | Candidate only | "
                "Same text | Different text | "
                "Output token reduction | Total token reduction | Cost reduction | Time reduction |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for comparison in comparisons:
            lines.append(
                f"| {comparison['candidate_profile']} | {comparison['shared_changed_indices']} | "
                f"{comparison['baseline_only_changed_indices']} | "
                f"{comparison['candidate_only_changed_indices']} | "
                f"{comparison['shared_changed_same_text']} | "
                f"{comparison['shared_changed_different_text']} | "
                f"{percent_text(comparison['output_token_reduction_percent'])} | "
                f"{percent_text(comparison['total_token_reduction_percent'])} | "
                f"{percent_text(comparison['cost_reduction_percent'])} | "
                f"{percent_text(comparison['processing_time_reduction_percent'])} |"
            )
    lines.extend(
        [
            "",
            "Cost is an estimate from actual API usage and the pricing snapshot recorded in the JSON report.",
            (
                "Manual quality classifications were applied from the supplied review file."
                if report.get("manual_review_applied")
                else "Manual quality fields remain null until the change review file is supplied."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare OpenAI subtitle correction models on fixed transcript segments.")
    parser.add_argument("--phase", choices=["probe", "benchmark", "review"], required=True)
    parser.add_argument("--segments", type=Path)
    parser.add_argument("--targets-file", type=Path)
    parser.add_argument("--scope", choices=["all", "suspicious"], default="suspicious")
    parser.add_argument("--suspicion-threshold", type=float, default=0.4)
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--probe-report", type=Path)
    parser.add_argument("--probe-target-index", type=int)
    parser.add_argument("--reference-file", type=Path)
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--glossary", action="append", default=[])
    parser.add_argument("--no-default-glossary", action="store_true")
    parser.add_argument("--canonical-alias", action="append", type=parse_alias, default=[])
    parser.add_argument("--manual-review-file", type=Path)
    parser.add_argument("--existing-report", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--baseline-changes", type=Path)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--context-segments", type=int, default=2)
    parser.add_argument("--min-confidence", type=float, default=0.9)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.phase == "review":
        if args.existing_report is None or args.manual_review_file is None:
            raise SystemExit("--existing-report and --manual-review-file are required for review")
        report = apply_manual_review_to_report(
            json.loads(args.existing_report.resolve().read_text(encoding="utf-8")),
            load_manual_review(args.manual_review_file.resolve()),
        )
        json_path = args.output_dir / "subtitle_correction_model_benchmark_reviewed.json"
        markdown_path = args.output_dir / "subtitle_correction_model_benchmark_reviewed.md"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        print(json_path)
        print(markdown_path)
        return 0

    if args.segments is None:
        raise SystemExit("--segments is required for probe and benchmark")
    args.segments = args.segments.resolve()
    if not args.segments.is_file():
        raise SystemExit(f"segments file not found: {args.segments}")
    if args.batch_size < 1 or args.batch_size > 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    if args.context_segments < 0 or args.context_segments > 10:
        raise SystemExit("--context-segments must be between 0 and 10")
    if not 0 <= args.min_confidence <= 1:
        raise SystemExit("--min-confidence must be between 0 and 1")
    if not 0 <= args.suspicion_threshold <= 1:
        raise SystemExit("--suspicion-threshold must be between 0 and 1")

    segments = load_segments(args.segments)
    glossary = [
        *([] if args.no_default_glossary else DEFAULT_TRANSCRIPT_REPLACEMENTS.values()),
        *args.glossary,
    ]
    if args.targets_file:
        targets = load_target_indices(args.targets_file.resolve(), segment_count=len(segments))
        target_source = str(args.targets_file.resolve())
    elif args.scope == "suspicious":
        suspicion_result = analyze_transcript_suspicion(
            segments,
            threshold=args.suspicion_threshold,
            context_segments=args.context_segments,
            batch_size=args.batch_size,
            glossary=glossary,
        )
        targets = suspicion_result.target_indices
        target_source = "derived_suspicious"
    else:
        targets = list(range(len(segments)))
        target_source = "all"
    if not targets:
        raise SystemExit("no correction target segments")
    profiles = [parse_profile(value) for value in (args.profile or DEFAULT_PROFILES)]

    if args.phase == "probe":
        target_index = args.probe_target_index if args.probe_target_index is not None else targets[0]
        if target_index not in targets:
            raise SystemExit("probe target index is not in the selected target set")
        report = run_probe(
            segments,
            profiles,
            target_index=target_index,
            context_segments=args.context_segments,
            min_confidence=args.min_confidence,
            glossary=glossary,
        )
        report["target_source"] = target_source
        report["suspicion_threshold"] = args.suspicion_threshold
        json_path = args.output_dir / "subtitle_correction_probe_report.json"
        markdown_path = args.output_dir / "subtitle_correction_probe_report.md"
    else:
        if (args.baseline_report is None) != (args.baseline_changes is None):
            raise SystemExit("--baseline-report and --baseline-changes must be supplied together")
        if args.baseline_report is not None and not args.profile:
            raise SystemExit("at least one --profile is required when reusing a baseline")
        resolved_profiles: list[BenchmarkProfile] = []
        for profile in profiles:
            if profile.reasoning_effort == "lowest":
                if args.probe_report is None:
                    raise SystemExit("--probe-report is required for a lowest reasoning profile")
                profile = BenchmarkProfile(
                    profile.model,
                    resolve_lowest_reasoning_from_probe(args.probe_report.resolve(), profile.model),
                    profile.response_schema,
                )
            resolved_profiles.append(profile)
        reference = args.reference_file.read_text(encoding="utf-8") if args.reference_file else None
        baseline_run = (
            load_baseline_run(
                args.baseline_report.resolve(),
                args.baseline_changes.resolve(),
                segment_count=len(segments),
                target_segment_count=len(targets),
            )
            if args.baseline_report is not None and args.baseline_changes is not None
            else None
        )
        report = run_benchmark(
            segments,
            resolved_profiles,
            target_indices=targets,
            batch_size=args.batch_size,
            context_segments=args.context_segments,
            min_confidence=args.min_confidence,
            glossary=glossary,
            reference=reference,
            keywords=args.keyword,
            aliases=args.canonical_alias,
            manual_review=load_manual_review(args.manual_review_file),
            output_dir=args.output_dir,
            baseline_run=baseline_run,
        )
        report["target_source"] = target_source
        report["suspicion_threshold"] = args.suspicion_threshold
        json_path = args.output_dir / "subtitle_correction_model_benchmark.json"
        markdown_path = args.output_dir / "subtitle_correction_model_benchmark.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
