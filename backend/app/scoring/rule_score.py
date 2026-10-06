import re
import unicodedata
from typing import Sequence

from pydantic import BaseModel, Field

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import AudioFeatures, silence_seconds
from app.candidates.merge_boundaries import Candidate
from app.scoring.clip_preferences import (
    CandidateClipPreference,
    guidance_match_score,
    normal_topic_structure_score,
    selection_content_flags,
    selection_content_penalty,
)


HOOK_KEYWORDS = {
    "ai",
    "automation",
    "before",
    "best",
    "danger",
    "fail",
    "fix",
    "how",
    "important",
    "mistake",
    "money",
    "never",
    "secret",
    "stop",
    "truth",
    "why",
}

JAPANESE_HOOK_KEYWORDS = {
    "なぜ",
    "理由",
    "実は",
    "初めて",
    "重要",
    "大事",
    "発表",
    "結論",
    "失敗",
    "危険",
    "秘密",
    "本当",
    "復帰",
    "倒れ",
    "事件",
    "まさか",
    "やば",
}

HEATMAP_SCORE_MAX = 10.0
OPENING_SCORE_MAX = 15.0
CODEX_OPENING_SCORE_WEIGHT = 0.2
JA_INCOMPLETE_START_PREFIXES = ("で、", "で，", "だから", "それ", "あれ", "えー", "ええと", "えっと", "あの")


def _weak_japanese_start(text: str) -> bool:
    return unicodedata.normalize("NFKC", text).lstrip().startswith(JA_INCOMPLETE_START_PREFIXES)


def opening_score(candidate: Candidate, segments: Sequence[TranscriptSegment]) -> float:
    """Approximate the first three seconds from overlapping segment text and speech time."""
    start, end = candidate.start, min(candidate.end, candidate.start + 3.0)
    if end <= start:
        return 0.0
    spans: list[tuple[float, float]] = []
    texts: list[str] = []
    for segment in sorted(segments, key=lambda item: (item.start, item.end)):
        left, right = max(start, segment.start), min(end, segment.end)
        if right <= left or not segment.text.strip() or segment.end <= segment.start:
            continue
        spans.append((left, right))
        # Segment timing is sufficient; proportional slicing keeps later topic words out of the opening.
        length = len(segment.text)
        first = int(length * (left - segment.start) / (segment.end - segment.start))
        last = min(length, int(length * (right - segment.start) / (segment.end - segment.start) + 0.999999))
        texts.append(segment.text[first:last])
    text = unicodedata.normalize("NFKC", "".join(texts)).strip()
    if not text:
        return 0.0
    speech = 0.0
    covered_end = start
    for left, right in sorted(spans):
        speech += max(0.0, right - max(left, covered_end))
        covered_end = max(covered_end, right)
    density = min(1.0, speech / (end - start))
    concrete = bool(re.search(r"\d|[ァ-ヶー]{2,}|[一-龯々]{2,}", text)) or any(
        keyword in text for keyword in JAPANESE_HOOK_KEYWORDS
    )
    weak = _weak_japanese_start(text)
    return round(_clamp(density * 5.0 + (5.0 if concrete else 0.0) + (0.0 if weak else 5.0)
                        - (5.0 if weak else 0.0), maximum=OPENING_SCORE_MAX), 3)


def codex_opening_bonus(score: float | None, audience_familiarity: str) -> float:
    return CODEX_OPENING_SCORE_WEIGHT * (score or 0.0) / OPENING_SCORE_MAX if audience_familiarity == "unknown" else 0.0

INCOMPLETE_START_WORDS = {
    "and",
    "because",
    "but",
    "if",
    "so",
    "then",
    "therefore",
    "this",
    "that",
    "which",
}

INCOMPLETE_END_WORDS = {
    "and",
    "because",
    "but",
    "if",
    "or",
    "so",
    "then",
    "to",
    "when",
    "while",
}


class RuleScoreBreakdown(BaseModel):
    opening_score: float = Field(default=0, ge=0, le=OPENING_SCORE_MAX)
    hook_score: float = Field(ge=0, le=15)
    guidance_score: float = Field(ge=0, le=15)
    silence_score: float = Field(ge=0, le=15)
    speech_density_score: float = Field(ge=0, le=15)
    duration_score: float = Field(ge=0, le=20)
    transcript_length_score: float = Field(ge=0, le=15)
    audio_peak_score: float = Field(ge=0, le=10)
    heatmap_score: float = Field(ge=0, le=HEATMAP_SCORE_MAX)
    incomplete_penalty: float = Field(ge=0, le=25)
    generic_content_penalty: float = Field(ge=0, le=25)
    final_score: float = Field(ge=0, le=100)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return min(max(value, minimum), maximum)


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", unicodedata.normalize("NFKC", text).lower())


