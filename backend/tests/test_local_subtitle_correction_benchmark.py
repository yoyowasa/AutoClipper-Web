from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from app.audio.benchmark_local_subtitle_correction import (
    OllamaOptions,
    apply_safety_gate,
    correction_safety_decision,
    evaluate_task65_review,
    output_signature,
    repeat_stability,
    run_ollama_correction,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment


def segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=1.0, text="前の文です", confidence=0.9),
        TranscriptSegment(start=1.0, end=2.0, text="テスト です", confidence=0.8),
        TranscriptSegment(start=2.0, end=3.0, text="次の文です", confidence=0.9),
    ]


def test_ollama_request_forces_non_thinking_full_schema_and_no_timestamps() -> None:
    requests: list[dict[str, Any]] = []

    def fake_request(_: str, path: str, payload: dict[str, Any] | None, __: float) -> dict[str, Any]:
        assert path == "/api/chat"
        assert payload is not None
        requests.append(payload)
        user_payload = json.loads(payload["messages"][1]["content"])
        target = user_payload["target_segments"][0]
        return {
            "message": {
                "content": json.dumps(
                    {
                        "segments": [
                            {
                                "index": target["index"],
                                "corrected_text": "テストです",
                                "reason": "punctuation",
                                "confidence": 0.99,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            },
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

    report = run_ollama_correction(
        segments(),
        target_indices=[1],
        batch_size=1,
        context_segments=1,
        glossary=[],
        options=OllamaOptions("qwen3.5:9b", "http://localhost:11434", 8192, 0, 42, 10),
        request_json=fake_request,
    )

    request = requests[0]
    user_payload = json.loads(request["messages"][1]["content"])
    assert request["think"] is False
    assert request["stream"] is False
    assert request["options"] == {"temperature": 0, "seed": 42, "num_ctx": 8192}
    assert request["format"]["properties"]["segments"]["minItems"] == 1
    assert set(user_payload["target_segments"][0]) == {"index", "original_text"}
    assert "start" not in json.dumps(user_payload)
    assert report["metrics"]["prompt_eval_count"] == 10


def test_schema_validation_rejects_wrong_index() -> None:
    def fake_request(_: str, __: str, ___: dict[str, Any] | None, ____: float) -> dict[str, Any]:
        return {
            "message": {
                "content": json.dumps(
                    {
                        "segments": [
                            {
                                "index": 2,
                                "corrected_text": "修正",
                                "reason": "asr_error",
                                "confidence": 0.9,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }

    with pytest.raises(ValueError, match="indices|original_text"):
        run_ollama_correction(
            segments(),
            target_indices=[1],
            batch_size=1,
            context_segments=0,
            glossary=[],
            options=OllamaOptions("qwen3.5:9b", "http://localhost:11434", 8192, 0, 42, 10),
            request_json=fake_request,
        )


def test_deterministic_gate_accepts_only_low_risk_changes() -> None:
    assert correction_safety_decision("テスト です", "テストです", reason="punctuation", glossary=[]).action == "escalate"
    assert (
        correction_safety_decision(
            "この内容は正しいですけど問題ありません",
            "この内容は正しいですが問題ありません",
            reason="asr_error",
            glossary=[],
        ).action
        == "accept_local"
    )
    assert correction_safety_decision("記憶者です", "キオクシアです", reason="proper_noun", glossary=[]).action == "escalate"
    assert correction_safety_decision("10円", "100円", reason="numeric_expression", glossary=[]).action == "escalate"
    assert correction_safety_decision("STカード", "SDカード", reason="asr_error", glossary=[]).action == "escalate"
    assert correction_safety_decision("東京です", "京都です", reason="asr_error", glossary=[]).action == "escalate"


def test_task65_review_marks_wrong_local_accept_as_unsafe(tmp_path: Path) -> None:
    review_path = tmp_path / "review.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "source_text",
                "default_output",
                "none_output",
                "default_label",
                "none_label",
                "preferred_output",
                "term_types",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "index": 1,
                "source_text": "記憶者",
                "default_output": "キオクシア",
                "none_output": "NVIDIA",
                "default_label": "useful_correction",
                "none_label": "harmful_correction",
                "preferred_output": "default",
                "term_types": "proper_noun",
                "notes": "",
            }
        )
    outputs = [
        {
            "index": 1,
            "original_text": "記憶者",
            "corrected_text": "NVIDIA",
            "changed": True,
            "reason": "asr_error",
            "confidence": 0.99,
        }
    ]
    forced_accept = {"accepted_indices": [1], "escalated_indices": []}
    real_gate = apply_safety_gate(outputs, glossary=[])

    assert evaluate_task65_review(outputs, forced_accept, review_path)["unsafe_local_accept_count"] == 1
    assert evaluate_task65_review(outputs, real_gate, review_path)["escalated_count"] == 1


def test_output_signature_detects_repeat_instability() -> None:
    first = [{"index": 1, "corrected_text": "修正", "changed": True, "reason": "asr_error"}]
    second = [{"index": 1, "corrected_text": "別修正", "changed": True, "reason": "asr_error"}]

    assert output_signature(first) != output_signature(second)


def test_repeat_stability_requires_at_least_two_runs() -> None:
    signature = [(1, "修正", True, "asr_error")]

    assert repeat_stability([signature]) is None
    assert repeat_stability([signature, signature]) is True
    assert repeat_stability([signature, [(1, "別修正", True, "asr_error")]]) is False
