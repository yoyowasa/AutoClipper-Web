import json
import time
from collections.abc import Callable, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.audio.volume_features import AudioFeatures
from app.candidates.merge_boundaries import Candidate
from app.scoring.score_schema import ClipCandidateScore, response_format_json_schema
from app.video.black_screen import VisualQuality


TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
}


class OpenAIResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any:
        pass


class OpenAIClientProtocol(Protocol):
    responses: OpenAIResponsesResource


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
    return payload


def candidate_score_cache_key(
    candidate: Candidate,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    visual_features: VisualQuality | dict[str, Any] | None = None,
) -> str:
    payload = build_score_input_payload(candidate, audio_features, visual_features)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
        model: str = "gpt-4o-mini",
        cache: OpenAIScoreCache | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.25,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self.model = model
        self.cache = cache or OpenAIScoreCache()
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep_func = sleep_func

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
        cache_key = candidate_score_cache_key(candidate, audio_features, visual_features)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        payload = build_score_input_payload(candidate, audio_features, visual_features)
        score = self._score_with_retries(payload)
        self.cache.set(cache_key, score)
        return score

    def _score_with_retries(self, payload: dict[str, Any]) -> ClipCandidateScore:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "Score clip candidates for a fully automated clipping app. "
                                "Return only the requested structured JSON. Do not ask for video files."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False),
                        },
                    ],
                    text={"format": response_format_json_schema()},
                )
                return parse_openai_score_response(response)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if not _is_transient_api_error(exc) or attempt >= self.max_retries:
                    break
                self.sleep_func(self.retry_backoff_seconds * (2**attempt))

        raise RuntimeError(f"OpenAI scoring failed: {last_error}") from last_error


def apply_openai_score_to_candidate(candidate: Candidate, score: ClipCandidateScore) -> Candidate:
    reject_reason = None if score.should_use else score.reason
    return candidate.model_copy(
        update={
            "ai_score": float(score.final_score),
            "final_score": float(score.final_score),
            "should_use": score.should_use,
            "title": score.title,
            "overlay_title": score.overlay_title,
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
