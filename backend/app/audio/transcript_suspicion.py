from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.audio.transcribe_faster_whisper import TranscriptSegment


TRANSCRIPT_SUSPICION_SEGMENTS_FILENAME = "transcript_suspicion_segments.json"
TRANSCRIPT_SUSPICION_SUMMARY_FILENAME = "transcript_suspicion_summary.json"
SUBTITLE_CORRECTION_TARGETS_FILENAME = "subtitle_correction_targets.json"

_ENTITY_TOKEN_RE = re.compile(r"[ァ-ヶー]{4,}|[A-Za-z][A-Za-z0-9+._-]{2,}")
_MIXED_SCRIPT_RE = re.compile(r"(?:[A-Za-z]{2,}[ァ-ヶー]+|[ァ-ヶー]+[A-Za-z]{2,})")
_KANJI_KATAKANA_BOUNDARY_RE = re.compile(r"(?:[一-龯][ァ-ヶー]{4,}|[ァ-ヶー]{4,}[一-龯])")
_JAPANESE_NUMERIC_BRIDGE_RE = re.compile(r"[一-龯ぁ-んァ-ヶー]\d{1,3}[一-龯ぁ-んァ-ヶー]")
_REPEATED_FRAGMENT_RE = re.compile(r"(.{2,8}?)(?:\1){2,}")
_LIST_SEPARATOR_RE = re.compile(r"[、,]")
_CJK_COMPOUND_RE = re.compile(r"[一-龯]{2,8}")


@dataclass(frozen=True)
class SegmentSuspicion:
    index: int
    start: float
    end: float
    text: str
    confidence: float | None
    score: float
    reasons: tuple[str, ...]
    suspicious: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "confidence": self.confidence,
            "suspicion_score": self.score,
            "suspicion_reasons": list(self.reasons),
            "suspicious": self.suspicious,
        }


@dataclass(frozen=True)
class TranscriptSuspicionResult:
    segments: tuple[SegmentSuspicion, ...]
    threshold: float
    context_segments: int
    batch_size: int
    context_indices: tuple[int, ...]

    @property
    def target_indices(self) -> list[int]:
        return [segment.index for segment in self.segments if segment.suspicious]

    @property
    def suspicion_by_index(self) -> dict[int, SegmentSuspicion]:
        return {segment.index: segment for segment in self.segments}

    def summary(self) -> dict[str, Any]:
        targets = self.target_indices
        reason_counts: Counter[str] = Counter(
            reason
            for segment in self.segments
            if segment.suspicious
            for reason in segment.reasons
        )
        return {
            "segment_count": len(self.segments),
            "suspicious_segment_count": len(targets),
            "suspicious_ratio": round(len(targets) / len(self.segments), 6) if self.segments else 0.0,
            "context_segment_count": len(self.context_indices),
            "unique_segments_sent": len(set(targets) | set(self.context_indices)),
            "threshold": self.threshold,
            "batch_size": self.batch_size,
            "estimated_api_calls": (len(targets) + self.batch_size - 1) // self.batch_size,
            "reason_counts": dict(sorted(reason_counts.items())),
            "filter_failed": False,
        }


