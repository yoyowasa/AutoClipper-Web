from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Sequence

from app.audio.transcribe_faster_whisper import FasterWhisperTranscriptionEngine, TranscriptSegment, segments_to_jsonable


DEFAULT_PROFILES = ("base:auto", "base:ja", "small:ja", "medium:ja")


def parse_profile(value: str) -> tuple[str, str]:
    model, separator, language = value.partition(":")
    if not separator or model not in {"base", "small", "medium", "large-v3"} or language not in {"auto", "ja"}:
        raise argparse.ArgumentTypeError("profile must be MODEL:LANGUAGE using base|small|medium|large-v3 and auto|ja")
    return model, language


def profile_label(model: str, language: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{model}_{language}")


def normalize_for_cer(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(character for character in normalized if not character.isspace() and not unicodedata.category(character).startswith("P"))


def levenshtein_distance(reference: str, hypothesis: str) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_character in enumerate(reference, start=1):
        current = [reference_index]
        for hypothesis_index, hypothesis_character in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[hypothesis_index] + 1,
                    previous[hypothesis_index - 1] + (reference_character != hypothesis_character),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float | None:
    normalized_reference = normalize_for_cer(reference)
    if not normalized_reference:
        return None
    normalized_hypothesis = normalize_for_cer(hypothesis)
    return levenshtein_distance(normalized_reference, normalized_hypothesis) / len(normalized_reference)


def transcript_text(segments: Sequence[TranscriptSegment] | Sequence[dict[str, Any]]) -> str:
    texts = []
    for segment in segments:
        text = segment.text if isinstance(segment, TranscriptSegment) else str(segment.get("text", ""))
        if text.strip():
            texts.append(text.strip())
    return " ".join(texts)


def timestamp_metrics(segments: Sequence[dict[str, Any]]) -> dict[str, Any]:
    invalid_ranges = 0
    non_monotonic = 0
    previous_end = 0.0
    for segment in segments:
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        if start < 0 or end < start:
            invalid_ranges += 1
        if start < previous_end - 0.05:
            non_monotonic += 1
        previous_end = max(previous_end, end)
    return {
        "segment_count": len(segments),
        "invalid_timestamp_ranges": invalid_ranges,
        "non_monotonic_timestamps": non_monotonic,
        "last_segment_end": round(previous_end, 3) if segments else 0.0,
    }


def keyword_metrics(text: str, keywords: Sequence[str]) -> dict[str, Any]:
    normalized_text = normalize_for_cer(text)
    matched = [keyword for keyword in keywords if normalize_for_cer(keyword) in normalized_text]
    return {
        "requested": len(keywords),
        "matched": len(matched),
        "accuracy": round(len(matched) / len(keywords), 6) if keywords else None,
        "matched_keywords": matched,
        "missing_keywords": [keyword for keyword in keywords if keyword not in matched],
    }


def _peak_memory_mb() -> float | None:
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return round(value / 1024.0, 3)
    except (ImportError, OSError, ValueError):
        return None


def run_single_profile(
    audio_path: Path,
    *,
    model: str,
    language: str,
    device: str,
    compute_type: str,
) -> dict[str, Any]:
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    engine = FasterWhisperTranscriptionEngine(
        model_size=model,
        device=device,
        compute_type=compute_type,
        language=None if language == "auto" else language,
    )
    segments = engine.transcribe(audio_path)
    payload = segments_to_jsonable(segments)
    return {
        "model": model,
        "language": language,
        "device": device,
        "compute_type": compute_type,
        "wall_seconds": round(time.monotonic() - started_wall, 3),
        "cpu_seconds": round(time.process_time() - started_cpu, 3),
        "peak_process_memory_mb": _peak_memory_mb(),
        "peak_vram_mb": None,
        "segments": payload,
    }


def build_run_summary(result: dict[str, Any], reference: str | None, keywords: Sequence[str]) -> dict[str, Any]:
    segments = list(result["segments"])
    text = transcript_text(segments)
    return {
        key: value for key, value in result.items() if key != "segments"
    } | {
        "raw_transcript_text_length": len(text),
        "character_error_rate": round(character_error_rate(reference, text), 6) if reference is not None else None,
        "keyword_metrics": keyword_metrics(text, keywords),
        "timestamp_metrics": timestamp_metrics(segments),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Transcription Accuracy Benchmark",
        "",
        "Raw faster-whisper output only. Transcript post-processing is not applied.",
        "",
        "| Profile | CER | Keywords | Segments | Wall | CPU | Peak RAM | Timestamp errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        keyword_data = run["keyword_metrics"]
        timestamp_data = run["timestamp_metrics"]
        keyword_value = f"{keyword_data['matched']}/{keyword_data['requested']}" if keyword_data["requested"] else "n/a"
        cer = "n/a" if run["character_error_rate"] is None else f"{run['character_error_rate']:.4f}"
        peak_memory = "n/a" if run["peak_process_memory_mb"] is None else f"{run['peak_process_memory_mb']:.1f} MB"
        timestamp_errors = timestamp_data["invalid_timestamp_ranges"] + timestamp_data["non_monotonic_timestamps"]
        lines.append(
            f"| {run['model']}:{run['language']} | {cer} | {keyword_value} | {timestamp_data['segment_count']} | "
            f"{run['wall_seconds']:.3f}s | {run['cpu_seconds']:.3f}s | {peak_memory} | {timestamp_errors} |"
        )
    lines.extend(
        [
            "",
            "Notes:",
            "- CER uses NFKC text with whitespace and punctuation removed.",
            "- First execution may include model download time. Re-run after models are cached for runtime comparison.",
            "- VRAM is reported as null when the runtime does not expose a reliable measurement.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark raw faster-whisper profiles without transcript post-processing.")
    parser.add_argument("--audio", type=Path, required=True, help="Path to a mono WAV accessible in the runtime.")
    parser.add_argument("--profile", action="append", default=[], help="Repeatable MODEL:LANGUAGE profile.")
    parser.add_argument("--reference-file", type=Path)
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--single-profile", help=argparse.SUPPRESS)
    parser.add_argument("--single-output", type=Path, help=argparse.SUPPRESS)
    return parser


def _run_child(args: argparse.Namespace, profile: str, output_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "app.audio.benchmark_transcription",
        "--audio",
        str(args.audio),
        "--output-dir",
        str(args.output_dir),
        "--device",
        args.device,
        "--compute-type",
        args.compute_type,
        "--single-profile",
        profile,
        "--single-output",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.audio = args.audio.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.audio.is_file():
        raise SystemExit(f"audio not found: {args.audio}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.single_profile:
        if args.single_output is None:
            raise SystemExit("--single-output is required with --single-profile")
        model, language = parse_profile(args.single_profile)
        result = run_single_profile(
            args.audio,
            model=model,
            language=language,
            device=args.device,
            compute_type=args.compute_type,
        )
        args.single_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    profiles = args.profile or list(DEFAULT_PROFILES)
    parsed_profiles = [parse_profile(profile) for profile in profiles]
    reference = args.reference_file.read_text(encoding="utf-8") if args.reference_file else None
    runs = []
    for model, language in parsed_profiles:
        label = profile_label(model, language)
        child_output = args.output_dir / f".{label}_result.json"
        _run_child(args, f"{model}:{language}", child_output)
        result = json.loads(child_output.read_text(encoding="utf-8"))
        child_output.unlink()
        raw_path = args.output_dir / f"{label}_raw_transcript_segments.json"
        raw_path.write_text(json.dumps(result["segments"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = build_run_summary(result, reference, args.keyword)
        summary["raw_transcript_path"] = str(raw_path)
        runs.append(summary)

    report = {
        "audio_path": str(args.audio),
        "reference_file": str(args.reference_file.resolve()) if args.reference_file else None,
        "post_processing_applied": False,
        "runs": runs,
    }
    json_path = args.output_dir / "transcription_benchmark_report.json"
    markdown_path = args.output_dir / "transcription_benchmark_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