def _text_units(text: str) -> int:
    compact = re.sub(r"\s+", "", text)
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", compact):
        return max(0, len(compact) // 3)
    words = _words(text)
    if len(words) >= 2:
        return len(words)
    return max(0, len(compact) // 3)


def hook_keyword_score(transcript_text: str, hook_keywords: set[str] | None = None) -> float:
    words = set(_words(transcript_text))
    keywords = hook_keywords or (HOOK_KEYWORDS | JAPANESE_HOOK_KEYWORDS)
    ascii_keywords = {keyword for keyword in keywords if keyword.isascii()}
    substring_keywords = keywords - ascii_keywords
    hits = len(words & ascii_keywords)
    normalized = unicodedata.normalize("NFKC", transcript_text).lower()
    hits += sum(1 for keyword in substring_keywords if keyword.lower() in normalized)
    return _clamp(hits * 5.0, maximum=15.0)


def _score_against_range(value: float, minimum: float, maximum: float, max_score: float) -> float:
    if minimum <= value <= maximum:
        return max_score
    if value < minimum:
        return _clamp(max_score * (value / minimum), maximum=max_score)
    return _clamp(max_score * (maximum / value), maximum=max_score)


def duration_fit_score(candidate: Candidate) -> float:
    if candidate.type == "short":
        return _score_against_range(candidate.duration, 20.0, 75.0, 20.0)
    return _score_against_range(candidate.duration, 90.0, 600.0, 20.0)


def transcript_length_score(candidate: Candidate) -> float:
    units = _text_units(candidate.transcript_text)
    if candidate.type == "short":
        return _score_against_range(float(units), 18.0, 160.0, 15.0)
    return _score_against_range(float(units), 80.0, 1400.0, 15.0)


def _candidate_silence_ratio(
    candidate: Candidate,
    silence_segments: Sequence[SilenceSegment],
    fallback: float,
) -> float:
    if not silence_segments or candidate.duration <= 0:
        return _clamp(fallback, maximum=1.0)
    local_segments: list[SilenceSegment] = []
    for segment in silence_segments:
        start = max(segment.start, candidate.start)
        end = min(segment.end, candidate.end)
        if end > start:
            local_segments.append(
                SilenceSegment(start=start - candidate.start, end=end - candidate.start, duration=end - start)
            )
    return silence_seconds(candidate.duration, local_segments) / candidate.duration


def silence_ratio_score(silence_ratio: float) -> float:
    if silence_ratio <= 0.08:
        return 15.0
    if silence_ratio <= 0.22:
        return 12.0
    if silence_ratio <= 0.4:
        return 8.0
    if silence_ratio <= 0.6:
        return 4.0
    return 0.0


def speech_density_score(speech_density: float) -> float:
    if 0.65 <= speech_density <= 1.0:
        return 15.0
    if 0.45 <= speech_density < 0.65:
        return 11.0
    if 0.25 <= speech_density < 0.45:
        return 6.0
    return 2.0 if speech_density > 0 else 0.0


def audio_peak_score(volume_peak: float) -> float:
    peak = _clamp(volume_peak, maximum=1.0)
    if 0.25 <= peak <= 0.9:
        return 10.0
    if 0.12 <= peak < 0.25:
        return 7.0
    if 0.9 < peak <= 0.98:
        return 6.0
    if peak > 0.98:
        return 3.0
    return 2.0 if peak > 0 else 0.0


def heatmap_popularity_score(value: float | None) -> float:
    if value is None:
        return 0.0
    return _clamp(value, maximum=1.0) * HEATMAP_SCORE_MAX


def incomplete_boundary_penalty(transcript_text: str, *, audience_familiarity: str = "known") -> float:
    text = unicodedata.normalize("NFKC", transcript_text).strip()
    if not text:
        return 25.0

    words = _words(text)
    penalty = 0.0
    if audience_familiarity == "unknown" and _weak_japanese_start(text):
        penalty += 10.0
    if words and words[0] in INCOMPLETE_START_WORDS:
        penalty += 10.0
    if words and words[-1] in INCOMPLETE_END_WORDS:
        penalty += 10.0
    if text[0] in ",.;:)]}":
        penalty += 5.0
    if text[-1] in ",;:":
        penalty += 5.0
    return _clamp(penalty, maximum=25.0)


def score_candidate(
    candidate: Candidate,
    audio_features: AudioFeatures | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
    hook_keywords: set[str] | None = None,
    selection_preference: CandidateClipPreference | None = None,
    transcript_segments: Sequence[TranscriptSegment] = (),
) -> RuleScoreBreakdown:
    fallback_silence_ratio = audio_features.silence_ratio if audio_features else 0.0
    silence_ratio = _candidate_silence_ratio(candidate, silence_segments or [], fallback_silence_ratio)
    speech_density = 1.0 - silence_ratio
    if audio_features and not silence_segments:
        speech_density = audio_features.speech_density
    volume_peak = audio_features.volume_peak if audio_features else 0.5
    preference = selection_preference or CandidateClipPreference()

    hook = (
        hook_keyword_score(candidate.transcript_text, hook_keywords=hook_keywords)
        if candidate.type == "short"
        else normal_topic_structure_score(candidate.transcript_text)
    )
    guidance = guidance_match_score(candidate.transcript_text, preference)
    silence = silence_ratio_score(silence_ratio)
    speech = speech_density_score(speech_density)
    duration = duration_fit_score(candidate)
    length = transcript_length_score(candidate)
    peak = audio_peak_score(volume_peak)
    heatmap = heatmap_popularity_score(candidate.heatmap_value)
    opening = opening_score(candidate, transcript_segments) if candidate.type == "short" else 0.0
    familiarity = preference.audience_familiarity if candidate.type == "short" else "known"
    penalty = incomplete_boundary_penalty(candidate.transcript_text, audience_familiarity=familiarity)
    generic_penalty = selection_content_penalty(
        candidate.transcript_text,
        preference,
        candidate.type,
    )
    final = _clamp(
        hook
        + guidance
        + silence
        + speech
        + duration
        + length
        + peak
        + heatmap
        + (opening if familiarity == "unknown" else 0.0)
        - penalty
        - generic_penalty
    )

    return RuleScoreBreakdown(
        opening_score=opening,
        hook_score=hook,
        guidance_score=guidance,
        silence_score=silence,
        speech_density_score=speech,
        duration_score=duration,
        transcript_length_score=length,
        audio_peak_score=peak,
        heatmap_score=heatmap,
        incomplete_penalty=penalty,
        generic_content_penalty=generic_penalty,
        final_score=round(final, 3),
    )


def apply_rule_score(
    candidate: Candidate,
    audio_features: AudioFeatures | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
    hook_keywords: set[str] | None = None,
    selection_preference: CandidateClipPreference | None = None,
    transcript_segments: Sequence[TranscriptSegment] = (),
) -> Candidate:
    breakdown = score_candidate(
        candidate,
        audio_features=audio_features,
        silence_segments=silence_segments,
        hook_keywords=hook_keywords,
        selection_preference=selection_preference,
        transcript_segments=transcript_segments,
    )
    preference = selection_preference or CandidateClipPreference()
    flags = list(candidate.risk_flags)
    for flag in selection_content_flags(
        candidate.transcript_text,
        preference,
        candidate.type,
    ):
        if flag not in flags:
            flags.append(flag)
    return candidate.model_copy(
        update={
            "rule_score": breakdown.final_score,
            "opening_score": breakdown.opening_score if candidate.type == "short" else None,
            "heatmap_score": (
                breakdown.heatmap_score if candidate.heatmap_value is not None else None
            ),
            "risk_flags": flags,
        }
    )


def score_candidates(
    candidates: Sequence[Candidate],
    audio_features: AudioFeatures | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
    hook_keywords: set[str] | None = None,
    selection_preferences: dict[str, CandidateClipPreference] | None = None,
    transcript_segments: Sequence[TranscriptSegment] = (),
) -> list[Candidate]:
    return [
        apply_rule_score(
            candidate,
            audio_features=audio_features,
            silence_segments=silence_segments,
            hook_keywords=hook_keywords,
            selection_preference=(selection_preferences or {}).get(candidate.type),
            transcript_segments=transcript_segments,
        )
        for candidate in candidates
    ]
