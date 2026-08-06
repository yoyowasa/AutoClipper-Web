import json
import time
from dataclasses import dataclass, field
from collections.abc import Callable, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.audio.volume_features import AudioFeatures
from app.candidates.merge_boundaries import Candidate
from app.scoring.clip_preferences import CandidateClipPreference
from app.scoring.score_schema import ClipCandidateScore, response_format_json_schema
from app.video.black_screen import VisualQuality


TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
}

SYSTEM_PROMPT = (
    "Score clip candidates for a fully automated clipping app. "
    "Judge whether each candidate matches the supplied content preference and works as a standalone clip. "
    "Normal clips should contain a focused, complete topic. Shorts should contain a strong hook, reaction, "
    "punchline, or concise useful point. Reject generic greetings, endings, and promotional filler when the "
    "preference asks for their exclusion. When heatmap_features are present, their value is a relative 0-to-1 "
    "popularity signal within this video, not a view count. Use it only as supporting evidence and never as the "
    "sole reason to select a clip. Return only the requested structured JSON. Do not ask for video files."
)


class OpenAIResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any:
        pass


class OpenAIClientProtocol(Protocol):
    responses: OpenAIResponsesResource


@dataclass
class OpenAIScoringStats:
    model: str
    candidates_sent_to_openai: int = 0
    successful_scores: int = 0
    failed_scores: int = 0
    fallback_scores: int = 0
    cache_hits: int = 0
    total_api_calls: int = 0
    total_latency_seconds: float = 0.0
    max_latency_seconds: float = 0.0
    estimated_input_text_length: int = 0
    estimated_output_text_length: int = 0
    schema_validation_failures: int = 0
    error_types: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record_latency(self, seconds: float) -> None:
        elapsed = max(0.0, float(seconds))
        self.total_latency_seconds += elapsed
        self.max_latency_seconds = max(self.max_latency_seconds, elapsed)

    def record_error(self, exc: Exception) -> None:
        error_type = exc.__class__.__name__
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
        if len(self.errors) < 10:
            self.errors.append(f"{error_type}: {exc}")

    def to_summary(
        self,
        *,
        candidate_limit: int | None,
        candidates_considered: int,
        skipped_due_to_limit: int,
        fallback_scores: int,
        rule_score_only_candidates: int,
        candidates_selected_for_openai: int | None = None,
    ) -> dict[str, Any]:
        average_latency = None
        if self.total_api_calls > 0:
            average_latency = round(self.total_latency_seconds / self.total_api_calls, 6)
        selected_for_openai = (
            candidates_selected_for_openai
            if candidates_selected_for_openai is not None
            else self.candidates_sent_to_openai
        )
        return {
            "model": self.model,
            "candidate_limit": candidate_limit,
            "candidates_considered": candidates_considered,
            "candidates_eligible_for_openai_scoring": candidates_considered,
            "candidates_selected_for_openai": selected_for_openai,
            "candidates_sent_to_openai": self.candidates_sent_to_openai,
            "candidates_actually_sent": self.candidates_sent_to_openai,
            "successful_scores": self.successful_scores,
            "successful_structured_scores": self.successful_scores,
            "failed_scores": self.failed_scores,
            "failed_structured_scores": self.failed_scores,
            "fallback_scores": fallback_scores,
            "rule_score_only_candidates": rule_score_only_candidates,
            "skipped_due_to_limit": skipped_due_to_limit,
            "cache_hits": self.cache_hits,
            "average_latency_seconds": average_latency,
            "avg_latency_seconds": average_latency,
            "max_latency_seconds": round(self.max_latency_seconds, 6) if self.total_api_calls > 0 else None,
            "total_latency_seconds": round(self.total_latency_seconds, 6),
            "estimated_input_text_length": self.estimated_input_text_length,
            "estimated_output_text_length": self.estimated_output_text_length,
            "estimated_text_payload_size": self.estimated_input_text_length + self.estimated_output_text_length,
            "total_api_calls": self.total_api_calls,
            "schema_validation_failures": self.schema_validation_failures,
            "error_types": dict(sorted(self.error_types.items())),
            "errors": self.errors,
        }


