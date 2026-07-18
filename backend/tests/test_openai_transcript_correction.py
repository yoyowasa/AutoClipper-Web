import json
from pathlib import Path
from typing import Any

import pytest

from app.audio.openai_transcript_correction import (
    OpenAITranscriptCorrector,
    disabled_correction_result,
    filter_failed_correction_result,
    fallback_correction_result,
    write_corrected_transcript,
    write_correction_diff,
    write_correction_summary,
)
from app.audio.transcript_correction_schema import (
    CompactTranscriptCorrectionBatch,
    TranscriptCorrectionBatch,
    compact_transcript_correction_json_schema,
    compact_transcript_correction_response_format,
    transcript_correction_json_schema,
    transcript_correction_response_format,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.jobs.runner import PipelineExpectedError, _apply_transcript_correction


class TransientOpenAIError(Exception):
    status_code = 429


class FakeResponse:
    def __init__(self, payload: dict[str, Any], usage: dict[str, Any] | None = None) -> None:
        self.output_text = json.dumps(payload, ensure_ascii=False)
        self.usage = usage


class FakeResponses:
    def __init__(self, outcomes: list[Any], usage: dict[str, Any] | None = None) -> None:
        self.outcomes = outcomes
        self.usage = usage
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome, self.usage)


class FakeClient:
    def __init__(self, outcomes: list[Any], usage: dict[str, Any] | None = None) -> None:
        self.responses = FakeResponses(outcomes, usage)


def segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=1.5, text="オープンエーアイのモデル", confidence=0.7),
        TranscriptSegment(start=1.5, end=3.0, text="字幕を確認します", confidence=0.9),
    ]


def correction_payload(*, first_confidence: float = 0.96) -> dict[str, Any]:
    return {
        "segments": [
            {
                "index": 0,
                "original_text": "オープンエーアイのモデル",
                "corrected_text": "OpenAIのモデル",
                "changed": True,
                "reason": "proper_noun",
                "confidence": first_confidence,
            },
            {
                "index": 1,
                "original_text": "字幕を確認します",
                "corrected_text": "字幕を確認します",
                "changed": False,
                "reason": "unchanged",
                "confidence": 1.0,
            },
        ]
    }


def compact_correction_payload() -> dict[str, Any]:
    return {
        "target_count": 2,
        "changes": [
            {
                "index": 0,
                "corrected_text": "OpenAIのモデル",
                "reason": "proper_noun",
                "confidence": 0.96,
            }
        ],
    }


def test_correction_schema_is_strict() -> None:
    schema = transcript_correction_json_schema(2)
    response_format = transcript_correction_response_format(2)

    assert schema["additionalProperties"] is False
    assert schema["properties"]["segments"]["minItems"] == 2
    assert schema["properties"]["segments"]["maxItems"] == 2
    assert response_format["strict"] is True
    assert TranscriptCorrectionBatch.model_validate(correction_payload()).segments[0].reason == "proper_noun"


def test_compact_correction_schema_is_strict_and_changes_only() -> None:
    schema = compact_transcript_correction_json_schema(2)
    response_format = compact_transcript_correction_response_format(2)

    assert schema["additionalProperties"] is False
    assert schema["properties"]["target_count"]["enum"] == [2]
    assert schema["properties"]["changes"]["minItems"] == 0
    assert schema["properties"]["changes"]["maxItems"] == 2
    assert "original_text" not in schema["properties"]["changes"]["items"]["properties"]
    assert "changed" not in schema["properties"]["changes"]["items"]["properties"]
    assert response_format["strict"] is True
    assert CompactTranscriptCorrectionBatch.model_validate(compact_correction_payload()).changes[0].index == 0


def test_correction_applies_text_only_and_preserves_timestamps() -> None:
    client = FakeClient([correction_payload()])
    corrector = OpenAITranscriptCorrector(client=client, sleep_func=lambda _seconds: None)

    result = corrector.correct_segments(
        segments(),
        min_confidence=0.8,
        batch_size=2,
        context_segments=1,
        glossary=["OpenAI"],
    )

    assert [segment.text for segment in result.segments] == ["OpenAIのモデル", "字幕を確認します"]
    assert [(segment.start, segment.end) for segment in result.segments] == [(0.0, 1.5), (1.5, 3.0)]
    assert result.summary["corrected_segment_count"] == 1
    assert result.summary["unchanged_segment_count"] == 1
    assert result.summary["fallback_used"] is False
    assert result.summary["reason_counts"] == {"proper_noun": 1}
    call = client.responses.calls[0]
    assert call["text"]["format"]["strict"] is True
    assert "reasoning" not in call
    encoded = json.dumps(call["input"], ensure_ascii=False)
    assert "OpenAI" in encoded
    assert ".mp4" not in encoded.lower()
    assert "video_path" not in encoded.lower()
    assert "stored_path" not in encoded.lower()


