from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.audio.benchmark_subtitle_correction import load_segments, load_target_indices
from app.audio.transcript_correction_schema import (
    CorrectionReason,
    CorrectedTranscriptSegment,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_postprocess import DEFAULT_TRANSCRIPT_REPLACEMENTS
from app.audio.transcript_suspicion import (
    analyze_transcript_suspicion,
    select_read_only_context_indices,
)


SYSTEM_PROMPT = """You correct ASR errors in Japanese subtitle text.
Return only JSON that matches the supplied schema.
Do not summarize, paraphrase, improve style, or add information.
Do not merge, split, reorder, add, or remove segments.
The input is text only. Never claim to have heard audio.
Preserve fillers and conversational tone unless text is clearly an ASR error.
Only correct wording strongly supported by the supplied context.
For unchanged text, copy the supplied text exactly into corrected_text and set reason=unchanged.
For changed text, preserve meaning and make the smallest possible correction.
"""

LATIN_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]+")
KATAKANA_RE = re.compile(r"[ァ-ヴー]{2,}")
NUMBER_RE = re.compile(r"\d|[０-９]|[一二三四五六七八九十百千万億兆]+(?:円|人|年|月|日|時|分|秒|%|％)")
PUNCTUATION_RE = re.compile(r"[\s、。！？!?・「」『』（）()\[\]【】，,.…:：;；'\"“”‘’]")
KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff々〆ヶ]")
HIRAGANA_RE = re.compile(r"^[ぁ-ゖゝゞー]+$")


@dataclass(frozen=True)
class OllamaOptions:
    model: str
    base_url: str
    num_ctx: int
    temperature: float
    seed: int
    timeout_seconds: float


@dataclass(frozen=True)
class SafetyDecision:
    action: str
    reason: str


class LocalCorrectedTranscriptSegment(BaseModel):
    index: int = Field(ge=0)
    corrected_text: str
    reason: CorrectionReason
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class LocalTranscriptCorrectionBatch(BaseModel):
    segments: list[LocalCorrectedTranscriptSegment]

    model_config = ConfigDict(extra="forbid")


JsonRequest = Callable[[str, str, Mapping[str, Any] | None, float], dict[str, Any]]


def ollama_json_request(
    base_url: str,
    path: str,
    payload: Mapping[str, Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama connection failed: {exc.reason}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama response must be a JSON object")
    return result


class VramMonitor:
    def __init__(self, *, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self.samples_mib: list[int] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.samples_mib.append(sum(int(value.strip()) for value in result.stdout.splitlines() if value.strip()))
            except (FileNotFoundError, subprocess.SubprocessError, ValueError):
                return
            self._stop.wait(self.interval_seconds)

    def __enter__(self) -> VramMonitor:
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def summary(self) -> dict[str, int | None]:
        if not self.samples_mib:
            return {"baseline_mib": None, "peak_mib": None, "increase_mib": None}
        baseline = self.samples_mib[0]
        peak = max(self.samples_mib)
        return {
            "baseline_mib": baseline,
            "peak_mib": peak,
            "increase_mib": max(0, peak - baseline),
        }


def _validate_batch(
    corrected: Sequence[LocalCorrectedTranscriptSegment],
    targets: Sequence[tuple[int, TranscriptSegment]],
) -> None:
    expected = {index: segment.text for index, segment in targets}
    received = {item.index: item for item in corrected}
    if len(received) != len(corrected) or set(received) != set(expected):
        missing = sorted(set(expected) - set(received))
        unexpected = sorted(set(received) - set(expected))
        raise ValueError(
            "local correction response indices do not match target indices: "
            f"expected={len(expected)}, received={len(corrected)}, "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}"
        )
    for index, original_text in expected.items():
        item = received[index]
        if item.corrected_text != original_text and not item.corrected_text.strip():
            raise ValueError(f"changed correction is blank at index {index}")


def local_correction_json_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["index", "corrected_text", "reason", "confidence"],
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "corrected_text": {"type": "string"},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "unchanged",
                                "proper_noun",
                                "homophone",
                                "punctuation",
                                "numeric_expression",
                                "asr_error",
                            ],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    }


