from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal


TitleSource = Literal["openai", "transcript_fallback", "deterministic_fallback"]
TITLE_MAX_LENGTH = 42
FILENAME_TITLE_MAX_LENGTH = 64
GENERIC_TITLE_PATTERN = re.compile(r"^(Normal clip|Short) \d+$", re.IGNORECASE)
TITLE_SPLIT_PATTERN = re.compile(r"[。．！？!?.]\s*|\n+")
EDGE_PUNCTUATION = " \t\r\n、。，．・.:：;；,!?！？「」『』（）()[]【】<>〈〉\"'`"
FILENAME_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


@dataclass(frozen=True)
class TitleFields:
    title: str
    overlay_title: str | None
    title_source: TitleSource
    filename_safe_title: str


def normalize_title_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(EDGE_PUNCTUATION)
    text = re.sub(r"([!?！？。]){2,}", r"\1", text)
    return text.strip(EDGE_PUNCTUATION)


def _truncate_title(text: str, max_length: int = TITLE_MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rstrip(EDGE_PUNCTUATION)
    return truncated or text[:max_length].strip()


def _meaningful_transcript_phrases(transcript_text: str) -> list[str]:
    text = normalize_title_text(transcript_text)
    if not text:
        return []
    phrases: list[str] = []
    for sentence in TITLE_SPLIT_PATTERN.split(text):
        sentence = normalize_title_text(sentence)
        if len(sentence) >= 6:
            phrases.append(sentence)
            continue
        if sentence:
            phrases.append(sentence)
    return phrases


def title_from_transcript(transcript_text: str, max_length: int = TITLE_MAX_LENGTH) -> str | None:
    phrase = next(iter(_meaningful_transcript_phrases(transcript_text)), "")
    if not phrase:
        return None
    return _truncate_title(phrase, max_length=max_length)


def deterministic_title(clip_type: str, index: int) -> str:
    prefix = "Short" if clip_type == "short" else "Normal Clip"
    return f"{prefix} {max(1, index):02d}"


def filename_safe_title(title: str) -> str:
    clean = normalize_title_text(title)
    clean = FILENAME_UNSAFE_PATTERN.sub("_", clean)
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("._ ")
    if not clean:
        clean = "clip"
    return clean[:FILENAME_TITLE_MAX_LENGTH].rstrip("._ ") or "clip"


def _usable_existing_title(title: Any) -> str | None:
    clean = normalize_title_text(title)
    if not clean:
        return None
    if GENERIC_TITLE_PATTERN.fullmatch(clean):
        return None
    return _truncate_title(clean)


def _source_for_existing_title(
    *,
    title_source: Any,
    used_ai_score: Any,
    openai_score_source: Any,
) -> TitleSource:
    if title_source in {"openai", "transcript_fallback", "deterministic_fallback"}:
        return title_source
    if used_ai_score is True or openai_score_source in {"preselection_pool", "finalist_on_demand"}:
        return "openai"
    return "transcript_fallback"


def build_title_fields(
    *,
    clip_type: str,
    index: int,
    transcript_text: str,
    title: Any = None,
    overlay_title: Any = None,
    title_source: Any = None,
    used_ai_score: Any = None,
    openai_score_source: Any = None,
) -> TitleFields:
    existing_title = _usable_existing_title(title)
    if existing_title is not None:
        source = _source_for_existing_title(
            title_source=title_source,
            used_ai_score=used_ai_score,
            openai_score_source=openai_score_source,
        )
        final_title = existing_title
    else:
        transcript_title = title_from_transcript(transcript_text)
        if transcript_title is not None:
            final_title = transcript_title
            source = "transcript_fallback"
        else:
            final_title = deterministic_title(clip_type, index)
            source = "deterministic_fallback"

    final_overlay_title = normalize_title_text(overlay_title) or None
    if clip_type == "short" and final_overlay_title is None:
        final_overlay_title = final_title

    return TitleFields(
        title=final_title,
        overlay_title=final_overlay_title,
        title_source=source,
        filename_safe_title=filename_safe_title(final_title),
    )


def apply_title_fields_to_candidate(candidate: Any, index: int) -> Any:
    fields = build_title_fields(
        clip_type=str(candidate.type),
        index=index,
        transcript_text=str(candidate.transcript_text or ""),
        title=candidate.title,
        overlay_title=candidate.overlay_title,
        title_source=getattr(candidate, "title_source", None),
        used_ai_score=getattr(candidate, "used_ai_score", None),
        openai_score_source=getattr(candidate, "openai_score_source", None),
    )
    return candidate.model_copy(
        update={
            "title": fields.title,
            "overlay_title": fields.overlay_title,
            "title_source": fields.title_source,
            "filename_safe_title": fields.filename_safe_title,
        }
    )


def apply_titles_by_type(candidates: list[Any], clip_type: str) -> list[Any]:
    return [
        apply_title_fields_to_candidate(candidate, index)
        for index, candidate in enumerate(
            [candidate for candidate in candidates if candidate.type == clip_type],
            start=1,
        )
    ]
