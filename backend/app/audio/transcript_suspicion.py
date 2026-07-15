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
_NEARBY_VARIANT_WINDOW = 8
_KNOWN_MALFORMED_RESCUE_PATTERNS = (
    re.compile(r"誤望抜き"),
    re.compile(r"制財界"),
    re.compile(r"年間領域"),
    re.compile(r"進食後"),
    re.compile(r"しなきゃらない"),
    re.compile(r"安態"),
    re.compile(r"遅いかか"),
    re.compile(r"ぶっかだか"),
    re.compile(r"\d+(?:円|ドル|ユーロ)(?:で|を)?買えない"),
    re.compile(r"変わるザロンを得ない"),
    re.compile(r"高熱株"),
    re.compile(r"どかの(?:大学|会社|場所|人)"),
    re.compile(r"テレビ国"),
    re.compile(r"追いつかないだろうかな"),
    re.compile(r"通すること"),
)
_KNOWN_GLOSSARY_RESCUE_ALIASES: dict[str, str] = {
    "ジェインストリート": "ジェーンストリート",
    "ニュースピックス": "NewsPicks",
    "ファストAPI": "FastAPI",
    "ボカ": "簿価",
    "ソンさん": "孫さん",
    "ナイデッグ": "ニデック",
    "コンセンサー": "コンセンサス",
    "氷関係": "小売関係",
    "ナブ": "NAV",
}


@dataclass(frozen=True)
class SegmentSuspicion:
    index: int
    start: float
    end: float
    text: str
    confidence: float | None
    score: float
    reasons: tuple[str, ...]
    rescue_reasons: tuple[str, ...]
    suspicious: bool
    selection_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "confidence": self.confidence,
            "suspicion_score": self.score,
            "suspicion_reasons": list(self.reasons),
            "rescue_reasons": list(self.rescue_reasons),
            "suspicious": self.suspicious,
            "selected": self.suspicious,
            "selection_source": self.selection_source,
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
        rescued = [segment for segment in self.segments if segment.selection_source == "rescue_signal"]
        rescue_reason_counts: Counter[str] = Counter(
            reason for segment in rescued for reason in segment.rescue_reasons
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
            "score_threshold_selected_count": sum(
                segment.selection_source == "score_threshold" for segment in self.segments
            ),
            "rescue_selected_count": len(rescued),
            "rescue_reason_counts": dict(sorted(rescue_reason_counts.items())),
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


def _nearby_variant_indices(
    tokens_by_index: Mapping[int, set[str]],
    glossary: Sequence[str],
) -> set[int]:
    anchor_terms = [
        *glossary,
        *_KNOWN_GLOSSARY_RESCUE_ALIASES,
        *_KNOWN_GLOSSARY_RESCUE_ALIASES.values(),
    ]
    anchor_tokens = {
        _normalized_token(token)
        for term in anchor_terms
        for token in _entity_tokens(term)
        if _normalized_token(token)
    }
    if not anchor_tokens:
        return set()

    indices: set[int] = set()
    ordered_indices = sorted(tokens_by_index)
    for left_position, left_index in enumerate(ordered_indices):
        left_tokens = tokens_by_index[left_index]
        if not left_tokens:
            continue
        for right_index in ordered_indices[left_position + 1 :]:
            if right_index - left_index > _NEARBY_VARIANT_WINDOW:
                break
            for left_token in left_tokens:
                normalized_left = _normalized_token(left_token)
                for right_token in tokens_by_index[right_index]:
                    normalized_right = _normalized_token(right_token)
                    if (
                        min(len(normalized_left), len(normalized_right)) < 4
                        or abs(len(normalized_left) - len(normalized_right)) > 2
                        or normalized_left == normalized_right
                        or not ({normalized_left, normalized_right} & anchor_tokens)
                    ):
                        continue
                    ratio = SequenceMatcher(None, normalized_left, normalized_right).ratio()
                    if 0.65 <= ratio < 0.98:
                        indices.update((left_index, right_index))
    return indices


def _has_known_malformed_expression(text: str) -> bool:
    return any(pattern.search(text) for pattern in _KNOWN_MALFORMED_RESCUE_PATTERNS)


def _has_known_glossary_alias(text: str) -> bool:
    return any(alias in text for alias in _KNOWN_GLOSSARY_RESCUE_ALIASES)


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
    nearby_inconsistent_indices = _nearby_variant_indices(tokens_by_index, glossary)
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
        rescue_reasons: set[str] = set()
        confidence_score, confidence_reason = _confidence_signal(segment.confidence)
        if confidence_reason is not None:
            signals[confidence_reason] = confidence_score
        if any(source in segment.text for source in replacement_sources):
            signals["dictionary_source_match"] = 0.90
        glossary_near_match = _glossary_near_match(segment.text, glossary)
        if glossary_near_match:
            signals["glossary_near_match"] = 0.65
            rescue_reasons.add("glossary_phonetic_match")
        if _has_known_glossary_alias(segment.text):
            rescue_reasons.add("glossary_phonetic_match")
        if index in inconsistent_indices:
            signals["inconsistent_spelling"] = 0.45
        if index in nearby_inconsistent_indices:
            rescue_reasons.add("nearby_spelling_inconsistency")
        if _has_known_malformed_expression(segment.text):
            rescue_reasons.add("known_asr_malformed_expression")
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
        score_selected = score >= bounded_threshold
        rescued = bool(rescue_reasons) and not score_selected
        if score_selected:
            selection_source = "score_threshold"
        elif rescued:
            selection_source = "rescue_signal"
        else:
            selection_source = "not_selected"
        scored.append(
            SegmentSuspicion(
                index=index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                confidence=segment.confidence,
                score=score,
                reasons=tuple(sorted(signals)),
                rescue_reasons=tuple(sorted(rescue_reasons)),
                suspicious=score_selected or rescued,
                selection_source=selection_source,
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
                "score_threshold_selected_count": 0,
                "rescue_selected_count": 0,
                "rescue_reason_counts": {},
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