def _build_user_payload(
    segments: Sequence[TranscriptSegment],
    *,
    batch_indices: Sequence[int],
    context_segments: int,
    glossary: Sequence[str],
) -> dict[str, Any]:
    context_indices = select_read_only_context_indices(
        batch_indices,
        segment_count=len(segments),
        context_segments=context_segments,
    )
    return {
        "target_segments": [{"index": index, "original_text": segments[index].text} for index in batch_indices],
        "read_only_context_segments": [
            {"index": index, "text": segments[index].text} for index in context_indices
        ],
        "preferred_terms": list(dict.fromkeys(term for term in glossary if term.strip())),
    }


def run_ollama_correction(
    segments: Sequence[TranscriptSegment],
    *,
    target_indices: Sequence[int],
    batch_size: int,
    context_segments: int,
    glossary: Sequence[str],
    options: OllamaOptions,
    request_json: JsonRequest = ollama_json_request,
) -> dict[str, Any]:
    started_at = time.monotonic()
    outputs: dict[int, CorrectedTranscriptSegment] = {}
    input_text_chars = 0
    output_text_chars = 0
    prompt_eval_count = 0
    eval_count = 0
    load_duration_ns = 0
    prompt_eval_duration_ns = 0
    eval_duration_ns = 0
    batch_count = 0
    semantic_normalization_count = 0
    with VramMonitor() as vram_monitor:
        for batch_start in range(0, len(target_indices), batch_size):
            batch_indices = list(target_indices[batch_start : batch_start + batch_size])
            targets = [(index, segments[index]) for index in batch_indices]
            user_payload = _build_user_payload(
                segments,
                batch_indices=batch_indices,
                context_segments=context_segments,
                glossary=glossary,
            )
            user_content = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
            input_text_chars += len(SYSTEM_PROMPT) + len(user_content)
            response = request_json(
                options.base_url,
                "/api/chat",
                {
                    "model": options.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "stream": False,
                    "think": False,
                    "format": local_correction_json_schema(len(targets)),
                    "options": {
                        "temperature": options.temperature,
                        "seed": options.seed,
                        "num_ctx": options.num_ctx,
                    },
                },
                options.timeout_seconds,
            )
            message = response.get("message")
            content = message.get("content") if isinstance(message, Mapping) else None
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("Ollama response did not include message.content")
            output_text_chars += len(content)
            batch = LocalTranscriptCorrectionBatch.model_validate(json.loads(content))
            _validate_batch(batch.segments, targets)
            for item in batch.segments:
                if item.index in outputs:
                    raise ValueError(f"duplicate output index across batches: {item.index}")
                original_text = segments[item.index].text
                changed = item.corrected_text != original_text
                normalized_reason = item.reason
                if not changed and normalized_reason != "unchanged":
                    normalized_reason = "unchanged"
                    semantic_normalization_count += 1
                elif changed and normalized_reason == "unchanged":
                    normalized_reason = (
                        "punctuation" if _punctuation_only(original_text, item.corrected_text) else "asr_error"
                    )
                    semantic_normalization_count += 1
                outputs[item.index] = CorrectedTranscriptSegment(
                    index=item.index,
                    original_text=original_text,
                    corrected_text=item.corrected_text,
                    changed=changed,
                    reason=normalized_reason,
                    confidence=item.confidence,
                )
            prompt_eval_count += int(response.get("prompt_eval_count", 0) or 0)
            eval_count += int(response.get("eval_count", 0) or 0)
            load_duration_ns += int(response.get("load_duration", 0) or 0)
            prompt_eval_duration_ns += int(response.get("prompt_eval_duration", 0) or 0)
            eval_duration_ns += int(response.get("eval_duration", 0) or 0)
            batch_count += 1
    if set(outputs) != set(target_indices):
        raise ValueError("local correction did not return every target index exactly once")
    ordered = [outputs[index] for index in target_indices]
    return {
        "segments": [item.model_dump() for item in ordered],
        "metrics": {
            "target_count": len(target_indices),
            "batch_count": batch_count,
            "semantic_normalization_count": semantic_normalization_count,
            "input_text_chars": input_text_chars,
            "output_text_chars": output_text_chars,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
            "processing_seconds": round(time.monotonic() - started_at, 6),
            "load_seconds": round(load_duration_ns / 1_000_000_000, 6),
            "prompt_eval_seconds": round(prompt_eval_duration_ns / 1_000_000_000, 6),
            "eval_seconds": round(eval_duration_ns / 1_000_000_000, 6),
            "vram": vram_monitor.summary(),
        },
    }