class OpenAIScoreCache:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._items: dict[str, dict[str, Any]] = {}
        if self.path is not None and self.path.is_file():
            self._items = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key: str) -> ClipCandidateScore | None:
        payload = self._items.get(key)
        if payload is None:
            return None
        return ClipCandidateScore.model_validate(payload)

    def set(self, key: str, value: ClipCandidateScore) -> None:
        self._items[key] = value.model_dump()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._items, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


def _model_dump_or_none(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


def build_score_input_payload(
    candidate: Candidate,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
    selection_preference: CandidateClipPreference | dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate": {
            "id": candidate.id,
            "type": candidate.type,
            "start": candidate.start,
            "end": candidate.end,
            "duration": candidate.duration,
            "transcript_text": candidate.transcript_text,
            "rule_score": candidate.rule_score,
        },
        "audio_features": _model_dump_or_none(audio_features),
        "visual_features": _model_dump_or_none(visual_features),
    }
    if candidate.heatmap_value is not None:
        payload["heatmap_features"] = {
            "value": candidate.heatmap_value,
            "overlap_seconds": candidate.heatmap_overlap_seconds,
            "score_bonus": candidate.heatmap_score,
            "value_semantics": "relative_in_video_0_to_1_not_view_count",
            "supporting_signal_only": True,
        }
    if isinstance(selection_preference, CandidateClipPreference):
        payload["selection_preference"] = selection_preference.to_payload()
    elif isinstance(selection_preference, dict):
        payload["selection_preference"] = selection_preference
    return payload


def candidate_score_cache_key(
    candidate: Candidate,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
    selection_preference: CandidateClipPreference | dict[str, Any] | None = None,
) -> str:
    payload = build_score_input_payload(
        candidate,
        audio_features,
        visual_features,
        selection_preference,
    )
    cache_payload = {
        "system_prompt": SYSTEM_PROMPT,
        "input": payload,
    }
    encoded = json.dumps(
        cache_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _extract_response_text(response: Any) -> str:
    output_parsed = getattr(response, "output_parsed", None)
    if output_parsed is not None:
        return json.dumps(output_parsed)

    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)

    if isinstance(response, dict):
        if response.get("output_text"):
            return str(response["output_text"])
        if response.get("output_parsed") is not None:
            return json.dumps(response["output_parsed"])
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    for item in output or []:
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for content_item in content or []:
            text = content_item.get("text") if isinstance(content_item, dict) else getattr(content_item, "text", None)
            if text:
                return str(text)
    raise ValueError("OpenAI response did not include output text")


def parse_openai_score_response(response: Any) -> ClipCandidateScore:
    text = _extract_response_text(response)
    payload = json.loads(text)
    return ClipCandidateScore.model_validate(payload)


def _is_transient_api_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in TRANSIENT_STATUS_CODES:
        return True
    return exc.__class__.__name__ in TRANSIENT_ERROR_NAMES


def _load_default_client() -> OpenAIClientProtocol:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc
    return OpenAI()


