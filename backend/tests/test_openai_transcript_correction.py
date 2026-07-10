import json
from pathlib import Path
from typing import Any

import pytest

from app.audio.openai_transcript_correction import (
    OpenAITranscriptCorrector,
    disabled_correction_result,
    fallback_correction_result,
    write_corrected_transcript,
    write_correction_diff,
    write_correction_summary,
)
from app.audio.transcript_correction_schema import (
    TranscriptCorrectionBatch,
    transcript_correction_json_schema,
    transcript_correction_response_format,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.jobs.runner import PipelineExpectedError, _apply_transcript_correction


class TransientOpenAIError(Exception):
    status_code = 429


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.output_text = json.dumps(payload, ensure_ascii=False)


class FakeResponses:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


class FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.responses = FakeResponses(outcomes)


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


def test_correction_schema_is_strict() -> None:
    schema = transcript_correction_json_schema(2)
    response_format = transcript_correction_response_format(2)

    assert schema["additionalProperties"] is False
    assert schema["properties"]["segments"]["minItems"] == 2
    assert schema["properties"]["segments"]["maxItems"] == 2
    assert response_format["strict"] is True
    assert TranscriptCorrectionBatch.model_validate(correction_payload()).segments[0].reason == "proper_noun"


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
    encoded = json.dumps(call["input"], ensure_ascii=False)
    assert "OpenAI" in encoded
    assert ".mp4" not in encoded.lower()
    assert "video_path" not in encoded.lower()
    assert "stored_path" not in encoded.lower()


def test_low_confidence_correction_is_not_applied() -> None:
    corrector = OpenAITranscriptCorrector(client=FakeClient([correction_payload(first_confidence=0.5)]))

    result = corrector.correct_segments(segments(), min_confidence=0.8, batch_size=2)

    assert result.segments == segments()
    assert result.summary["corrected_segment_count"] == 0
    assert result.summary["low_confidence_rejected_count"] == 1


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

    result = corrector.correct_segments(segments(), batch_size=2)

    assert result.summary["api_call_count"] == 2
    assert len(client.responses.calls) == 2


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
