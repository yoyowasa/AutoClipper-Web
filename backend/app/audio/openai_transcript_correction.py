from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.audio.transcript_correction_schema import (
    CorrectedTranscriptSegment,
    TranscriptCorrectionBatch,
    transcript_correction_response_format,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment, write_transcript_segments


DETERMINISTIC_TRANSCRIPT_FILENAME = "deterministic_transcript_segments.json"
OPENAI_CORRECTED_TRANSCRIPT_FILENAME = "openai_corrected_transcript_segments.json"
TRANSCRIPT_CORRECTION_SUMMARY_FILENAME = "transcript_correction_summary.json"
TRANSCRIPT_CORRECTION_DIFF_FILENAME = "transcript_correction_diff.md"
TRANSCRIPT_CORRECTION_PROGRESS_FILENAME = "subtitle_correction_progress.json"

TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
}

SYSTEM_PROMPT = """You correct ASR errors in Japanese subtitle segments.
Return only the requested structured output.
Do not summarize, paraphrase, improve style, or add information.
Do not merge, split, reorder, add, or remove segments.
Preserve fillers and conversational tone unless text is clearly an ASR error.
Only correct wording strongly supported by the supplied segment context.
The input contains text only. Never infer content from audio or video.
Do not replace numeric tokens with phonetic kanji unless the intended numeric expression is unequivocal.
Leave short ambiguous utterances unchanged.
For unchanged text, copy original_text exactly, set changed=false, reason=unchanged.
"""


class OpenAIResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any:
        pass


class OpenAIClientProtocol(Protocol):
    responses: OpenAIResponsesResource


CorrectionProgressCallback = Callable[[int, int, int], None]


@dataclass
class TranscriptCorrectionStats:
    model: str
    input_segment_count: int = 0
    corrected_segment_count: int = 0
    unchanged_segment_count: int = 0
    low_confidence_rejected_count: int = 0
    safety_rejected_count: int = 0
    api_call_count: int = 0
    retry_count: int = 0
    successful_batch_count: int = 0
    failed_batch_count: int = 0
    schema_validation_failures: int = 0
    processing_seconds: float = 0.0
    estimated_input_text_length: int = 0
    estimated_output_text_length: int = 0
    reason_counts: Counter[str] = field(default_factory=Counter)
    safety_rejection_counts: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def summary(self, *, enabled: bool, fallback_used: bool, fallback_reason: str | None) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "model": self.model,
            "input_segment_count": self.input_segment_count,
            "corrected_segment_count": self.corrected_segment_count,
            "unchanged_segment_count": self.unchanged_segment_count,
            "low_confidence_rejected_count": self.low_confidence_rejected_count,
            "safety_rejected_count": self.safety_rejected_count,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "api_call_count": self.api_call_count,
            "retry_count": self.retry_count,
            "successful_batch_count": self.successful_batch_count,
            "failed_batch_count": self.failed_batch_count,
            "schema_validation_failures": self.schema_validation_failures,
            "processing_seconds": round(self.processing_seconds, 6),
            "estimated_input_text_length": self.estimated_input_text_length,
            "estimated_output_text_length": self.estimated_output_text_length,
            "reason_counts": dict(sorted(self.reason_counts.items())),
            "safety_rejection_counts": dict(sorted(self.safety_rejection_counts.items())),
            "errors": self.errors[:10],
            "timestamps_preserved": True,
            "segment_count_preserved": True,
        }


@dataclass(frozen=True)
class TranscriptCorrectionResult:
    segments: list[TranscriptSegment]
    summary: dict[str, Any]
    changes: list[dict[str, Any]]


def _load_default_client() -> OpenAIClientProtocol:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc
    return OpenAI()


def _extract_response_text(response: Any) -> str:
    parsed = getattr(response, "output_parsed", None)
    if parsed is not None:
        if hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump()
        return json.dumps(parsed)
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    if isinstance(response, Mapping) and response.get("output_text"):
        return str(response["output_text"])
    raise ValueError("OpenAI response did not include output text")


def _is_transient_error(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) in TRANSIENT_STATUS_CODES or exc.__class__.__name__ in TRANSIENT_ERROR_NAMES


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