def _normalized_token(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip("._-+ ")


def select_read_only_context_indices(
    target_indices: Sequence[int],
    *,
    segment_count: int,
    context_segments: int,
) -> tuple[int, ...]:
    targets = sorted(set(target_indices))
    if not targets or context_segments <= 0:
        return ()
    target_set = set(targets)
    candidates: set[int] = set()
    for index in targets:
        candidates.update(
            range(max(0, index - context_segments), min(segment_count, index + context_segments + 1))
        )
    candidates.difference_update(target_set)
    budget = context_segments * 2
    if len(candidates) <= budget:
        return tuple(sorted(candidates))

    def rank(index: int) -> tuple[int, int, int]:
        adjacent_targets = sum(abs(index - target) <= context_segments for target in targets)
        nearest_distance = min(abs(index - target) for target in targets)
        return (-adjacent_targets, nearest_distance, index)

    return tuple(sorted(sorted(candidates, key=rank)[:budget]))


def _entity_tokens(text: str) -> set[str]:
    return {match.group(0) for match in _ENTITY_TOKEN_RE.finditer(text)}


def _confidence_signal(confidence: float | None) -> tuple[float, str | None]:
    if confidence is None:
        return 0.15, "missing_asr_confidence"
    if confidence < 0.65:
        return 0.75, "low_asr_confidence"
    if confidence < 0.75:
        return 0.55, "low_asr_confidence"
    if confidence < 0.85:
        return 0.40, "low_asr_confidence"
    if confidence < 0.92:
        return 0.20, "moderate_asr_confidence"
    return 0.0, None


def _variant_indices(tokens_by_index: Mapping[int, set[str]]) -> set[int]:
    occurrences: dict[str, set[int]] = defaultdict(set)
    original: dict[str, str] = {}
    for index, tokens in tokens_by_index.items():
        for token in tokens:
            normalized = _normalized_token(token)
            if normalized:
                occurrences[normalized].add(index)
                original.setdefault(normalized, token)

    values = list(occurrences)
    indices: set[int] = set()
    for left_position, left in enumerate(values):
        for right in values[left_position + 1 :]:
            if abs(len(left) - len(right)) > 4 or min(len(left), len(right)) < 4:
                continue
            ratio = SequenceMatcher(None, left, right).ratio()
            if 0.72 <= ratio < 0.98:
                indices.update(occurrences[left])
                indices.update(occurrences[right])
    return indices


def _glossary_near_match(text: str, glossary: Sequence[str]) -> bool:
    text_tokens = {_normalized_token(token) for token in _entity_tokens(text)}
    glossary_tokens = {_normalized_token(term) for term in glossary if term.strip()}
    for text_token in text_tokens:
        for glossary_token in glossary_tokens:
            if not text_token or not glossary_token or text_token == glossary_token:
                continue
            if abs(len(text_token) - len(glossary_token)) <= 4 and SequenceMatcher(
                None, text_token, glossary_token
            ).ratio() >= 0.72:
                return True
    return False


def analyze_transcript_suspicion(
    segments: Sequence[TranscriptSegment],
    *,
    threshold: float = 0.40,
    context_segments: int = 2,
    batch_size: int = 40,
    glossary: Sequence[str] = (),
    replacements: Mapping[str, str] | None = None,
) -> TranscriptSuspicionResult:
    bounded_threshold = max(0.0, min(1.0, float(threshold)))
    bounded_context = max(0, int(context_segments))
    bounded_batch_size = max(1, int(batch_size))
    tokens_by_index = {index: _entity_tokens(segment.text) for index, segment in enumerate(segments)}
    token_counts = Counter(
        _normalized_token(token)
        for tokens in tokens_by_index.values()
        for token in tokens
        if _normalized_token(token)
    )
    inconsistent_indices = _variant_indices(tokens_by_index)
    replacement_sources = tuple(source for source in (replacements or {}) if source)
    list_like_indices = {
        index for index, segment in enumerate(segments) if len(_LIST_SEPARATOR_RE.findall(segment.text)) >= 3
    }
    repeated_cjk_indices: set[int] = set()
    if len(segments) >= 100:
        cjk_compound_occurrences: dict[str, set[int]] = defaultdict(set)
        for index, segment in enumerate(segments):
            for compound in _CJK_COMPOUND_RE.findall(segment.text):
                cjk_compound_occurrences[compound].add(index)
        repeated_cjk_indices = {
            index for indices in cjk_compound_occurrences.values() if len(indices) >= 2 for index in indices
        }
    scored: list[SegmentSuspicion] = []

    for index, segment in enumerate(segments):
        signals: dict[str, float] = {}
        confidence_score, confidence_reason = _confidence_signal(segment.confidence)
        if confidence_reason is not None:
            signals[confidence_reason] = confidence_score
        if any(source in segment.text for source in replacement_sources):
            signals["dictionary_source_match"] = 0.90
        if _glossary_near_match(segment.text, glossary):
            signals["glossary_near_match"] = 0.65
        if index in inconsistent_indices:
            signals["inconsistent_spelling"] = 0.45
        if tokens_by_index[index]:
            signals["entity_candidate"] = 0.15
        if any(token_counts[_normalized_token(token)] >= 2 for token in tokens_by_index[index]):
            signals["repeated_entity_candidate"] = 0.30
        if index in list_like_indices:
            signals["list_like_segment"] = 0.45
        if index + 1 in list_like_indices:
            signals["list_introduction_context"] = 0.40
        if _MIXED_SCRIPT_RE.search(segment.text):
            signals["mixed_script_token"] = 0.50
        if _KANJI_KATAKANA_BOUNDARY_RE.search(segment.text):
            signals["kanji_katakana_boundary"] = 0.15
        if _JAPANESE_NUMERIC_BRIDGE_RE.search(segment.text):
            signals["numeric_or_latin_anomaly"] = 0.35
        if _REPEATED_FRAGMENT_RE.search(segment.text):
            signals["repetition_anomaly"] = 0.65
        if index in repeated_cjk_indices:
            signals["repeated_cjk_compound"] = 0.40
        if len(segment.text.strip()) >= 90:
            signals["unusually_long_segment"] = 0.20
        elif 0 < len(segment.text.strip()) <= 2:
            signals["unusually_short_segment"] = 0.15
        if index == 0:
            signals["opening_context"] = 0.35

        score = round(min(1.0, sum(signals.values())), 6)
        scored.append(
            SegmentSuspicion(
                index=index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                confidence=segment.confidence,
                score=score,
                reasons=tuple(sorted(signals)),
                suspicious=score >= bounded_threshold,
            )
        )

    target_indices = {segment.index for segment in scored if segment.suspicious}
    sorted_targets = sorted(target_indices)
    context_index_set: set[int] = set()
    for batch_start in range(0, len(sorted_targets), bounded_batch_size):
        context_index_set.update(
            select_read_only_context_indices(
                sorted_targets[batch_start : batch_start + bounded_batch_size],
                segment_count=len(segments),
                context_segments=bounded_context,
            )
        )
    context_indices = tuple(sorted(context_index_set))
    return TranscriptSuspicionResult(
        segments=tuple(scored),
        threshold=bounded_threshold,
        context_segments=bounded_context,
        batch_size=bounded_batch_size,
        context_indices=context_indices,
    )


def write_suspicion_artifacts(result: TranscriptSuspicionResult, output_dir: str | Path) -> list[Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    segments_path = directory / TRANSCRIPT_SUSPICION_SEGMENTS_FILENAME
    summary_path = directory / TRANSCRIPT_SUSPICION_SUMMARY_FILENAME
    targets_path = directory / SUBTITLE_CORRECTION_TARGETS_FILENAME
    segments_path.write_text(
        json.dumps([segment.as_dict() for segment in result.segments], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(result.summary(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    targets_path.write_text(
        json.dumps(
            {
                "target_indices": result.target_indices,
                "context_indices": list(result.context_indices),
                "targets": [
                    segment.as_dict() for segment in result.segments if segment.suspicious
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [segments_path, summary_path, targets_path]


def write_suspicion_failure_summary(
    output_dir: str | Path,
    *,
    segment_count: int,
    threshold: float,
    exc: Exception,
) -> Path:
    path = Path(output_dir) / TRANSCRIPT_SUSPICION_SUMMARY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "segment_count": segment_count,
                "suspicious_segment_count": 0,
                "suspicious_ratio": 0.0,
                "context_segment_count": 0,
                "unique_segments_sent": 0,
                "threshold": threshold,
                "reason_counts": {},
                "filter_failed": True,
                "error": f"{type(exc).__name__}: {exc}",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
