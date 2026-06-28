import difflib
import re
from typing import Sequence

from app.candidates.merge_boundaries import Candidate


def time_overlap_seconds(left: Candidate, right: Candidate) -> float:
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def time_overlap_ratio(left: Candidate, right: Candidate) -> float:
    overlap = time_overlap_seconds(left, right)
    shortest = min(left.duration, right.duration)
    if shortest <= 0:
        return 0.0
    return overlap / shortest


def normalize_transcript(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
    if tokens:
        return " ".join(tokens)
    return re.sub(r"\s+", "", text).lower()


def transcript_similarity(left: str, right: str) -> float:
    normalized_left = normalize_transcript(left)
    normalized_right = normalize_transcript(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return difflib.SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _candidate_rank(candidate: Candidate) -> tuple[float, float, float]:
    return (
        candidate.rule_score if candidate.rule_score is not None else -1.0,
        len(candidate.transcript_text),
        candidate.duration,
    )


def _is_duplicate(
    candidate: Candidate,
    kept: Candidate,
    time_overlap_threshold: float,
    transcript_similarity_threshold: float,
    deduplicate_across_types: bool,
) -> bool:
    if not deduplicate_across_types and candidate.type != kept.type:
        return False
    return (
        time_overlap_ratio(candidate, kept) >= time_overlap_threshold
        or transcript_similarity(candidate.transcript_text, kept.transcript_text)
        >= transcript_similarity_threshold
    )


def deduplicate_candidates(
    candidates: Sequence[Candidate],
    time_overlap_threshold: float = 0.8,
    transcript_similarity_threshold: float = 0.9,
    deduplicate_across_types: bool = False,
) -> list[Candidate]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (_candidate_rank(candidate), -candidate.start),
        reverse=True,
    )
    kept: list[Candidate] = []
    for candidate in ranked:
        if any(
            _is_duplicate(
                candidate,
                kept_candidate,
                time_overlap_threshold=time_overlap_threshold,
                transcript_similarity_threshold=transcript_similarity_threshold,
                deduplicate_across_types=deduplicate_across_types,
            )
            for kept_candidate in kept
        ):
            continue
        kept.append(candidate)

    return sorted(kept, key=lambda candidate: (candidate.start, candidate.type, candidate.id))
