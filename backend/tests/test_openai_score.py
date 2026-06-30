import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.audio.volume_features import AudioFeatures
from app.candidates.merge_boundaries import Candidate
from app.jobs.runner import score_candidate_batch_for_worker
from app.scoring.openai_score import (
    OpenAICandidateScorer,
    OpenAIScoreCache,
    apply_openai_score_to_candidate,
    build_score_input_payload,
    candidate_score_cache_key,
    score_candidate_batch,
    score_candidate_with_openai,
)
from app.scoring.score_schema import (
    ClipCandidateScore,
    clip_candidate_score_json_schema,
    response_format_json_schema,
)
from app.video.black_screen import VisualQuality


VALID_SCORE = {
    "should_use": True,
    "final_score": 88,
    "hook_score": 90,
    "completeness_score": 80,
    "context_independence_score": 85,
    "information_density_score": 92,
    "title": "Automation mistake to fix",
    "overlay_title": "Fix this automation mistake",
    "reason": "Strong hook and clear standalone point.",
    "risk_flags": [],
}


class TransientOpenAIError(Exception):
    status_code = 429


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.output_text = json.dumps(payload)


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


def make_candidate(candidate_id: str = "cand_1", transcript_text: str = "why automation fails") -> Candidate:
    return Candidate(
        id=candidate_id,
        type="short",
        start=0.0,
        end=45.0,
        duration=45.0,
        transcript_text=transcript_text,
        rule_score=72.0,
    )


def make_audio_features() -> AudioFeatures:
    return AudioFeatures(
        duration=45.0,
        silence_ratio=0.05,
        speech_density=0.95,
        volume_peak=0.5,
        silent_seconds=2.25,
        speech_seconds=42.75,
    )


def make_visual_features() -> VisualQuality:
    return VisualQuality(
        duration=45.0,
        black_screen_ratio=0.0,
        usable_ratio=1.0,
        black_seconds=0.0,
        black_segments=[],
    )


def test_pydantic_model_validates_score_output() -> None:
    score = ClipCandidateScore.model_validate(VALID_SCORE)

    assert score.should_use is True
    assert score.final_score == 88
    assert score.title == "Automation mistake to fix"


def test_pydantic_model_rejects_extra_fields() -> None:
    payload = {**VALID_SCORE, "unexpected": True}

    with pytest.raises(ValidationError):
        ClipCandidateScore.model_validate(payload)


def test_response_format_uses_strict_json_schema() -> None:
    schema = clip_candidate_score_json_schema()
    response_format = response_format_json_schema()

    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())


def test_build_score_input_payload_sends_transcript_and_features_only() -> None:
    payload = build_score_input_payload(
        make_candidate(),
        audio_features=make_audio_features(),
        visual_features=make_visual_features(),
    )
    encoded = json.dumps(payload)

    assert payload["candidate"]["transcript_text"] == "why automation fails"
    assert payload["audio_features"]["silence_ratio"] == 0.05
    assert payload["visual_features"]["usable_ratio"] == 1.0
    assert "video_path" not in encoded
    assert "stored_path" not in encoded
    assert "mp4" not in encoded.lower()


def test_mocked_openai_score_updates_candidate() -> None:
    client = FakeClient([VALID_SCORE])
    scorer = OpenAICandidateScorer(client=client, sleep_func=lambda seconds: None)

    scored = score_candidate_with_openai(
        make_candidate(),
        scorer=scorer,
        audio_features=make_audio_features(),
        visual_features=make_visual_features(),
    )

    assert scored.should_use is True
    assert scored.ai_score == 88.0
    assert scored.final_score == 88.0
    assert scored.title == "Automation mistake to fix"
    assert scored.overlay_title == "Fix this automation mistake"
    assert scored.reject_reason is None
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["text"]["format"]["strict"] is True
    encoded_request = json.dumps(client.responses.calls[0]["input"], ensure_ascii=False)
    assert "video_path" not in encoded_request
    assert "stored_path" not in encoded_request
    assert ".mp4" not in encoded_request
    assert scorer.stats.successful_scores == 1
    assert scorer.stats.total_api_calls == 1
    assert scorer.stats.estimated_input_text_length > 0
    assert scorer.stats.estimated_output_text_length > 0


def test_transient_errors_are_retried() -> None:
    client = FakeClient([TransientOpenAIError("rate limited"), TransientOpenAIError("retry"), VALID_SCORE])
    scorer = OpenAICandidateScorer(
        client=client,
        max_retries=3,
        retry_backoff_seconds=0.0,
        sleep_func=lambda seconds: None,
    )

    score = scorer.score(make_candidate())

    assert score.final_score == 88
    assert len(client.responses.calls) == 3


def test_repeated_scoring_failure_marks_candidate_rejected() -> None:
    client = FakeClient([TransientOpenAIError("rate limited"), TransientOpenAIError("still limited")])
    scorer = OpenAICandidateScorer(
        client=client,
        max_retries=1,
        retry_backoff_seconds=0.0,
        sleep_func=lambda seconds: None,
    )

    scored = score_candidate_with_openai(make_candidate(), scorer=scorer)

    assert scored.should_use is False
    assert scored.final_score == 72.0
    assert scored.reject_reason is not None
    assert scored.reject_reason.startswith("openai_scoring_failed:")
    assert "openai_scoring_failed" in scored.risk_flags
    assert len(client.responses.calls) == 2
    assert scorer.stats.failed_scores == 1
    assert scorer.stats.total_api_calls == 2
    assert scorer.stats.error_types