def _dictionary_correction(original: str, corrected: str, replacements: Mapping[str, str]) -> bool:
    result = original
    for source, target in sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True):
        result = result.replace(source, target)
    return result == corrected and result != original


def _punctuation_only(original: str, corrected: str) -> bool:
    return PUNCTUATION_RE.sub("", original) == PUNCTUATION_RE.sub("", corrected)


def _changed_spans(original: str, corrected: str) -> list[str]:
    spans: list[str] = []
    for operation, start_a, end_a, start_b, end_b in SequenceMatcher(None, original, corrected).get_opcodes():
        if operation != "equal":
            spans.extend((original[start_a:end_a], corrected[start_b:end_b]))
    return [span for span in spans if span]


def correction_safety_decision(
    original: str,
    corrected: str,
    *,
    reason: str,
    glossary: Sequence[str],
    replacements: Mapping[str, str] = DEFAULT_TRANSCRIPT_REPLACEMENTS,
) -> SafetyDecision:
    if corrected == original:
        return SafetyDecision("escalate", "unresolved_unchanged")
    if _dictionary_correction(original, corrected, replacements):
        return SafetyDecision("accept_local", "trusted_dictionary_replacement")
    if _punctuation_only(original, corrected):
        return SafetyDecision("escalate", "punctuation_only_does_not_resolve_suspicion")
    if unicodedata.normalize("NFKC", original) == unicodedata.normalize("NFKC", corrected):
        return SafetyDecision("accept_local", "width_normalization_only")
    if reason == "proper_noun":
        return SafetyDecision("escalate", "model_marked_proper_noun")
    if reason == "numeric_expression":
        return SafetyDecision("escalate", "model_marked_numeric_expression")
    if NUMBER_RE.search(original) or NUMBER_RE.search(corrected):
        return SafetyDecision("escalate", "numeric_or_unit_change")
    if LATIN_RE.search(original) or LATIN_RE.search(corrected):
        return SafetyDecision("escalate", "latin_token_change")
    if KATAKANA_RE.search(original) or KATAKANA_RE.search(corrected):
        return SafetyDecision("escalate", "katakana_token_change")
    if any((term in original) != (term in corrected) for term in glossary if term.strip()):
        return SafetyDecision("escalate", "glossary_conflict")
    ratio = SequenceMatcher(None, original, corrected).ratio()
    if ratio < 0.9:
        return SafetyDecision("escalate", "large_edit_distance")
    spans = _changed_spans(original, corrected)
    if any(KANJI_RE.search(span) for span in spans):
        return SafetyDecision("escalate", "kanji_change")
    if spans and all(HIRAGANA_RE.fullmatch(span) for span in spans):
        return SafetyDecision("accept_local", "small_hiragana_change")
    return SafetyDecision("escalate", "unclassified_text_change")


