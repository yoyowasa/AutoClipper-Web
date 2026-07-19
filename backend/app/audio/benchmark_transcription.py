from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Sequence

from app.audio.transcript_postprocess import postprocess_transcript_segments
from app.audio.transcript_suspicion import analyze_transcript_suspicion
from app.audio.transcribe_faster_whisper import FasterWhisperTranscriptionEngine, TranscriptSegment, segments_to_jsonable


SUPPORTED_MODELS = {"base", "small", "medium", "large-v3", "turbo"}
SUPPORTED_LANGUAGES = {"auto", "ja"}
SUPPORTED_DEVICES = {"auto", "cpu", "cuda"}
SUPPORTED_COMPUTE_TYPES = {"auto", "int8", "float16", "int8_float16"}
DEFAULT_PROFILES = ("base:auto:cpu:int8", "base:ja:cpu:int8", "small:ja:cpu:int8", "medium:ja:cpu:int8")


def parse_profile(
    value: str,
    *,
    default_device: str = "cpu",
    default_compute_type: str = "int8",
) -> tuple[str, str, str, str]:
    parts = value.split(":")
    if len(parts) not in {2, 4}:
        raise argparse.ArgumentTypeError(
            "profile must be MODEL:LANGUAGE or MODEL:LANGUAGE:DEVICE:COMPUTE_TYPE"
        )
    model, language = parts[:2]
    device, compute_type = (
        (parts[2], parts[3])
        if len(parts) == 4
        else (default_device, default_compute_type)
    )
    if (
        model not in SUPPORTED_MODELS
        or language not in SUPPORTED_LANGUAGES
        or device not in SUPPORTED_DEVICES
        or compute_type not in SUPPORTED_COMPUTE_TYPES
    ):
        raise argparse.ArgumentTypeError(
            "unsupported transcription profile; use "
            "base|small|medium|large-v3|turbo, auto|ja, auto|cpu|cuda, "
            "and auto|int8|float16|int8_float16"
        )
    return model, language, device, compute_type