def test_malformed_openai_response_is_reported_as_schema_failure() -> None:
    malformed = {key: value for key, value in VALID_SCORE.items() if key != "title"}
    client = FakeClient([malformed])
    scorer = OpenAICandidateScorer(client=client)

    scored = score_candidate_with_openai(make_candidate(), scorer=scorer)

    assert scored.should_use is False
    assert scored.reject_reason is not None
    assert "schema_validation_failed" in scored.reject_reason
    assert "openai_scoring_failed" in scored.risk_flags
    assert scorer.stats.failed_scores == 1
    assert scorer.stats.schema_validation_failures == 1


def test_scorer_summary_reports_counts_and_latency() -> None:
    client = FakeClient([VALID_SCORE])
    scorer = OpenAICandidateScorer(client=client)

    score_candidate_with_openai(make_candidate(), scorer=scorer)
    summary = scorer.stats.to_summary(
        candidate_limit=20,
        candidates_considered=100,
        skipped_due_to_limit=80,
        fallback_scores=0,
        rule_score_only_candidates=80,
        candidates_selected_for_openai=20,
    )

    assert summary["model"] == "gpt-5.5"
    assert summary["candidate_limit"] == 20
    assert summary["candidates_considered"] == 100
    assert summary["candidates_eligible_for_openai_scoring"] == 100
    assert summary["candidates_selected_for_openai"] == 20
    assert summary["candidates_sent_to_openai"] == 1
    assert summary["candidates_actually_sent"] == 1
    assert summary["successful_scores"] == 1
    assert summary["successful_structured_scores"] == 1
    assert summary["failed_scores"] == 0
    assert summary["failed_structured_scores"] == 0
    assert summary["skipped_due_to_limit"] == 80
    assert summary["rule_score_only_candidates"] == 80
    assert summary["total_api_calls"] == 1
    assert summary["average_latency_seconds"] is not None
    assert summary["avg_latency_seconds"] is not None
    assert summary["max_latency_seconds"] is not None
    assert summary["total_latency_seconds"] is not None
    assert summary["estimated_text_payload_size"] > 0
    assert summary["schema_validation_failures"] == 0


def test_score_cache_reuses_existing_result(tmp_path: Path) -> None:
    cache_path = tmp_path / "openai_score_cache.json"
    client = FakeClient([VALID_SCORE])
    cache = OpenAIScoreCache(cache_path)
    scorer = OpenAICandidateScorer(client=client, cache=cache)
    candidate = make_candidate()

    first = scorer.score(candidate, audio_features=make_audio_features())
    second = scorer.score(candidate, audio_features=make_audio_features())

    assert first == second
    assert len(client.responses.calls) == 1
    assert cache_path.is_file()

    new_cache = OpenAIScoreCache(cache_path)
    cache_key = candidate_score_cache_key(candidate, make_audio_features(), None)
    assert new_cache.get(cache_key) == first


def test_batch_scoring_for_worker_use() -> None:
    first_score = {**VALID_SCORE, "title": "First", "final_score": 81}
    second_score = {**VALID_SCORE, "title": "Second", "final_score": 74, "should_use": False}
    client = FakeClient([first_score, second_score])
    scorer = OpenAICandidateScorer(client=client)
    candidates = [
        make_candidate("cand_1", "why automation fails"),
        make_candidate("cand_2", "because this clip lacks context"),
    ]

    scored = score_candidate_batch(candidates, scorer=scorer, audio_features=make_audio_features())

    assert [candidate.title for candidate in scored] == ["First", "Second"]
    assert [candidate.title_source for candidate in scored] == ["openai", "openai"]
    assert [candidate.filename_safe_title for candidate in scored] == ["First", "Second"]
    assert [candidate.final_score for candidate in scored] == [81.0, 74.0]
    assert scored[0].should_use is True
    assert scored[1].should_use is False
    assert scored[1].reject_reason == "Strong hook and clear standalone point."
    assert len(client.responses.calls) == 2


def test_worker_runner_can_score_candidate_batch() -> None:
    client = FakeClient([{**VALID_SCORE, "title": "Worker scored"}])
    scorer = OpenAICandidateScorer(client=client)

    scored = score_candidate_batch_for_worker(
        [make_candidate("cand_worker", "why this automation fix matters")],
        audio_features=make_audio_features().model_dump(),
        visual_features=make_visual_features().model_dump(),
        scorer=scorer,
    )

    assert len(scored) == 1
    assert scored[0].title == "Worker scored"
    assert scored[0].should_use is True
    assert len(client.responses.calls) == 1


def test_apply_openai_score_sets_reject_reason_when_should_use_false() -> None:
    score = ClipCandidateScore.model_validate({**VALID_SCORE, "should_use": False})

    candidate = apply_openai_score_to_candidate(make_candidate(), score)

    assert candidate.should_use is False
    assert candidate.reject_reason == VALID_SCORE["reason"]
