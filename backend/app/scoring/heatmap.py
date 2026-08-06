from collections.abc import Sequence

from app.candidates.merge_boundaries import Candidate
from app.video.heatmap import HeatmapSegment


def candidate_heatmap_features(
    candidate: Candidate,
    segments: Sequence[HeatmapSegment],
) -> tuple[float, float]:
    weighted_value = 0.0
    overlap_seconds = 0.0
    for segment in segments:
        if segment.end_time <= candidate.start:
            continue
        if segment.start_time >= candidate.end:
            break
        overlap = min(candidate.end, segment.end_time) - max(candidate.start, segment.start_time)
        if overlap <= 0:
            continue
        overlap_seconds += overlap
        weighted_value += overlap * segment.value
    if overlap_seconds <= 0:
        return 0.0, 0.0
    return round(weighted_value / overlap_seconds, 6), round(overlap_seconds, 6)


def annotate_candidates_with_heatmap(
    candidates: Sequence[Candidate],
    segments: Sequence[HeatmapSegment],
) -> list[Candidate]:
    if not segments:
        return [
            candidate.model_copy(
                update={
                    "heatmap_value": None,
                    "heatmap_overlap_seconds": None,
                    "heatmap_score": None,
                    "heatmap_direct_score": None,
                }
            )
            for candidate in candidates
        ]
    annotated: list[Candidate] = []
    for candidate in candidates:
        value, overlap_seconds = candidate_heatmap_features(candidate, segments)
        direct_score = (
            round(min(1.0, value * overlap_seconds / candidate.duration), 6)
            if candidate.generation_source == "heatmap_interval" and candidate.duration > 0
            else candidate.heatmap_direct_score
        )
        annotated.append(
            candidate.model_copy(
                update={
                    "heatmap_value": value,
                    "heatmap_overlap_seconds": overlap_seconds,
                    "heatmap_score": (
                        round(value * 10.0, 6)
                        if candidate.heatmap_score is not None
                        else None
                    ),
                    "heatmap_direct_score": direct_score,
                }
            )
        )
    return annotated