def profile_label(model: str, language: str, device: str, compute_type: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{model}_{language}_{device}_{compute_type}")


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
    diagnostics = engine.diagnostics
    return {
        "model": model,
        "language": language,
        "requested_device": device,
        "device": diagnostics.get("actual_device"),
        "requested_compute_type": compute_type,
        "compute_type": diagnostics.get("actual_compute_type"),
        "gpu_name": diagnostics.get("gpu_name"),
        "gpu_memory_total_mb": diagnostics.get("gpu_memory_total_mb"),
        "model_load_seconds": diagnostics.get("model_load_seconds"),
        "transcription_seconds": diagnostics.get("transcription_seconds"),
        "wall_seconds": round(time.monotonic() - started_wall, 3),
        "cpu_seconds": round(time.process_time() - started_cpu, 3),
        "peak_process_memory_mb": _peak_memory_mb(),
        "peak_vram_mb": diagnostics.get("peak_vram_mb"),
        "fallback_used": diagnostics.get("fallback_used"),
        "fallback_reason": diagnostics.get("fallback_reason"),
        "segments": payload,
    }


def build_run_summary(result: dict[str, Any], reference: str | None, keywords: Sequence[str]) -> dict[str, Any]:
    segments = list(result["segments"])
    text = transcript_text(segments)
    timestamps = timestamp_metrics(segments)
    audio_seconds = float(timestamps["last_segment_end"])
    transcription_seconds = float(result.get("transcription_seconds") or 0.0)
    return {
        key: value for key, value in result.items() if key != "segments"
    } | {
        "raw_transcript_text_length": len(text),
        "character_error_rate": round(character_error_rate(reference, text), 6) if reference is not None else None,
        "keyword_metrics": keyword_metrics(text, keywords),
        "timestamp_metrics": timestamps,
        "transcription_realtime_factor": (
            round(transcription_seconds / audio_seconds, 6) if audio_seconds > 0 else None
        ),
    }


def estimate_text_token_proxy(text: str) -> int:
    japanese_character_count = sum(
        (
            "\u3040" <= character <= "\u30ff"
            or "\u3400" <= character <= "\u4dbf"
            or "\u4e00" <= character <= "\u9fff"
        )
        for character in text
    )
    other_character_count = sum(
        not character.isspace()
        and not (
            "\u3040" <= character <= "\u30ff"
            or "\u3400" <= character <= "\u4dbf"
            or "\u4e00" <= character <= "\u9fff"
        )
        for character in text
    )
    return japanese_character_count + math.ceil(other_character_count / 4)


def build_local_correction_demand_metrics(
    segments: Sequence[TranscriptSegment],
    *,
    threshold: float,
    context_segments: int,
    batch_size: int,
    glossary: Sequence[str],
) -> dict[str, Any]:
    suspicion = analyze_transcript_suspicion(
        segments,
        threshold=threshold,
        context_segments=context_segments,
        batch_size=batch_size,
        glossary=glossary,
    )
    targets = set(suspicion.target_indices)
    context = set(suspicion.context_indices)
    sent_indices = targets | context
    input_text_chars = sum(len(segments[index].text) for index in sent_indices)
    input_text_token_proxy = sum(
        estimate_text_token_proxy(segments[index].text) for index in sent_indices
    )
    total_text_chars = sum(len(segment.text) for segment in segments)
    total_speech_seconds = sum(max(0.0, segment.end - segment.start) for segment in segments)
    target_speech_seconds = sum(
        max(0.0, segment.end - segment.start)
        for index, segment in enumerate(segments)
        if index in targets
    )
    return suspicion.summary() | {
        "target_speech_seconds": round(target_speech_seconds, 3),
        "target_speech_ratio": (
            round(target_speech_seconds / total_speech_seconds, 6)
            if total_speech_seconds > 0
            else 0.0
        ),
        "input_text_char_proxy": input_text_chars,
        "input_text_char_ratio": (
            round(input_text_chars / total_text_chars, 6) if total_text_chars > 0 else 0.0
        ),
        "input_text_token_proxy": input_text_token_proxy,
        "token_proxy_method": "japanese_char_plus_other_chars_div_4",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Transcription Accuracy Benchmark",
        "",
        "Raw faster-whisper and deterministic post-processing are compared. OpenAI correction is not applied.",
        "",
        "| Profile | Runtime | Raw CER | Deterministic CER | Keywords | Suspicious | Calls | Token proxy | RTF | Transcribe | Peak VRAM |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        keyword_data = run["keyword_metrics"]
        keyword_value = f"{keyword_data['matched']}/{keyword_data['requested']}" if keyword_data["requested"] else "n/a"
        cer = "n/a" if run["character_error_rate"] is None else f"{run['character_error_rate']:.4f}"
        peak_vram = "n/a" if run["peak_vram_mb"] is None else f"{run['peak_vram_mb']} MB"
        deterministic_cer = (
            "n/a"
            if run["deterministic_character_error_rate"] is None
            else f"{run['deterministic_character_error_rate']:.4f}"
        )
        demand = run["local_correction_demand"]
        lines.append(
            f"| {run['model']}:{run['language']} | {run['device']}:{run['compute_type']} | "
            f"{cer} | {deterministic_cer} | {keyword_value} | "
            f"{demand['suspicious_segment_count']}/{demand['segment_count']} | "
            f"{demand['estimated_api_calls']} | {demand['input_text_token_proxy']} | "
            f"{run['transcription_realtime_factor']:.4f} | "
            f"{run['transcription_seconds']:.3f}s | {peak_vram} |"
        )
    lines.extend(
        [
            "",
            "Notes:",
            "- CER uses NFKC text with whitespace and punctuation removed.",
            "- First execution may include model download time. Re-run after models are cached for runtime comparison.",
            "- VRAM is reported as null when the runtime does not expose a reliable measurement.",
            "- Token proxy is a local text-only estimate; it excludes prompt, schema, reasoning, and output tokens.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark faster-whisper runtime, raw accuracy, deterministic accuracy, and correction demand."
    )
    parser.add_argument("--audio", type=Path, required=True, help="Path to a mono WAV accessible in the runtime.")
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Repeatable MODEL:LANGUAGE or MODEL:LANGUAGE:DEVICE:COMPUTE_TYPE profile.",
    )
    parser.add_argument("--reference-file", type=Path)
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--suspicion-threshold", type=float, default=0.4)
    parser.add_argument("--suspicion-context-segments", type=int, default=2)
    parser.add_argument("--suspicion-batch-size", type=int, default=100)
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
        model, language, device, compute_type = parse_profile(
            args.single_profile,
            default_device=args.device,
            default_compute_type=args.compute_type,
        )
        result = run_single_profile(
            args.audio,
            model=model,
            language=language,
            device=device,
            compute_type=compute_type,
        )
        args.single_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    profiles = args.profile or list(DEFAULT_PROFILES)
    parsed_profiles = [
        parse_profile(
            profile,
            default_device=args.device,
            default_compute_type=args.compute_type,
        )
        for profile in profiles
    ]
    reference = args.reference_file.read_text(encoding="utf-8") if args.reference_file else None
    runs = []
    for model, language, device, compute_type in parsed_profiles:
        label = profile_label(model, language, device, compute_type)
        child_output = args.output_dir / f".{label}_result.json"
        _run_child(
            args,
            f"{model}:{language}:{device}:{compute_type}",
            child_output,
        )
        result = json.loads(child_output.read_text(encoding="utf-8"))
        child_output.unlink()
        segments = [TranscriptSegment.model_validate(segment) for segment in result["segments"]]
        raw_path = args.output_dir / f"{label}_raw_transcript_segments.json"
        raw_path.write_text(json.dumps(result["segments"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        postprocess_result = postprocess_transcript_segments(segments)
        deterministic_payload = segments_to_jsonable(postprocess_result.segments)
        deterministic_path = args.output_dir / f"{label}_deterministic_transcript_segments.json"
        deterministic_path.write_text(
            json.dumps(deterministic_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary = build_run_summary(result, reference, args.keyword)
        summary["raw_transcript_path"] = str(raw_path)
        deterministic_text = transcript_text(postprocess_result.segments)
        summary["deterministic_character_error_rate"] = (
            round(character_error_rate(reference, deterministic_text), 6)
            if reference is not None
            else None
        )
        summary["deterministic_keyword_metrics"] = keyword_metrics(deterministic_text, args.keyword)
        summary["deterministic_transcript_path"] = str(deterministic_path)
        summary["postprocess_changed_segment_count"] = postprocess_result.summary["changed_segment_count"]
        summary["local_correction_demand"] = build_local_correction_demand_metrics(
            postprocess_result.segments,
            threshold=max(0.0, min(1.0, args.suspicion_threshold)),
            context_segments=max(0, args.suspicion_context_segments),
            batch_size=max(1, args.suspicion_batch_size),
            glossary=args.keyword,
        )
        runs.append(summary)

    report = {
        "audio_path": str(args.audio),
        "reference_file": str(args.reference_file.resolve()) if args.reference_file else None,
        "post_processing_applied": False,
        "deterministic_post_processing_evaluated": True,
        "openai_correction_applied": False,
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
