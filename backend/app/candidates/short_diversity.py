from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.candidates.merge_boundaries import Candidate


@dataclass(frozen=True, slots=True)
class ShortDiversityMetadata:
    """Candidate 本体にない、ショート間の同一場面判定用metadata。"""

    moment_key: str | None = None
    parent_group: str | None = None
    parent_start: float | None = None
    parent_end: float | None = None
    evidence_segment_ids: tuple[str, ...] = ()
    heatmap_segment_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ShortDiversitySettings:
    max_overlap_seconds: float = 1.0
    max_parent_overlap_ratio: float = 0.8
    text_similarity_threshold: float = 0.9
    evidence_similarity_threshold: float = 0.8
    enforce_heatmap_segment_uniqueness: bool = False

    def __post_init__(self) -> None:
        if self.max_overlap_seconds < 0:
            raise ValueError("max_overlap_seconds must be non-negative")
        if not 0 < self.max_parent_overlap_ratio <= 1:
            raise ValueError("max_parent_overlap_ratio must be greater than 0 and at most 1")
        if not 0 <= self.text_similarity_threshold <= 1:
            raise ValueError("text_similarity_threshold must be between 0 and 1")
        if not 0 <= self.evidence_similarity_threshold <= 1:
            raise ValueError("evidence_similarity_threshold must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ShortDiversityRejection:
    candidate_id: str
    duplicate_of: str
    reasons: tuple[str, ...]
    overlap_seconds: float
    parent_overlap_ratio: float
    text_similarity: float
    evidence_similarity: float


@dataclass(frozen=True, slots=True)
class ShortDiversityResult:
    selected: tuple[Candidate, ...]
    rejected: tuple[ShortDiversityRejection, ...]
    requested_count: int

    @property
    def unfilled_count(self) -> int:
        return max(0, self.requested_count - len(self.selected))


MetadataInput = ShortDiversityMetadata | Mapping[str, Any]

_RISK_FLAG_KEYS = {
    "momentkey": "moment_key",
    "parentgroup": "parent_group",
    "evidencesegmentid": "evidence_segment_id",
}


def _normalized_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return normalized or None


def _metadata_from_risk_flags(candidate: Candidate) -> ShortDiversityMetadata:
    moment_key: str | None = None
    parent_group: str | None = None
    evidence_segment_ids: list[str] = []
    for flag in candidate.risk_flags:
        key, separator, value = flag.partition(":")
        if not separator or not value.strip():
            continue
        normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold())
        kind = _RISK_FLAG_KEYS.get(normalized_key)
        if kind == "moment_key" and moment_key is None:
            moment_key = value
        elif kind == "parent_group" and parent_group is None:
            parent_group = value
        elif kind == "evidence_segment_id":
            evidence_segment_ids.append(value)
    return ShortDiversityMetadata(
        moment_key=_normalized_identifier(moment_key),
        parent_group=_normalized_identifier(parent_group),
        evidence_segment_ids=tuple(item for item in (_normalized_identifier(value) for value in evidence_segment_ids) if item is not None),
    )


def _coerce_metadata(value: MetadataInput | None) -> ShortDiversityMetadata:
    if value is None:
        return ShortDiversityMetadata()
    if isinstance(value, ShortDiversityMetadata):
        metadata = value
    else:
        evidence = value.get("evidence_segment_ids", value.get("evidenceSegmentIds", ()))
        heatmap = value.get("heatmap_segment_ids", value.get("heatmapSegmentIds", ()))
        if isinstance(evidence, str):
            evidence = (evidence,)
        if isinstance(heatmap, str):
            heatmap = (heatmap,)
        metadata = ShortDiversityMetadata(
            moment_key=value.get("moment_key", value.get("momentKey")),
            parent_group=value.get("parent_group", value.get("parentGroup")),
            parent_start=value.get("parent_start", value.get("parentStart")),
            parent_end=value.get("parent_end", value.get("parentEnd")),
            evidence_segment_ids=tuple(str(item) for item in evidence or ()),
            heatmap_segment_ids=tuple(str(item) for item in heatmap or ()),
        )
    return ShortDiversityMetadata(
        moment_key=_normalized_identifier(metadata.moment_key),
        parent_group=_normalized_identifier(metadata.parent_group),
        parent_start=metadata.parent_start,
        parent_end=metadata.parent_end,
        evidence_segment_ids=tuple(
            item for item in (_normalized_identifier(value) for value in metadata.evidence_segment_ids) if item is not None
        ),
        heatmap_segment_ids=tuple(
            item for item in (_normalized_identifier(value) for value in metadata.heatmap_segment_ids) if item is not None
        ),
    )


def _candidate_metadata(
    candidate: Candidate,
    metadata_by_candidate_id: Mapping[str, MetadataInput],
) -> ShortDiversityMetadata:
    risk_fallback = _metadata_from_risk_flags(candidate)
    fallback = ShortDiversityMetadata(
        moment_key=_normalized_identifier(candidate.moment_key) or risk_fallback.moment_key,
        parent_group=risk_fallback.parent_group,
        parent_start=candidate.parent_start,
        parent_end=candidate.parent_end,
        evidence_segment_ids=tuple(_normalized_identifier(value) or value for value in (candidate.evidence_segment_ids or ()))
        or risk_fallback.evidence_segment_ids,
        heatmap_segment_ids=tuple(_normalized_identifier(value) or value for value in (candidate.heatmap_segment_ids or ())),
    )
    explicit_value = metadata_by_candidate_id.get(candidate.id)
    if explicit_value is None:
        return fallback
    explicit = _coerce_metadata(explicit_value)
    return ShortDiversityMetadata(
        moment_key=explicit.moment_key or fallback.moment_key,
        parent_group=explicit.parent_group or fallback.parent_group,
        parent_start=(explicit.parent_start if explicit.parent_start is not None else fallback.parent_start),
        parent_end=(explicit.parent_end if explicit.parent_end is not None else fallback.parent_end),
        evidence_segment_ids=(explicit.evidence_segment_ids if explicit.evidence_segment_ids else fallback.evidence_segment_ids),
        heatmap_segment_ids=(explicit.heatmap_segment_ids if explicit.heatmap_segment_ids else fallback.heatmap_segment_ids),
    )


