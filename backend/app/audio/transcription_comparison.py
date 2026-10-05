"""Offline comparison tool; it never writes job data or changes production settings."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
import json
from pathlib import Path
import tempfile
import time
from typing import Any
import wave

from app.audio.benchmark_transcription import normalize_for_cer, timestamp_metrics
from app.audio.transcript_repair_merge import merge_ranges, subtract_ranges, subtitle_gaps, nonsilent_gaps, merge_repair
from app.audio.transcribe_faster_whisper import _write_pcm_wav_chunk
from app.audio.transcription_runtime import NvidiaMemorySampler
from app.storage.json_io import write_json_atomic


METHODS = ("A", "B", "C8", "C16", "D")
PHANTOM_PHRASES = ("ご視聴ありがとうございました", "ご視聴ありがとうございます", "チャンネル登録", "高評価", "字幕をご覧")
Range = tuple[float, float]
Segment = dict[str, Any]


def load_silence_ranges(path: Path, duration: float) -> list[Range]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("silence_segments.json must contain a list")
    return merge_ranges([
        (max(0.0, float(item["start"])), min(duration, float(item["end"])))
        for item in payload
    ])


def _range_payload(ranges: Sequence[Range]) -> list[dict[str, float]]:
    return [{"start": round(start, 6), "end": round(end, 6), "duration": round(end - start, 6)} for start, end in ranges]


def _nonsilent_seconds(start: float, end: float, silence: Sequence[Range]) -> float:
    return sum(stop - begin for begin, stop in subtract_ranges([(start, end)], silence))


def repeated_text_runs(segments: Sequence[Segment]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    start_index = 0
    while start_index < len(segments):
        normalized = normalize_for_cer(str(segments[start_index].get("text", "")))
        end_index = start_index + 1
        while end_index < len(segments) and normalize_for_cer(str(segments[end_index].get("text", ""))) == normalized:
            end_index += 1
        if normalized and end_index - start_index >= 3:
            runs.append({
                "text": str(segments[start_index]["text"]), "count": end_index - start_index,
                "start": float(segments[start_index]["start"]), "end": float(segments[end_index - 1]["end"]),
            })
        start_index = end_index
    return runs


def start_time_shifts(segments: Sequence[Segment], baseline: Sequence[Segment]) -> dict[str, Any]:
    """Align identical normalized sentences in order, excluding insertions/deletions."""
    normalized = [normalize_for_cer(str(item.get("text", ""))) for item in segments]
    baseline_normalized = [normalize_for_cer(str(item.get("text", ""))) for item in baseline]
    matcher = SequenceMatcher(None, baseline_normalized, normalized, autojunk=False)
    shifts: list[dict[str, Any]] = []
    matched_count = 0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            old = baseline[block.a + offset]
            current = segments[block.b + offset]
            if not normalized[block.b + offset]:
                continue
            matched_count += 1
            delta = float(current["start"]) - float(old["start"])
            if abs(delta) >= 1.0:
                shifts.append({
                    "text": current["text"], "baseline_start": old["start"], "start": current["start"],
                    "delta_seconds": round(delta, 6),
                })
    return {
        "method": "ordered_exact_normalized_text_alignment", "matched_segment_count": matched_count,
        "shifted_ge_1_second_count": len(shifts), "shifts": shifts,
        "limitation": "Different segmentation or wording is not matched; a shift is not proof of a timestamp error.",
    }


def word_audio_gap_metrics(
    segments: Sequence[Segment], *, duration: float, silence: Sequence[Range],
) -> dict[str, Any] | None:
    """Use word coverage to avoid depending on the model's segment granularity."""
    if any(not isinstance(segment.get("words"), list) for segment in segments):
        return None
    words = [word for segment in segments for word in segment["words"]]
    if any(not all(key in word for key in ("start", "end", "word")) for word in words):
        return None
    covered = [
        {"start": word["start"], "end": word["end"], "text": word["word"]}
        for word in words
    ]
    gaps: dict[str, Any] = {}
    for threshold in (3, 5):
        ranges = nonsilent_gaps(covered, duration, silence, threshold)
        gaps[f"ge_{threshold}_seconds"] = {
            "count": len(ranges), "total_seconds": round(sum(end - start for start, end in ranges), 6),
            "intervals": _range_payload(ranges),
        }
    return gaps