def apply_safety_gate(outputs: Sequence[Mapping[str, Any]], *, glossary: Sequence[str]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    accepted: list[int] = []
    escalated: list[int] = []
    reason_counts: Counter[str] = Counter()
    for raw in outputs:
        item = CorrectedTranscriptSegment.model_validate(raw)
        decision = correction_safety_decision(
            item.original_text,
            item.corrected_text,
            reason=item.reason,
            glossary=glossary,
        )
        reason_counts[decision.reason] += 1
        (accepted if decision.action == "accept_local" else escalated).append(item.index)
        decisions.append(
            {
                "index": item.index,
                "original_text": item.original_text,
                "corrected_text": item.corrected_text,
                "changed": item.changed,
                "model_reason": item.reason,
                "action": decision.action,
                "gate_reason": decision.reason,
            }
        )
    return {
        "decisions": decisions,
        "accepted_indices": accepted,
        "escalated_indices": escalated,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _target_text_chars(segments: Sequence[TranscriptSegment], indices: Sequence[int]) -> int:
    return sum(len(segments[index].text) for index in indices)


def _reduction_percent(baseline: int, candidate: int) -> float:
    return round((1 - candidate / baseline) * 100, 6) if baseline > 0 else 0.0


def evaluate_task65_review(
    outputs: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
    review_csv: Path,
) -> dict[str, Any]:
    by_index = {int(item["index"]): item for item in outputs}
    accepted = set(int(index) for index in gate["accepted_indices"])
    counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    with review_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("default_label") or row.get("none_label") or row.get("preferred_output") or row.get("notes")
        ]
    for row in rows:
        index = int(row["index"])
        item = by_index.get(index)
        if item is None:
            counts["missing_output"] += 1
            continue
        preferred = row.get("preferred_output", "").strip()
        expected = row.get("default_output", "") if preferred == "default" else row.get("none_output", "")
        if preferred not in {"default", "none"}:
            expected = ""
        if index not in accepted:
            classification = "escalated"
        elif expected and str(item["corrected_text"]) == expected:
            classification = "accepted_expected"
        else:
            classification = "unsafe_local_accept"
        counts[classification] += 1
        details.append(
            {
                "index": index,
                "source_text": row.get("source_text", ""),
                "local_output": item["corrected_text"],
                "expected_output": expected or None,
                "preferred_output": preferred or None,
                "term_types": row.get("term_types", ""),
                "classification": classification,
            }
        )
    total = len(rows)
    safely_handled = counts["escalated"] + counts["accepted_expected"]
    return {
        "reviewed_count": total,
        "escalated_count": counts["escalated"],
        "accepted_expected_count": counts["accepted_expected"],
        "unsafe_local_accept_count": counts["unsafe_local_accept"],
        "missing_output_count": counts["missing_output"],
        "safe_handling_rate": round(safely_handled / total, 6) if total else None,
        "details": details,
    }


def evaluate_reference_review(
    outputs: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
    *,
    changes_path: Path,
    review_path: Path,
    profile_label: str,
) -> dict[str, Any]:
    changes = json.loads(changes_path.read_text(encoding="utf-8"))
    expected_by_index = {int(change["index"]): str(change["after"]) for change in changes}
    review = json.loads(review_path.read_text(encoding="utf-8"))
    profile = review.get("profiles", {}).get(profile_label, {})
    useful_indices = {int(index) for index in profile.get("useful_corrections", [])}
    expected_useful = {index: expected_by_index[index] for index in useful_indices if index in expected_by_index}
    by_index = {int(item["index"]): item for item in outputs}
    accepted = set(int(index) for index in gate["accepted_indices"])
    correct_local = [
        index
        for index, expected in expected_useful.items()
        if index in accepted and by_index.get(index, {}).get("corrected_text") == expected
    ]
    unsafe_local = [
        index
        for index in accepted
        if index in expected_useful and by_index.get(index, {}).get("corrected_text") != expected_useful[index]
    ]
    return {
        "known_useful_count": len(expected_useful),
        "accepted_known_useful_count": len(correct_local),
        "accepted_known_useful_indices": sorted(correct_local),
        "unsafe_known_useful_indices": sorted(unsafe_local),
        "known_useful_escalated_count": len(set(expected_useful) - set(correct_local) - set(unsafe_local)),
    }


def _model_metadata(options: OllamaOptions, *, request_json: JsonRequest = ollama_json_request) -> dict[str, Any]:
    version = request_json(options.base_url, "/api/version", None, options.timeout_seconds)
    tags = request_json(options.base_url, "/api/tags", None, options.timeout_seconds)
    models = tags.get("models", [])
    model = next(
        (
            item
            for item in models
            if isinstance(item, Mapping) and str(item.get("name", "")) in {options.model, f"{options.model}:latest"}
        ),
        None,
    )
    return {
        "ollama_version": version.get("version"),
        "name": model.get("name") if isinstance(model, Mapping) else options.model,
        "digest": model.get("digest") if isinstance(model, Mapping) else None,
        "size_bytes": model.get("size") if isinstance(model, Mapping) else None,
        "details": model.get("details") if isinstance(model, Mapping) else None,
    }


def _gpu_metadata() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        name, driver, memory = [value.strip() for value in result.stdout.splitlines()[0].split(",")]
        return {"name": name, "driver": driver, "memory_total_mib": int(memory)}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return {"name": None, "driver": None, "memory_total_mib": None}


def output_signature(outputs: Sequence[Mapping[str, Any]]) -> list[tuple[int, str, bool, str]]:
    return [
        (int(item["index"]), str(item["corrected_text"]), bool(item["changed"]), str(item["reason"]))
        for item in outputs
    ]


def repeat_stability(signatures: Sequence[Sequence[tuple[int, str, bool, str]]]) -> bool | None:
    if len(signatures) < 2:
        return None
    return all(signature == signatures[0] for signature in signatures[1:])


def run_benchmark(
    segments: Sequence[TranscriptSegment],
    *,
    target_indices: Sequence[int],
    batch_size: int,
    context_segments: int,
    glossary: Sequence[str],
    options: OllamaOptions,
    runs: int,
    review_csv: Path | None,
    reference_changes: Path | None,
    reference_review: Path | None,
    reference_profile: str,
) -> dict[str, Any]:
    model = _model_metadata(options)
    run_reports: list[dict[str, Any]] = []
    for run_number in range(1, runs + 1):
        result = run_ollama_correction(
            segments,
            target_indices=target_indices,
            batch_size=batch_size,
            context_segments=context_segments,
            glossary=glossary,
            options=options,
        )
        gate = apply_safety_gate(result["segments"], glossary=glossary)
        baseline_chars = _target_text_chars(segments, target_indices)
        escalated_chars = _target_text_chars(segments, gate["escalated_indices"])
        report: dict[str, Any] = {
            "run": run_number,
            "metrics": result["metrics"],
            "gate": {
                **gate,
                "api_target_count_reduction_percent": _reduction_percent(
                    len(target_indices), len(gate["escalated_indices"])
                ),
                "api_target_text_reduction_percent": _reduction_percent(baseline_chars, escalated_chars),
            },
            "outputs": result["segments"],
        }
        if review_csv is not None:
            report["task65_review"] = evaluate_task65_review(result["segments"], gate, review_csv)
        if reference_changes is not None and reference_review is not None:
            report["reference_review"] = evaluate_reference_review(
                result["segments"],
                gate,
                changes_path=reference_changes,
                review_path=reference_review,
                profile_label=reference_profile,
            )
        run_reports.append(report)
    signatures = [output_signature(run["outputs"]) for run in run_reports]
    return {
        "phase": "local_subtitle_correction_benchmark",
        "model": model,
        "runtime": {
            "base_url": options.base_url,
            "think": False,
            "num_ctx": options.num_ctx,
            "temperature": options.temperature,
            "seed": options.seed,
            "batch_size": batch_size,
            "context_segments": context_segments,
            "gpu": _gpu_metadata(),
        },
        "segment_count": len(segments),
        "target_segment_count": len(target_indices),
        "run_count": runs,
        "outputs_stable": repeat_stability(signatures),
        "runs": run_reports,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    model = report["model"]
    runtime = report["runtime"]
    stable = report["outputs_stable"]
    stability_label = "not_evaluated" if stable is None else str(stable).lower()
    lines = [
        "# Local Subtitle Correction Benchmark",
        "",
        f"- model: `{model.get('name')}`",
        f"- digest: `{model.get('digest')}`",
        f"- quantization: `{(model.get('details') or {}).get('quantization_level')}`",
        f"- Ollama: `{model.get('ollama_version')}`",
        f"- GPU: `{runtime['gpu'].get('name')}`",
        f"- settings: `think=false / num_ctx={runtime['num_ctx']} / "
        f"temperature={runtime['temperature']} / seed={runtime['seed']}`",
        f"- segments / targets: `{report['segment_count']} / {report['target_segment_count']}`",
        f"- repeated output stable: `{stability_label}`",
        "",
        "| Run | Accepted local | Escalated | API target reduction | API text reduction | "
        "Unsafe hard accepts | Seconds | Peak VRAM |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        gate = run["gate"]
        hard_review = run.get("task65_review", {})
        peak = run["metrics"]["vram"]["peak_mib"]
        lines.append(
            f"| {run['run']} | {len(gate['accepted_indices'])} | {len(gate['escalated_indices'])} | "
            f"{gate['api_target_count_reduction_percent']:.3f}% | "
            f"{gate['api_target_text_reduction_percent']:.3f}% | "
            f"{hard_review.get('unsafe_local_accept_count', 'n/a')} | "
            f"{run['metrics']['processing_seconds']:.3f} | {peak if peak is not None else 'n/a'} MiB |"
        )
    lines.extend(
        [
            "",
            "This benchmark does not call OpenAI and does not change pipeline defaults.",
            "Model confidence is recorded but is not used by the deterministic acceptance gate.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama subtitle correction without changing the pipeline.")
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--targets-file", type=Path)
    parser.add_argument("--reviewed-only-csv", type=Path)
    parser.add_argument("--scope", choices=["all", "suspicious"], default="suspicious")
    parser.add_argument("--suspicion-threshold", type=float, default=0.4)
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--context-segments", type=int, default=2)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--glossary", action="append", default=[])
    parser.add_argument("--no-default-glossary", action="store_true")
    parser.add_argument("--reference-changes", type=Path)
    parser.add_argument("--reference-review", type=Path)
    parser.add_argument("--reference-profile", default="gpt-5_5_default")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def _reviewed_indices(path: Path, segment_count: int) -> list[int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        indices = sorted(
            {
                int(row["index"])
                for row in csv.DictReader(handle)
                if row.get("default_label") or row.get("none_label") or row.get("preferred_output") or row.get("notes")
            }
        )
    if any(index < 0 or index >= segment_count for index in indices):
        raise ValueError("review CSV index is outside transcript")
    return indices


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 40:
        raise SystemExit("--batch-size must be between 1 and 40")
    if args.context_segments < 0 or args.context_segments > 10:
        raise SystemExit("--context-segments must be between 0 and 10")
    if args.num_ctx < 2048:
        raise SystemExit("--num-ctx must be at least 2048")
    if args.runs < 1 or args.runs > 5:
        raise SystemExit("--runs must be between 1 and 5")
    segments = load_segments(args.segments.resolve())
    glossary = [
        *([] if args.no_default_glossary else DEFAULT_TRANSCRIPT_REPLACEMENTS.values()),
        *args.glossary,
    ]
    if args.reviewed_only_csv is not None:
        review_csv = args.reviewed_only_csv.resolve()
        target_indices = _reviewed_indices(review_csv, len(segments))
    elif args.targets_file is not None:
        review_csv = None
        target_indices = load_target_indices(args.targets_file.resolve(), segment_count=len(segments))
    elif args.scope == "suspicious":
        review_csv = None
        target_indices = analyze_transcript_suspicion(
            segments,
            threshold=args.suspicion_threshold,
            context_segments=args.context_segments,
            batch_size=args.batch_size,
            glossary=glossary,
        ).target_indices
    else:
        review_csv = None
        target_indices = list(range(len(segments)))
    if not target_indices:
        raise SystemExit("no local correction targets")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_benchmark(
        segments,
        target_indices=target_indices,
        batch_size=args.batch_size,
        context_segments=args.context_segments,
        glossary=glossary,
        options=OllamaOptions(
            model=args.model,
            base_url=args.base_url,
            num_ctx=args.num_ctx,
            temperature=args.temperature,
            seed=args.seed,
            timeout_seconds=args.timeout,
        ),
        runs=args.runs,
        review_csv=review_csv,
        reference_changes=args.reference_changes.resolve() if args.reference_changes else None,
        reference_review=args.reference_review.resolve() if args.reference_review else None,
        reference_profile=args.reference_profile,
    )
    json_path = output_dir / "local_subtitle_correction_benchmark.json"
    markdown_path = output_dir / "local_subtitle_correction_benchmark.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
