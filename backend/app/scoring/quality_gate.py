from typing import Any, Sequence

from pydantic import BaseModel, Field

from app.audio.silence_detect import SilenceSegment
from app.audio.volume_features import AudioFeatures, silence_seconds
from app.candidates.merge_boundaries import Candidate
from app.scoring.rule_score import incomplete_boundary_penalty


class QualityGateSettings(BaseModel):
    max_silence_ratio: float = Field(default=0.45, ge=0, le=1)
    min_speech_density: float = Field(default=0.4, ge=0, le=1)
    min_final_score: float = Field(default=60.0, ge=0, le=100)
    reject_incomplete_sentence: bool = True
    incomplete_penalty_threshold: float = Field(default=0.0, ge=0, le=25)
    reject_model_rejected_candidates: bool = True


class QualityGateResult(BaseModel):
    candidate_id: str
    passed: bool
    reasons: list[str]
    silence_ratio: float = Field(ge=0, le=1)
    speech_density: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=100)
    incomplete_penalty: float = Field(ge=0, le=25)


def effective_final_score(candidate: Candidate) -> float:
    for score in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if score is not None:
            return float(score)
    return 0.0


def _candidate_audio_quality(
    candidate: Candidate,
    audio_features: AudioFeatures | dict[str, Any] | None,
    silence_segments: Sequence[SilenceSegment] | None,
) -> tuple[float, float]:
    if silence_segments:
        local_segments: list[SilenceSegment] = []
        for segment in silence_segments:
            start = max(segment.start, candidate.start)
            end = min(segment.end, candidate.end)
            if end > start:
                local_segments.append(
                    SilenceSegment(
                        start=start - candidate.start,
                        end=end - candidate.start,
                        duration=end - start,
                    )
                )
        silent = silence_seconds(candidate.duration, local_segments)
        silence_ratio = silent / candidate.duration if candidate.duration > 0 else 0.0
        return silence_ratio, 1.0 - silence_ratio

    if isinstance(audio_features, AudioFeatures):
        return audio_features.silence_ratio, audio_features.speech_density

    if isinstance(audio_features, dict):
        silence_ratio = float(audio_features.get("silence_ratio", 0.0))
        speech_density = float(audio_features.get("speech_density", 1.0 - silence_ratio))
        return min(max(silence_ratio, 0.0), 1.0), min(max(speech_density, 0.0), 1.0)

    return 0.0, 1.0


def evaluate_quality_gate(
    candidate: Candidate,
    settings: QualityGateSettings | None = None,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
) -> QualityGateResult:
    parsed_settings = settings or QualityGateSettings()
    silence_ratio, speech_density = _candidate_audio_quality(
        candidate,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    final_score = effective_final_score(candidate)
    incomplete_penalty = incomplete_boundary_penalty(candidate.transcript_text)
    reasons: list[str] = []

    if parsed_settings.reject_model_rejected_candidates and candidate.should_use is False:
        reasons.append("model_rejected")
    if silence_ratio > parsed_settings.max_silence_ratio:
        reasons.append("max_silence_ratio")
    if speech_density < parsed_settings.min_speech_density:
        reasons.append("too_little_speech")
    if final_score < parsed_settings.min_final_score:
        reasons.append("low_final_score")
    if (
        parsed_settings.reject_incomplete_sentence
        and incomplete_penalty > parsed_settings.incomplete_penalty_threshold
    ):
        reasons.append("incomplete_sentence")

    return QualityGateResult(
        candidate_id=candidate.id,
        passed=not reasons,
        reasons=reasons,
        silence_ratio=round(silence_ratio, 6),
        speech_density=round(speech_density, 6),
        final_score=round(final_score, 6),
        incomplete_penalty=round(incomplete_penalty, 6),
    )


def evaluate_hard_gate(
    candidate: Candidate,
    settings: QualityGateSettings | None = None,
    audio_features: AudioFeatures | dict[str, Any] | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
) -> QualityGateResult:
    parsed_settings = settings or QualityGateSettings()
    silence_ratio, speech_density = _candidate_audio_quality(
        candidate,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    final_score = effective_final_score(candidate)
    incomplete_penalty = incomplete_boundary_penalty(candidate.transcript_text)
    reasons: list[str] = []

    if not candidate.transcript_text.strip():
        reasons.append("no_transcript_text")
    if candidate.duration <= 0 or candidate.end <= candidate.start:
        reasons.append("invalid_duration")
    if parsed_settings.reject_model_rejected_candidates and candidate.should_use is False:
        reasons.append("model_rejected")
    if silence_ratio > parsed_settings.max_silence_ratio:
        reasons.append("max_silence_ratio")
    if speech_density < parsed_settings.min_speech_density:
        reasons.append("too_little_speech")
    if (
        parsed_settings.reject_incomplete_sentence
        and incomplete_penalty > parsed_settings.incomplete_penalty_threshold
    ):
        reasons.append("incomplete_sentence")

    return QualityGateResult(
        candidate_id=candidate.id,
        passed=not reasons,
        reasons=reasons,
        silence_ratio=round(silence_ratio, 6),
        speech_density=round(speech_density, 6),
        final_score=round(final_score, 6),
        incomplete_penalty=round(incomplete_penalty, 6),
    )