def build_metrics(
    segments: Sequence[Segment], *, duration: float, silence: Sequence[Range], baseline: Sequence[Segment] | None = None,
) -> dict[str, Any]:
    gaps: dict[str, Any] = {}
    for threshold in (3, 5):
        ranges = nonsilent_gaps(segments, duration, silence, threshold)
        gaps[f"ge_{threshold}_seconds"] = {
            "count": len(ranges), "total_seconds": round(sum(end - start for start, end in ranges), 6),
            "intervals": _range_payload(ranges),
        }
    raw_gaps = []
    for start, end in subtitle_gaps(segments, duration):
        if end - start >= 3:
            sound = _nonsilent_seconds(start, end, silence)
            raw_gaps.append({
                "start": start, "end": end, "duration": end - start, "nonsilent_seconds": sound,
                "nonsilent_ratio": sound / (end - start),
            })
    phantom_events = []
    for segment in segments:
        normalized = normalize_for_cer(str(segment.get("text", "")))
        for phrase in PHANTOM_PHRASES:
            count = normalized.count(normalize_for_cer(phrase))
            if not count:
                continue
            start, end = float(segment["start"]), float(segment["end"])
            seconds = max(0.0, end - start)
            silence_ratio = 1 - _nonsilent_seconds(start, end, silence) / seconds if seconds else 0.0
            phantom_events.append({
                "phrase": phrase, "occurrences": count, "text": segment["text"], "start": start, "end": end,
                "silence_ratio": silence_ratio, "in_majority_silence": silence_ratio >= 0.5,
            })
    repetitions = repeated_text_runs(segments)
    return {
        "gap_definition": "Contiguous non-silent portions of subtitle-free intervals; silence intervals are subtracted first.",
        "audio_gaps": gaps, "subtitle_free_intervals_ge_3_seconds": raw_gaps,
        "word_audio_gaps": word_audio_gap_metrics(segments, duration=duration, silence=silence),
        "word_gap_definition": (
            "Contiguous non-silent portions not covered by nonempty word timestamps; silence intervals are subtracted first."
        ),
        "word_gap_limitation": (
            "Unavailable (null) if any segment lacks word timestamps. Word timing errors can change these counts; "
            "non-silence can be BGM, not necessarily omitted speech."
        ),
        "total_text_characters": sum(len(str(item.get("text", "")).strip()) for item in segments),
        "timestamp_metrics": timestamp_metrics(segments),
        "phantom_phrase_occurrences": sum(item["occurrences"] for item in phantom_events),
        "phantom_phrase_occurrences_in_majority_silence": sum(
            item["occurrences"] for item in phantom_events if item["in_majority_silence"]
        ),
        "phantom_phrase_events": phantom_events,
        "phantom_phrase_occurrences_in_bgm_only": None,
        "phantom_phrase_limitation": (
            "Phrase matches are suspicions, not verified errors. Silence detection cannot distinguish BGM from speech."
        ),
        "repeated_text_run_count": len(repetitions), "repeated_text_runs": repetitions,
        "baseline_start_time_comparison": start_time_shifts(segments, baseline) if baseline is not None else None,
    }


def segment_payload(segment: Any, *, offset: float = 0.0) -> Segment:
    result: Segment = {
        "start": float(segment.start) + offset, "end": float(segment.end) + offset, "text": str(segment.text).strip(),
        "avg_logprob": float(segment.avg_logprob), "no_speech_prob": float(segment.no_speech_prob),
        "compression_ratio": float(segment.compression_ratio),
        "words": [
            {"start": float(word.start) + offset, "end": float(word.end) + offset,
             "word": str(word.word), "probability": float(word.probability)}
            for word in (segment.words or [])
        ],
    }
    return result


def repair_windows(segments: Sequence[Segment], duration: float, silence: Sequence[Range]) -> list[Range]:
    return merge_ranges([
        (max(0.0, start - 2), min(duration, end + 2))
        for start, end in nonsilent_gaps(segments, duration, silence, 3.0)
    ])


def repair_transcript(
    audio_path: Path, model: Any, baseline: Sequence[Segment], *, duration: float, silence: Sequence[Range],
    progress: Callable[[str], None] = print,
) -> tuple[list[Segment], dict[str, Any]]:
    gaps = nonsilent_gaps(baseline, duration, silence, 3.0)
    windows = repair_windows(baseline, duration, silence)
    current = [dict(segment) for segment in baseline]
    details = []
    with wave.open(str(audio_path), "rb") as reader, tempfile.TemporaryDirectory(prefix="transcription-repair-") as directory:
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or reader.getframerate() != 16000:
            raise ValueError("D requires mono 16 kHz PCM signed 16-bit WAV")
        rate = reader.getframerate()
        for index, (start, end) in enumerate(windows):
            progress(f"repair {index + 1}/{len(windows)}: {start:.3f}-{end:.3f}s")
            path = Path(directory) / "repair.wav"
            start_frame = int(start * rate)
            end_frame = min(reader.getnframes(), int(end * rate))
            _write_pcm_wav_chunk(reader, path, start_frame=start_frame, frame_count=end_frame - start_frame)
            actual_offset = start_frame / rate
            segments, _ = model.transcribe(
                str(path), language="ja", beam_size=5, word_timestamps=True,
                vad_filter=False, condition_on_previous_text=False,
            )
            reread = [segment_payload(segment, offset=actual_offset) for segment in segments]
            current, changes = merge_repair(current, reread, window=(start, end), gaps=gaps)
            details.append({"start": start, "end": end, "reread_segments": reread, **changes})
    return current, {
        "merge_policy": "uncovered_word_centers_v2",
        "window_count": len(windows), "windows": details, "target_gaps": _range_payload(gaps),
    }