def test_compact_correction_omits_unchanged_targets_and_preserves_timestamps() -> None:
    client = FakeClient([compact_correction_payload()])
    corrector = OpenAITranscriptCorrector(client=client, response_schema="changes_only")

    result = corrector.correct_segments(segments(), min_confidence=0.8, batch_size=2)

    assert [segment.text for segment in result.segments] == ["OpenAIのモデル", "字幕を確認します"]
    assert [(segment.start, segment.end) for segment in result.segments] == [(0.0, 1.5), (1.5, 3.0)]
    assert result.summary["response_schema"] == "changes_only"
    assert result.summary["response_change_item_count"] == 1
    assert result.summary["corrected_segment_count"] == 1
    assert result.summary["unchanged_segment_count"] == 1
    call = client.responses.calls[0]
    assert call["text"]["format"]["name"] == "subtitle_correction_changes_only_batch"
    assert "Omit unchanged target segments" in call["input"][0]["content"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "target_count": 2,
                "changes": [
                    {"index": 9, "corrected_text": "x", "reason": "asr_error", "confidence": 0.9},
                ],
            },
            "unrequested target index",
        ),
        (
            {
                "target_count": 2,
                "changes": [
                    {"index": 0, "corrected_text": "x", "reason": "asr_error", "confidence": 0.9},
                    {"index": 0, "corrected_text": "y", "reason": "asr_error", "confidence": 0.9},
                ],
            },
            "duplicate target indices",
        ),
        (
            {
                "target_count": 2,
                "changes": [
                    {"index": 0, "corrected_text": "   ", "reason": "asr_error", "confidence": 0.9},
                ],
            },
            "empty text",
        ),
    ],
)
def test_compact_correction_rejects_unsafe_indices_and_text(payload: dict[str, Any], message: str) -> None:
    corrector = OpenAITranscriptCorrector(
        client=FakeClient([payload]),
        response_schema="changes_only",
        max_retries=0,
    )

    with pytest.raises(RuntimeError, match=message):
        corrector.correct_segments(segments(), batch_size=2)


def test_explicit_reasoning_effort_is_sent_to_responses_api() -> None:
    client = FakeClient([correction_payload()])
    corrector = OpenAITranscriptCorrector(client=client, reasoning_effort="none")

    result = corrector.correct_segments(segments(), batch_size=2)

    assert client.responses.calls[0]["reasoning"] == {"effort": "none"}
    assert result.summary["reasoning_effort"] == "none"


def test_invalid_reasoning_effort_is_rejected_before_api_call() -> None:
    with pytest.raises(ValueError, match="unsupported subtitle correction reasoning effort"):
        OpenAITranscriptCorrector(client=FakeClient([]), reasoning_effort="automatic")


def test_invalid_response_schema_is_rejected_before_api_call() -> None:
    with pytest.raises(ValueError, match="unsupported subtitle correction response schema"):
        OpenAITranscriptCorrector(client=FakeClient([]), response_schema="compact")


def test_low_confidence_correction_is_not_applied() -> None:
    corrector = OpenAITranscriptCorrector(client=FakeClient([correction_payload(first_confidence=0.5)]))

    result = corrector.correct_segments(segments(), min_confidence=0.8, batch_size=2)

    assert result.segments == segments()
    assert result.summary["corrected_segment_count"] == 0
    assert result.summary["low_confidence_rejected_count"] == 1


def test_suspicious_scope_sends_only_targets_with_read_only_context() -> None:
    payload = {"segments": [correction_payload()["segments"][0]]}
    client = FakeClient([payload])
    corrector = OpenAITranscriptCorrector(client=client)

    result = corrector.correct_segments(
        segments(),
        target_indices=[0],
        context_segments=1,
    )

    request = json.loads(client.responses.calls[0]["input"][1]["content"])
    assert [item["index"] for item in request["target_segments"]] == [0]
    assert set(request["target_segments"][0]) == {"index", "original_text", "asr_confidence"}
    assert request["read_only_context_segments"] == [{"index": 1, "text": "字幕を確認します"}]
    assert result.segments[1] == segments()[1]
    assert result.summary["scope"] == "suspicious"
    assert result.summary["target_segment_count"] == 1
    assert result.summary["context_segment_count"] == 1