class OpenAITranscriptCorrector:
    def __init__(
        self,
        client: OpenAIClientProtocol | None = None,
        *,
        model: str = "gpt-5.5",
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.25,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self.model = model
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep_func = sleep_func
        self.stats = TranscriptCorrectionStats(model=model)

    @property
    def client(self) -> OpenAIClientProtocol:
        if self._client is None:
            self._client = _load_default_client()
        return self._client

    def correct_segments(
        self,
        segments: Sequence[TranscriptSegment],
        *,
        min_confidence: float = 0.9,
        batch_size: int = 40,
        context_segments: int = 2,
        glossary: Sequence[str] = (),
        progress_callback: CorrectionProgressCallback | None = None,
    ) -> TranscriptCorrectionResult:
        started_at = time.monotonic()
        self.stats = TranscriptCorrectionStats(model=self.model)
        source = list(segments)
        self.stats.input_segment_count = len(source)
        output = list(source)
        changes: list[dict[str, Any]] = []
        total_batches = (len(source) + batch_size - 1) // batch_size
        completed_batches = 0

        def notify_progress() -> None:
            if progress_callback is not None:
                progress_callback(completed_batches, total_batches, self.stats.retry_count)

        notify_progress()
        try:
            for batch_start in range(0, len(source), batch_size):
                batch_end = min(len(source), batch_start + batch_size)
                targets = list(enumerate(source[batch_start:batch_end], start=batch_start))
                context_start = max(0, batch_start - context_segments)
                context_end = min(len(source), batch_end + context_segments)
                context = [
                    {"index": index, "text": source[index].text}
                    for index in range(context_start, context_end)
                    if index < batch_start or index >= batch_end
                ]
                corrected = self._correct_batch(
                    targets,
                    context=context,
                    glossary=glossary,
                    on_retry=notify_progress,
                )
                for item in corrected:
                    original = source[item.index]
                    corrected_text = item.corrected_text.strip()
                    safety_rejection = _correction_safety_rejection(item, original.text, corrected_text)
                    should_apply = (
                        item.changed
                        and item.confidence >= min_confidence
                        and corrected_text
                        and corrected_text != original.text
                        and safety_rejection is None
                    )
                    if should_apply:
                        output[item.index] = original.model_copy(update={"text": corrected_text})
                        self.stats.corrected_segment_count += 1
                        self.stats.reason_counts[item.reason] += 1
                        changes.append(
                            {
                                "index": item.index,
                                "start": original.start,
                                "end": original.end,
                                "before": original.text,
                                "after": corrected_text,
                                "reason": item.reason,
                                "confidence": item.confidence,
                            }
                        )
                    else:
                        self.stats.unchanged_segment_count += 1
                        if item.changed and item.confidence < min_confidence:
                            self.stats.low_confidence_rejected_count += 1
                        elif safety_rejection is not None:
                            self.stats.safety_rejected_count += 1
                            self.stats.safety_rejection_counts[safety_rejection] += 1
                completed_batches += 1
                notify_progress()
        finally:
            self.stats.processing_seconds = time.monotonic() - started_at
        return TranscriptCorrectionResult(
            segments=output,
            summary=self.stats.summary(enabled=True, fallback_used=False, fallback_reason=None),
            changes=changes,
        )

    def _correct_batch(
        self,
        targets: Sequence[tuple[int, TranscriptSegment]],
        *,
        context: Sequence[dict[str, Any]],
        glossary: Sequence[str],
        on_retry: Callable[[], None] | None = None,
    ) -> list[CorrectedTranscriptSegment]:
        payload = {
            "target_segments": [
                {
                    "index": index,
                    "original_text": segment.text,
                    "asr_confidence": segment.confidence,
                }
                for index, segment in targets
            ],
            "read_only_context_segments": list(context),
            "preferred_terms": list(dict.fromkeys(term for term in glossary if term.strip())),
        }
        user_content = json.dumps(payload, ensure_ascii=False)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started_at = time.monotonic()
            try:
                self.stats.api_call_count += 1
                self.stats.estimated_input_text_length += len(SYSTEM_PROMPT) + len(user_content)
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    text={"format": transcript_correction_response_format(len(targets))},
                )
                text = _extract_response_text(response)
                self.stats.estimated_output_text_length += len(text)
                result = TranscriptCorrectionBatch.model_validate(json.loads(text))
                self._validate_batch(result.segments, targets)
                self.stats.successful_batch_count += 1
                return result.segments
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                self.stats.schema_validation_failures += 1
                self.stats.failed_batch_count += 1
                self.stats.errors.append(_safe_error(exc))
                raise RuntimeError(f"schema_validation_failed: {exc}") from exc
            except Exception as exc:
                last_error = exc
                if not _is_transient_error(exc) or attempt >= self.max_retries:
                    self.stats.failed_batch_count += 1
                    self.stats.errors.append(_safe_error(exc))
                    break
                self.stats.retry_count += 1
                if on_retry is not None:
                    on_retry()
                self.sleep_func(self.retry_backoff_seconds * (2**attempt))
            finally:
                _ = time.monotonic() - started_at
        raise RuntimeError(f"openai_subtitle_correction_failed: {_safe_error(last_error or RuntimeError('unknown'))}") from last_error

    @staticmethod
    def _validate_batch(
        corrected: Sequence[CorrectedTranscriptSegment],
        targets: Sequence[tuple[int, TranscriptSegment]],
    ) -> None:
        expected = {index: segment.text for index, segment in targets}
        received = {item.index: item for item in corrected}
        if len(received) != len(corrected) or set(received) != set(expected):
            raise ValueError("correction response indices do not match requested target indices")
        for index, original_text in expected.items():
            item = received[index]
            if item.original_text != original_text:
                raise ValueError(f"correction response original_text mismatch at index {index}")
            if item.changed and item.reason == "unchanged":
                raise ValueError(f"changed correction used unchanged reason at index {index}")
            if not item.changed and (item.corrected_text != original_text or item.reason != "unchanged"):
                raise ValueError(f"unchanged correction modified text or reason at index {index}")