def run_comparison(
    audio_path: Path, *, silence_path: Path, duration: float, method: str, model_path: Path,
    compute_type: str = "float16", device: str = "cuda", baseline_path: Path | None = None,
) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method}")
    if duration <= 0:
        raise ValueError("duration must be positive")
    if not model_path.is_dir() or not (model_path / "model.bin").is_file():
        raise ValueError("--model-path must be an existing faster-whisper model directory; downloading is disabled")
    baseline_result = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path else None
    if baseline_result is not None and baseline_result.get("status") != "completed":
        raise ValueError("baseline must be a completed comparison result")
    if method == "D" and (baseline_result is None or baseline_result.get("method") != "A"):
        raise ValueError("D requires the completed A result as --baseline-json")
    if baseline_result is not None and abs(float(baseline_result.get("duration_seconds", duration)) - duration) > 0.01:
        raise ValueError("baseline duration does not match the compared audio")
    baseline = baseline_result["segments"] if baseline_result else None
    silence = load_silence_ranges(silence_path, duration)
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    started = time.monotonic()
    sampler = NvidiaMemorySampler(enabled=device == "cuda")
    sampler.start()
    try:
        model_started = time.monotonic()
        model = WhisperModel(str(model_path), device=device, compute_type=compute_type, local_files_only=True)
        load_seconds = time.monotonic() - model_started
        transcribe_started = time.monotonic()
        options: dict[str, Any] = {"language": "ja", "beam_size": 5, "word_timestamps": True}
        repairs = None
        if method == "D":
            options.update(vad_filter=False, condition_on_previous_text=False)
            payload, repairs = repair_transcript(audio_path, model, baseline, duration=duration, silence=silence)
        else:
            if method in {"C8", "C16"}:
                options.update(vad_filter=True, batch_size=int(method[1:]))
                engine = BatchedInferencePipeline(model=model)
            else:
                options["vad_filter"] = False
                if method == "B":
                    options["condition_on_previous_text"] = False
                engine = model
            segments, info = engine.transcribe(str(audio_path), **options)
            payload = []
            for index, segment in enumerate(segments):
                payload.append(segment_payload(segment))
                if index % 100 == 0:
                    print(f"{method}: {index + 1} segments, end {segment.end:.1f}/{duration:.1f}s", flush=True)
            options["resolved_condition_on_previous_text"] = info.transcription_options.condition_on_previous_text
        transcribe_seconds = time.monotonic() - transcribe_started
    finally:
        peak_vram = sampler.stop()
    metrics = build_metrics(payload, duration=duration, silence=silence, baseline=baseline)
    return {
        "schema_version": 1, "status": "completed", "method": method,
        "model": "turbo", "model_path": str(model_path), "device": device, "compute_type": compute_type,
        "audio_path": str(audio_path), "silence_path": str(silence_path), "duration_seconds": duration,
        "options": options, "postprocessing_applied": False,
        "model_load_seconds": round(load_seconds, 3), "transcription_seconds": round(transcribe_seconds, 3),
        "wall_seconds": round(time.monotonic() - started, 3), "peak_vram_mb": peak_vram,
        "peak_vram_scope": "Whole first visible GPU sampled every 0.5 seconds, not process-exclusive; null if nvidia-smi unavailable.",
        "baseline_wall_seconds": baseline_result.get("wall_seconds") if method == "D" else None,
        "baseline_peak_vram_mb": baseline_result.get("peak_vram_mb") if method == "D" else None,
        "total_pipeline_peak_vram_mb": (
            max(value for value in (peak_vram, baseline_result.get("peak_vram_mb")) if value is not None)
            if method == "D" and (peak_vram is not None or baseline_result.get("peak_vram_mb") is not None)
            else peak_vram
        ),
        "total_pipeline_wall_seconds": round(
            time.monotonic() - started + (float(baseline_result["wall_seconds"]) if method == "D" else 0), 3,
        ),
        "segments": payload, "metrics": metrics, "repairs": repairs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--silence-json", type=Path, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--compute-type", choices=("float16", "int8_float16", "int8", "float32"), default="float16")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # A killed/failed invocation never publishes a completed JSON.
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing result: {args.output}")
    result = run_comparison(
        args.audio, silence_path=args.silence_json, duration=args.duration, method=args.method,
        model_path=args.model_path, compute_type=args.compute_type, device=args.device, baseline_path=args.baseline_json,
    )
    write_json_atomic(args.output, result)
    print(args.output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