def test_zero_suspicious_targets_skips_api() -> None:
    client = FakeClient([])
    result = OpenAITranscriptCorrector(client=client).correct_segments(segments(), target_indices=[])

    assert client.responses.calls == []
    assert result.segments == segments()
    assert result.summary["api_call_count"] == 0
    assert result.summary["target_segment_count"] == 0
    assert result.summary["unchanged_segment_count"] == 2


def test_response_usage_is_recorded() -> None:
    usage = {
        "input_tokens": 120,
        "output_tokens": 35,
        "input_tokens_details": {"cached_tokens": 20},
        "output_tokens_details": {"reasoning_tokens": 12},
    }
    result = OpenAITranscriptCorrector(client=FakeClient([correction_payload()], usage)).correct_segments(
        segments(), batch_size=2
    )

    assert result.summary["input_tokens"] == 120
    assert result.summary["output_tokens"] == 35
    assert result.summary["reasoning_tokens"] == 12
    assert result.summary["visible_output_tokens"] == 23
    assert result.summary["cached_tokens"] == 20


def test_numeric_change_requires_numeric_expression_reason() -> None:
    source = [TranscriptSegment(start=0.0, end=1.0, text="アメリカの2のテック界隈", confidence=0.8)]
    payload = {
        "segments": [
            {
                "index": 0,
                "original_text": source[0].text,
                "corrected_text": "アメリカの通のテック界隈",
                "changed": True,
                "reason": "homophone",
                "confidence": 0.99,
            }
        ]
    }
    corrector = OpenAITranscriptCorrector(client=FakeClient([payload]))

    result = corrector.correct_segments(source, min_confidence=0.8, batch_size=1)

    assert result.segments == source
    assert result.summary["corrected_segment_count"] == 0
    assert result.summary["safety_rejected_count"] == 1
    assert result.summary["safety_rejection_counts"] == {"numeric_change_without_numeric_reason": 1}


def test_transient_error_is_retried() -> None:
    client = FakeClient([TransientOpenAIError("rate limited"), correction_payload()])
    corrector = OpenAITranscriptCorrector(
        client=client,
        max_retries=1,
        retry_backoff_seconds=0,
        sleep_func=lambda _seconds: None,
    )
    progress: list[tuple[int, int, int]] = []

    result = corrector.correct_segments(
        segments(),
        batch_size=2,
        progress_callback=lambda completed, total, retries: progress.append((completed, total, retries)),
    )

    assert result.summary["api_call_count"] == 2
    assert result.summary["retry_count"] == 1
    assert len(client.responses.calls) == 2
    assert progress == [(0, 1, 0), (0, 1, 1), (1, 1, 1)]


def test_mismatched_original_text_is_rejected() -> None:
    payload = correction_payload()
    payload["segments"][0]["original_text"] = "different"
    corrector = OpenAITranscriptCorrector(client=FakeClient([payload]))

    with pytest.raises(RuntimeError, match="schema_validation_failed"):
        corrector.correct_segments(segments(), batch_size=2)


def test_runner_falls_back_to_complete_deterministic_transcript() -> None:
    corrector = OpenAITranscriptCorrector(
        client=FakeClient([TransientOpenAIError("unavailable")]),
        max_retries=0,
    )

    result = _apply_transcript_correction(
        segments(),
        {
            "subtitleCorrectionMode": "openai",
            "subtitleCorrectionFallbackEnabled": True,
            "subtitleCorrectionBatchSize": 2,
        },
        corrector=corrector,
    )

    assert result.segments == segments()
    assert result.summary["fallback_used"] is True
    assert result.summary["corrected_segment_count"] == 0
    assert result.summary["unchanged_segment_count"] == 2