def _correction_safety_rejection(
    item: CorrectedTranscriptSegment,
    original_text: str,
    corrected_text: str,
) -> str | None:
    if item.reason != "numeric_expression" and re.findall(r"\d+", original_text) != re.findall(r"\d+", corrected_text):
        return "numeric_change_without_numeric_reason"
    return None


def disabled_correction_result(segments: Sequence[TranscriptSegment], model: str) -> TranscriptCorrectionResult:
    source = list(segments)
    stats = TranscriptCorrectionStats(
        model=model,
        input_segment_count=len(source),
        unchanged_segment_count=len(source),
    )
    return TranscriptCorrectionResult(
        segments=source,
        summary=stats.summary(enabled=False, fallback_used=False, fallback_reason=None),
        changes=[],
    )


def fallback_correction_result(
    segments: Sequence[TranscriptSegment],
    corrector: OpenAITranscriptCorrector,
    exc: Exception,
) -> TranscriptCorrectionResult:
    source = list(segments)
    corrector.stats.corrected_segment_count = 0
    corrector.stats.unchanged_segment_count = len(source)
    corrector.stats.low_confidence_rejected_count = 0
    corrector.stats.safety_rejected_count = 0
    corrector.stats.reason_counts.clear()
    corrector.stats.safety_rejection_counts.clear()
    return TranscriptCorrectionResult(
        segments=source,
        summary=corrector.stats.summary(enabled=True, fallback_used=True, fallback_reason=_safe_error(exc)),
        changes=[],
    )


def deterministic_transcript_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / DETERMINISTIC_TRANSCRIPT_FILENAME


def corrected_transcript_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / OPENAI_CORRECTED_TRANSCRIPT_FILENAME


def correction_summary_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / TRANSCRIPT_CORRECTION_SUMMARY_FILENAME


def correction_diff_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / TRANSCRIPT_CORRECTION_DIFF_FILENAME


def correction_progress_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / TRANSCRIPT_CORRECTION_PROGRESS_FILENAME


def write_correction_summary(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_correction_diff(result: TranscriptCorrectionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Transcript Correction Diff", ""]
    if not result.summary["enabled"]:
        lines.append("OpenAI subtitle correction was disabled.")
    elif result.summary["fallback_used"]:
        lines.append("OpenAI subtitle correction fell back to the deterministic transcript.")
    elif not result.changes:
        lines.append("No corrections were applied.")
    else:
        for change in result.changes:
            lines.extend(
                [
                    f"## Segment {change['index']}",
                    "",
                    f"- Time: `{change['start']:.3f} - {change['end']:.3f}`",
                    f"- Reason: `{change['reason']}`",
                    f"- Confidence: `{change['confidence']:.3f}`",
                    f"- Before: {change['before']}",
                    f"- After: {change['after']}",
                    "",
                ]
            )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_corrected_transcript(result: TranscriptCorrectionResult, output_dir: str | Path) -> Path:
    return write_transcript_segments(result.segments, corrected_transcript_output_path(output_dir))
