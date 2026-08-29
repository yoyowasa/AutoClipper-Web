from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_postprocess import repair_known_transcript_artifact_text
from app.audio.transcript_suspicion import contains_unexpected_script
from app.candidates.merge_boundaries import Candidate, TitleSource
from app.overlay_text import normalize_overlay_text
from app.scoring.clip_preferences import is_generic_intro_outro_text


TITLE_MAX_CHARS = 34
FILLER_PREFIXES = (
    "えー",
    "ええ",
    "あの",
    "えっと",
    "まあ",
    "そうですね",
)
PUNCTUATION_ONLY_RE = re.compile(r"^[\s。、，．！？!?…・:：;；「」『』（）()［］ー~〜-]+$")
REPEATED_PUNCTUATION_RE = re.compile(r"([。！？!?、，．.])\1+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?．.])\s*")


@dataclass(frozen=True)
class TitleResolution:
    title: str
    overlay_title: str | None
    title_source: TitleSource


def _plain_text(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    text = REPEATED_PUNCTUATION_RE.sub(r"\1", text)
    return text.strip(" \t\r\n、。，．.!！?？:：;；-ー~〜")


def _curated_plain_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _postprocessed_plain_text(value: str | None) -> str:
    clean = _plain_text(value)
    if not clean:
        return ""
    return _plain_text(repair_known_transcript_artifact_text(clean))


def _postprocessed_overlay_text(value: str | None) -> str:
    clean = normalize_overlay_text(value or "")
    if not clean:
        return ""
    return normalize_overlay_text(repair_known_transcript_artifact_text(clean))


def _strip_filler_prefixes(text: str) -> str:
    current = text
    changed = True
    while changed:
        changed = False
        current = current.lstrip(" 、。，．.!！?？")
        for prefix in FILLER_PREFIXES:
            if current.startswith(prefix):
                current = current[len(prefix) :].lstrip(" 、。，．.!！?？")
                changed = True
                break
    return current


def _usable_title(text: str) -> bool:
    clean = _plain_text(text)
    if not clean:
        return False
    if contains_unexpected_script(clean):
        return False
    if PUNCTUATION_ONLY_RE.match(clean):
        return False
    return clean not in FILLER_PREFIXES


def _segments_text_for_candidate(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> str:
    if not transcript_segments:
        return ""
    texts = [
        segment.text.strip()
        for segment in transcript_segments
        if segment.text.strip() and segment.end > candidate.start and segment.start < candidate.end
    ]
    return " ".join(texts).strip()


def _candidate_transcript_text(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> str:
    direct = _postprocessed_plain_text(candidate.transcript_text)
    if direct:
        return direct
    return _postprocessed_plain_text(_segments_text_for_candidate(candidate, transcript_segments))


def _meaningful_segment_title(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> str | None:
    if not transcript_segments:
        return None
    for segment in transcript_segments:
        if segment.end <= candidate.start or segment.start >= candidate.end:
            continue
        clean = _postprocessed_plain_text(segment.text)
        if not clean or is_generic_intro_outro_text(clean):
            continue
        if contains_unexpected_script(clean):
            return None
        title = title_from_transcript(clean)
        if title:
            return title
    return None


def title_from_transcript(text: str, *, max_chars: int = TITLE_MAX_CHARS) -> str | None:
    clean = _strip_filler_prefixes(_plain_text(text))
    if not _usable_title(clean):
        return None

    phrases = [part.strip() for part in SENTENCE_SPLIT_RE.split(clean) if part.strip()]
    phrase = next((part for part in phrases if _usable_title(_strip_filler_prefixes(part))), clean)
    phrase = _plain_text(_strip_filler_prefixes(phrase))
    if not _usable_title(phrase):
        return None
    if len(phrase) <= max_chars:
        return phrase
    return phrase[:max_chars].rstrip(" 、。，．.!！?？")


def deterministic_title(candidate_type: str, index: int) -> str:
    prefix = "Normal Clip" if candidate_type == "normal" else "Short"
    return f"{prefix} {index:02d}"


def resolve_candidate_title(
    candidate: Candidate,
    *,
    index: int,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
) -> TitleResolution:
    # A non-null source means this title was already resolved or explicitly curated.
    # Reapplying transcript repair can corrupt valid Japanese, such as a trailing `ー`.
    title_is_already_resolved = candidate.title_source is not None
    existing_title = (
        _curated_plain_text(candidate.title)
        if title_is_already_resolved
        else _postprocessed_plain_text(candidate.title)
    )
    if _usable_title(existing_title):
        source = candidate.title_source
        if source is None:
            source = "openai" if candidate.openai_scored is True or candidate.used_ai_score is True else "existing"
        overlay_title = (
            normalize_overlay_text(candidate.overlay_title or "")
            if title_is_already_resolved
            else _postprocessed_overlay_text(candidate.overlay_title)
        ) or (
            existing_title if candidate.type == "short" else None
        )
        return TitleResolution(title=existing_title, overlay_title=overlay_title, title_source=source)

    transcript_title = _meaningful_segment_title(candidate, transcript_segments)
    if transcript_title is None:
        transcript_title = title_from_transcript(
            _candidate_transcript_text(candidate, transcript_segments)
        )
    if transcript_title:
        overlay_title = _postprocessed_overlay_text(candidate.overlay_title) or (
            transcript_title if candidate.type == "short" else None
        )
        return TitleResolution(
            title=transcript_title,
            overlay_title=overlay_title,
            title_source="transcript_fallback",
        )

    fallback = deterministic_title(candidate.type, index)
    overlay_title = _postprocessed_overlay_text(candidate.overlay_title) or (
        fallback if candidate.type == "short" else None
    )
    return TitleResolution(
        title=fallback,
        overlay_title=overlay_title,
        title_source="deterministic_fallback",
    )


def candidate_with_title(
    candidate: Candidate,
    *,
    index: int,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
) -> Candidate:
    resolved = resolve_candidate_title(candidate, index=index, transcript_segments=transcript_segments)
    return candidate.model_copy(
        update={
            "title": resolved.title,
            "overlay_title": resolved.overlay_title if candidate.type == "short" else candidate.overlay_title,
            "title_source": resolved.title_source,
        }
    )


def titled_candidates(
    candidates: Sequence[Candidate],
    *,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
) -> list[Candidate]:
    return [
        candidate_with_title(candidate, index=index, transcript_segments=transcript_segments)
        for index, candidate in enumerate(candidates, start=1)
    ]