def _effective_range(candidate: Candidate) -> tuple[float, float]:
    if candidate.refined_start is not None and candidate.refined_end is not None and candidate.refined_end > candidate.refined_start:
        return candidate.refined_start, candidate.refined_end
    return candidate.start, candidate.end


def _overlap_seconds(left: Candidate, right: Candidate) -> float:
    left_start, left_end = _effective_range(left)
    right_start, right_end = _effective_range(right)
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def _parent_overlap_ratio(
    left: ShortDiversityMetadata,
    right: ShortDiversityMetadata,
) -> float:
    if left.parent_start is None or left.parent_end is None or right.parent_start is None or right.parent_end is None:
        return 0.0
    overlap = max(
        0.0,
        min(left.parent_end, right.parent_end) - max(left.parent_start, right.parent_start),
    )
    shortest = min(
        left.parent_end - left.parent_start,
        right.parent_end - right.parent_start,
    )
    return overlap / shortest if shortest > 0 else 0.0


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _evidence_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / min(len(left_set), len(right_set))


def _duplicate_rejection(
    candidate: Candidate,
    selected: Candidate,
    *,
    candidate_metadata: ShortDiversityMetadata,
    selected_metadata: ShortDiversityMetadata,
    settings: ShortDiversitySettings,
) -> ShortDiversityRejection | None:
    overlap_seconds = _overlap_seconds(candidate, selected)
    parent_overlap_ratio = _parent_overlap_ratio(
        candidate_metadata,
        selected_metadata,
    )
    text_similarity = _text_similarity(
        candidate.transcript_text,
        selected.transcript_text,
    )
    evidence_similarity = _evidence_similarity(
        candidate_metadata.evidence_segment_ids,
        selected_metadata.evidence_segment_ids,
    )
    reasons: list[str] = []
    if overlap_seconds > settings.max_overlap_seconds:
        reasons.append("time_overlap_over_limit")
    if parent_overlap_ratio >= settings.max_parent_overlap_ratio:
        reasons.append("high_parent_overlap")
    if text_similarity >= settings.text_similarity_threshold:
        reasons.append("high_text_similarity")
    if evidence_similarity >= settings.evidence_similarity_threshold:
        reasons.append("high_evidence_similarity")
    if candidate_metadata.moment_key is not None and candidate_metadata.moment_key == selected_metadata.moment_key:
        reasons.append("same_moment_key")
    if candidate_metadata.parent_group is not None and candidate_metadata.parent_group == selected_metadata.parent_group:
        reasons.append("same_parent_group")
    if settings.enforce_heatmap_segment_uniqueness and set(candidate_metadata.heatmap_segment_ids) & set(
        selected_metadata.heatmap_segment_ids
    ):
        reasons.append("same_heatmap_segment")
    if not reasons:
        return None
    return ShortDiversityRejection(
        candidate_id=candidate.id,
        duplicate_of=selected.id,
        reasons=tuple(reasons),
        overlap_seconds=round(overlap_seconds, 6),
        parent_overlap_ratio=round(parent_overlap_ratio, 6),
        text_similarity=round(text_similarity, 6),
        evidence_similarity=round(evidence_similarity, 6),
    )


def select_diverse_shorts(
    candidates: Sequence[Candidate],
    requested_count: int,
    *,
    metadata_by_candidate_id: Mapping[str, MetadataInput] | None = None,
    settings: ShortDiversitySettings | None = None,
) -> ShortDiversityResult:
    """順位順の候補から、別場面のショートだけをrequested_countまで採用する。

    Candidateのhook領域・hook_textは比較しないため、同一ショート内のhook複製は
    重複判定の対象外となる。normal候補も判定対象外。
    """

    if requested_count < 0:
        raise ValueError("requested_count must be non-negative")
    resolved_settings = settings or ShortDiversitySettings()
    resolved_metadata = metadata_by_candidate_id or {}
    selected: list[Candidate] = []
    selected_metadata: list[ShortDiversityMetadata] = []
    rejected: list[ShortDiversityRejection] = []

    for candidate in candidates:
        if len(selected) >= requested_count:
            break
        if candidate.type != "short":
            continue
        metadata = _candidate_metadata(candidate, resolved_metadata)
        rejection = next(
            (
                duplicate
                for kept, kept_metadata in zip(
                    selected,
                    selected_metadata,
                    strict=True,
                )
                if (
                    duplicate := _duplicate_rejection(
                        candidate,
                        kept,
                        candidate_metadata=metadata,
                        selected_metadata=kept_metadata,
                        settings=resolved_settings,
                    )
                )
                is not None
            ),
            None,
        )
        if rejection is not None:
            rejected.append(rejection)
            continue
        selected.append(candidate)
        selected_metadata.append(metadata)

    return ShortDiversityResult(
        selected=tuple(selected),
        rejected=tuple(rejected),
        requested_count=requested_count,
    )