class OpenAICandidateScorer:
    def __init__(
        self,
        client: OpenAIClientProtocol | None = None,
        model: str = "gpt-5.5",
        cache: OpenAIScoreCache | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.25,
        sleep_func: Callable[[float], None] = time.sleep,
        selection_preferences: dict[str, CandidateClipPreference] | None = None,
    ) -> None:
        self._client = client
        self.model = model
        self.cache = cache or OpenAIScoreCache()
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep_func = sleep_func
        self.selection_preferences = selection_preferences or {}
        self.stats = OpenAIScoringStats(model=model)

    @property
    def client(self) -> OpenAIClientProtocol:
        if self._client is None:
            self._client = _load_default_client()
        return self._client

    def score(
        self,
        candidate: Candidate,
        audio_features: AudioFeatures | dict[str, Any] | None = None,
        visual_features: VisualQuality | dict[str, Any] | None = None,
    ) -> ClipCandidateScore:
        preference = self.selection_preferences.get(candidate.type)
        cache_key = candidate_score_cache_key(
            candidate,
            audio_features,
            visual_features,
            preference,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached

        payload = build_score_input_payload(
            candidate,
            audio_features,
            visual_features,
            preference,
        )
        self.stats.candidates_sent_to_openai += 1
        try:
            score = self._score_with_retries(payload)
        except Exception as exc:
            self.stats.failed_scores += 1
            self.stats.record_error(exc)
            raise
        self.stats.successful_scores += 1
        self.cache.set(cache_key, score)
        return score

    def _score_with_retries(self, payload: dict[str, Any]) -> ClipCandidateScore:
        last_error: Exception | None = None
        user_content = json.dumps(payload, ensure_ascii=False)
        for attempt in range(self.max_retries + 1):
            try:
                self.stats.total_api_calls += 1
                self.stats.estimated_input_text_length += len(SYSTEM_PROMPT) + len(user_content)
                started_at = time.monotonic()
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": user_content,
                        },
                    ],
                    text={"format": response_format_json_schema()},
                )
                self.stats.record_latency(time.monotonic() - started_at)
                text = _extract_response_text(response)
                self.stats.estimated_output_text_length += len(text)
                return ClipCandidateScore.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                self.stats.schema_validation_failures += 1
                last_error = exc
                break
            except Exception as exc:
                self.stats.record_latency(time.monotonic() - started_at)
                last_error = exc
                if not _is_transient_api_error(exc) or attempt >= self.max_retries:
                    break
                self.sleep_func(self.retry_backoff_seconds * (2**attempt))

        if isinstance(last_error, (json.JSONDecodeError, ValidationError, ValueError)):
            raise RuntimeError(
                f"OpenAI scoring failed (schema_validation_failed: {last_error.__class__.__name__}): {last_error}"
            ) from last_error
        raise RuntimeError(
            f"OpenAI scoring failed ({last_error.__class__.__name__ if last_error else 'unknown'}): {last_error}"
        ) from last_error


def apply_openai_score_to_candidate(candidate: Candidate, score: ClipCandidateScore) -> Candidate:
    reject_reason = None if score.should_use else score.reason
    return candidate.model_copy(
        update={
            "ai_score": float(score.final_score),
            "final_score": float(score.final_score),
            "should_use": score.should_use,
            "title": score.title,
            "overlay_title": score.overlay_title,
            "title_source": "openai",
            "reason": score.reason,
            "risk_flags": score.risk_flags,
            "reject_reason": reject_reason,
        }
    )


def mark_candidate_rejected_for_scoring_failure(candidate: Candidate, reason: str) -> Candidate:
    return candidate.model_copy(
        update={
            "should_use": False,
            "final_score": candidate.rule_score,
            "reject_reason": f"openai_scoring_failed: {reason}",
            "risk_flags": [*candidate.risk_flags, "openai_scoring_failed"],
        }
    )


def score_candidate_with_openai(
    candidate: Candidate,
    scorer: OpenAICandidateScorer,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
) -> Candidate:
    try:
        score = scorer.score(candidate, audio_features=audio_features, visual_features=visual_features)
    except Exception as exc:
        return mark_candidate_rejected_for_scoring_failure(candidate, str(exc))
    return apply_openai_score_to_candidate(candidate, score)


def score_candidate_batch(
    candidates: Sequence[Candidate],
    scorer: OpenAICandidateScorer,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
) -> list[Candidate]:
    return [
        score_candidate_with_openai(
            candidate,
            scorer=scorer,
            audio_features=audio_features,
            visual_features=visual_features,
        )
        for candidate in candidates
    ]