def test_compact_schema_failure_falls_back_without_resending_full_batch() -> None:
    client = FakeClient(
        [
            {
                "target_count": 2,
                "changes": [
                    {"index": 7, "corrected_text": "x", "reason": "asr_error", "confidence": 0.99},
                ],
            }
        ]
    )
    corrector = OpenAITranscriptCorrector(
        client=client,
        response_schema="changes_only",
        max_retries=0,
    )

    result = _apply_transcript_correction(
        segments(),
        {
            "subtitleCorrectionMode": "openai",
            "subtitleCorrectionResponseSchema": "changes_only",
            "subtitleCorrectionFallbackEnabled": True,
            "subtitleCorrectionBatchSize": 2,
        },
        corrector=corrector,
    )

    assert result.segments == segments()
    assert result.summary["response_schema"] == "changes_only"
    assert result.summary["fallback_used"] is True
    assert result.summary["schema_validation_failures"] == 1
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["text"]["format"]["name"] == "subtitle_correction_changes_only_batch"


def test_runner_failure_without_fallback_is_clear() -> None:
    corrector = OpenAITranscriptCorrector(
        client=FakeClient([TransientOpenAIError("unavailable")]),
        max_retries=0,
    )

    with pytest.raises(PipelineExpectedError) as exc_info:
        _apply_transcript_correction(
            segments(),
            {
                "subtitleCorrectionMode": "openai",
                "subtitleCorrectionFallbackEnabled": False,
                "subtitleCorrectionBatchSize": 2,
            },
            corrector=corrector,
        )

    assert exc_info.value.code == "openai_subtitle_correction_failed"


def test_runner_openai_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(PipelineExpectedError) as exc_info:
        _apply_transcript_correction(segments(), {"subtitleCorrectionMode": "openai"})

    assert exc_info.value.code == "openai_configuration_missing"
    assert exc_info.value.details == {"setting": "OPENAI_API_KEY", "feature": "subtitle_correction"}


def test_runner_propagates_reasoning_and_response_schema_to_created_corrector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def build_corrector(**kwargs: Any) -> OpenAITranscriptCorrector:
        captured.update(kwargs)
        return OpenAITranscriptCorrector(client=FakeClient([compact_correction_payload()]), **kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr("app.jobs.runner.OpenAITranscriptCorrector", build_corrector)

    result = _apply_transcript_correction(
        segments(),
        {
            "subtitleCorrectionMode": "openai",
            "subtitleCorrectionReasoningEffort": "none",
            "subtitleCorrectionResponseSchema": "changes_only",
            "subtitleCorrectionBatchSize": 2,
        },
    )

    assert captured == {
        "model": "gpt-5.5",
        "reasoning_effort": "none",
        "response_schema": "changes_only",
    }
    assert result.summary["reasoning_effort"] == "none"
    assert result.summary["response_schema"] == "changes_only"


def test_zero_suspicious_targets_do_not_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = _apply_transcript_correction(
        segments(),
        {"subtitleCorrectionMode": "openai", "subtitleCorrectionScope": "suspicious"},
        target_indices=[],
    )

    assert result.summary["api_call_count"] == 0
    assert result.summary["target_segment_count"] == 0


def test_filter_failure_falls_back_without_openai() -> None:
    result = filter_failed_correction_result(segments(), "gpt-5.5", RuntimeError("filter broke"))

    assert result.segments == segments()
    assert result.summary["filter_failed"] is True
    assert result.summary["fallback_used"] is True
    assert result.summary["api_call_count"] == 0


def test_disabled_mode_does_not_call_openai() -> None:
    result = _apply_transcript_correction(segments(), {"subtitleCorrectionMode": "off"})

    assert result.segments == segments()
    assert result.summary["enabled"] is False
    assert result.summary["api_call_count"] == 0


def test_correction_artifacts_are_written(tmp_path: Path) -> None:
    result = disabled_correction_result(segments(), "gpt-5.5")
    summary_path = write_correction_summary(result.summary, tmp_path / "summary.json")
    diff_path = write_correction_diff(result, tmp_path / "diff.md")
    corrected_path = write_corrected_transcript(result, tmp_path)

    assert json.loads(summary_path.read_text(encoding="utf-8"))["enabled"] is False
    assert "disabled" in diff_path.read_text(encoding="utf-8").lower()
    assert json.loads(corrected_path.read_text(encoding="utf-8"))[0]["start"] == 0.0


def test_fallback_result_discards_partial_corrections() -> None:
    corrector = OpenAITranscriptCorrector(client=FakeClient([]))
    corrector.stats.corrected_segment_count = 1
    corrector.stats.reason_counts["proper_noun"] = 1

    result = fallback_correction_result(segments(), corrector, RuntimeError("failed"))

    assert result.segments == segments()
    assert result.changes == []
    assert result.summary["corrected_segment_count"] == 0
