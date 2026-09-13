from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationResult,
    CandidateGenerationSettings,
    CandidateType,
    adjust_end_to_speech_boundary,
    adjust_start_to_speech_boundary,
    build_candidate,
    parse_generation_settings,
)
from app.scoring.heatmap import candidate_heatmap_features
from app.video.heatmap import HeatmapSegment


@dataclass(frozen=True)
class _Seed:
    start: float
    end: float
    value: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class _RankedCandidate:
    candidate: Candidate
    seed: _Seed
    direct_score: float
    coverage_ratio: float

    @property
    def key(self) -> tuple[str, float, float]:
        return (self.candidate.type, self.candidate.start, self.candidate.end)

    @property
    def rank(self) -> tuple[float, float, float, float, float]:
        return (
            self.direct_score,
            self.seed.value,
            self.coverage_ratio,
            -self.candidate.duration,
            -self.candidate.start,
        )


def _round_time(value: float) -> float:
    return round(float(value), 3)


def _normalized_seeds(
    segments: Sequence[HeatmapSegment],
    video_duration: float,
) -> tuple[list[_Seed], int]:
    normalized: list[_Seed] = []
    outside_video = 0
    for segment in segments:
        start = max(0.0, min(float(segment.start_time), video_duration))
        end = max(0.0, min(float(segment.end_time), video_duration))
        if end <= start:
            outside_video += 1
            continue
        clean_start = _round_time(start)
        clean_end = _round_time(end)
        if clean_end <= clean_start:
            outside_video += 1
            continue
        normalized.append(
            _Seed(
                start=clean_start,
                end=clean_end,
                value=float(segment.value),
            )
        )
    return normalized, outside_video


def _select_diverse_seeds(
    seeds: Sequence[_Seed],
    *,
    limit: int,
    bucket_seconds: float,
) -> list[_Seed]:
    """Keep high-value seeds without letting one dense peak consume the pool."""
    groups: dict[int, list[_Seed]] = defaultdict(list)
    for seed in seeds:
        center = (seed.start + seed.end) / 2
        groups[int(center // bucket_seconds)].append(seed)
    for group in groups.values():
        group.sort(key=lambda seed: (-seed.value, seed.start, seed.end))
    bucket_order = sorted(
        groups,
        key=lambda bucket: (
            -groups[bucket][0].value,
            groups[bucket][0].start,
            bucket,
        ),
    )
    selected: list[_Seed] = []
    while len(selected) < limit and any(groups[bucket] for bucket in bucket_order):
        for bucket in bucket_order:
            if groups[bucket]:
                selected.append(groups[bucket].pop(0))
                if len(selected) >= limit:
                    break
    return selected


def _duration_targets(
    minimum: float,
    maximum: float,
    step: float,
    *,
    max_variants: int,
) -> list[float]:
    if maximum <= minimum:
        return [_round_time(minimum)]
    targets = [float(minimum)]
    current = float(minimum) + float(step)
    while current < maximum and len(targets) < max_variants - 1:
        targets.append(current)
        current += step
    targets.append(float(maximum))
    return sorted({_round_time(value) for value in targets})


def _shift_window_inside_video(
    start: float,
    end: float,
    video_duration: float,
) -> tuple[float, float, bool]:
    shifted = False
    if start < 0:
        end -= start
        start = 0.0
        shifted = True
    if end > video_duration:
        start -= end - video_duration
        end = video_duration
        shifted = True
    return _round_time(max(0.0, start)), _round_time(min(video_duration, end)), shifted


def _raw_windows(seed: _Seed, target_duration: float, video_duration: float) -> list[tuple[float, float, bool]]:
    if seed.duration <= target_duration:
        center = (seed.start + seed.end) / 2
        start = center - (target_duration / 2)
        end = start + target_duration
        return [(*_shift_window_inside_video(start, end, video_duration),)]

    windows: list[tuple[float, float, bool]] = []
    cursor = seed.start
    while cursor + target_duration <= seed.end + 0.001:
        windows.append((*_shift_window_inside_video(cursor, cursor + target_duration, video_duration),))
        cursor += target_duration
    tail_start = seed.end - target_duration
    tail = (*_shift_window_inside_video(tail_start, seed.end, video_duration),)
    if not windows or (tail[0], tail[1]) != (windows[-1][0], windows[-1][1]):
        windows.append(tail)
    return windows


def _speech_aligned_window(
    start: float,
    end: float,
    *,
    transcript_segments: Sequence[TranscriptSegment],
    tolerance: float,
    minimum: float,
    maximum: float,
    video_duration: float,
) -> tuple[float, float, bool]:
    adjusted_start = adjust_start_to_speech_boundary(start, transcript_segments, tolerance)
    adjusted_end = adjust_end_to_speech_boundary(end, transcript_segments, tolerance)
    adjusted_start = max(0.0, adjusted_start)
    adjusted_end = min(video_duration, adjusted_end)
    adjusted_duration = adjusted_end - adjusted_start
    if minimum <= adjusted_duration <= maximum:
        return _round_time(adjusted_start), _round_time(adjusted_end), (
            abs(adjusted_start - start) >= 0.001 or abs(adjusted_end - end) >= 0.001
        )
    return _round_time(start), _round_time(end), False


def _limit_by_bucket(
    candidates: Sequence[_RankedCandidate],
    *,
    bucket_seconds: float,
    limit: int,
    use_center: bool,
) -> tuple[list[_RankedCandidate], int]:
    groups: dict[int, list[_RankedCandidate]] = defaultdict(list)
    for item in candidates:
        position = (
            (item.candidate.start + item.candidate.end) / 2
            if use_center
            else item.candidate.start
        )
        groups[int(position // bucket_seconds)].append(item)
    kept: list[_RankedCandidate] = []
    dropped = 0
    for group in groups.values():
        ordered = sorted(group, key=lambda item: item.rank, reverse=True)
        kept.extend(ordered[:limit])
        dropped += max(0, len(ordered) - limit)
    return kept, dropped


def _round_robin_timeline_limit(
    candidates: Sequence[_RankedCandidate],
    *,
    bucket_seconds: float,
    limit: int,
) -> tuple[list[_RankedCandidate], int]:
    if len(candidates) <= limit:
        return list(candidates), 0
    groups: dict[int, list[_RankedCandidate]] = defaultdict(list)
    for item in candidates:
        center = (item.candidate.start + item.candidate.end) / 2
        groups[int(center // bucket_seconds)].append(item)
    for group in groups.values():
        group.sort(key=lambda item: item.rank, reverse=True)
    bucket_order = sorted(groups, key=lambda key: groups[key][0].rank, reverse=True)
    kept: list[_RankedCandidate] = []
    while len(kept) < limit and any(groups[key] for key in bucket_order):
        for key in bucket_order:
            if groups[key]:
                kept.append(groups[key].pop(0))
                if len(kept) >= limit:
                    break
    return kept, len(candidates) - len(kept)


def _empty_summary(
    candidate_type: CandidateType,
    *,
    video_duration: float,
    transcript_segment_count: int,
    heatmap_segment_count: int,
    normalized_seed_count: int,
    positive_seed_count: int,
    outside_video_count: int,
    settings: CandidateGenerationSettings,
    minimum: float,
    maximum: float,
    step: float,
    tolerance: float,
) -> dict[str, Any]:
    return {
        "strategy": "heatmap_intervals",
        "type": candidate_type,
        "video_duration": round(video_duration, 6),
        "transcript_segment_count": transcript_segment_count,
        "heatmap_segment_count": heatmap_segment_count,
        "normalized_seed_count": normalized_seed_count,
        "positive_seed_count": positive_seed_count,
        "seeds_used": 0,
        "duration_variant_count": 0,
        "chunks_processed": 0,
        "raw_candidates_considered": 0,
        "candidates_kept_by_type": {candidate_type: 0},
        "candidates_dropped_due_to_outside_video": outside_video_count,
        "candidates_dropped_due_to_invalid_duration": 0,
        "candidates_dropped_due_to_no_transcript": 0,
        "candidates_dropped_due_to_duplicate": 0,
        "candidates_dropped_due_to_cap": 0,
        "edge_shifted_count": 0,
        "speech_boundary_adjusted_count": 0,
        "long_seed_tiled_count": 0,
        "peak_memory_mb": None,
        "memory_guard_triggered": False,
        "configured_caps": settings.model_dump(),
        "configured_duration_range": {
            "min_duration": float(minimum),
            "max_duration": float(maximum),
            "step_seconds": float(step),
            "speech_boundary_tolerance": float(tolerance),
        },
        "heatmap_value_range": None,
        "mode_fallback_used": False,
    }


def generate_heatmap_candidates_with_summary(
    candidate_type: CandidateType,
    *,
    heatmap_segments: Sequence[HeatmapSegment],
    transcript_segments: Sequence[TranscriptSegment],
    video_duration: float,
    requested_count: int,
    settings: CandidateGenerationSettings | dict[str, Any] | None = None,
    heartbeat: Callable[[dict[str, Any]], None] | None = None,
) -> CandidateGenerationResult:
    parsed = parse_generation_settings(settings)
    if candidate_type == "normal":
        minimum = parsed.normal_min_duration
        maximum = parsed.normal_max_duration
        step = parsed.normal_step_seconds
    else:
        minimum = parsed.short_min_duration
        maximum = parsed.short_max_duration
        step = parsed.short_step_seconds
    tolerance = parsed.speech_boundary_tolerance
    normalized, outside_video_count = _normalized_seeds(heatmap_segments, video_duration)
    positive = [seed for seed in normalized if seed.value > 0]
    base_summary = _empty_summary(
        candidate_type,
        video_duration=video_duration,
        transcript_segment_count=len(transcript_segments),
        heatmap_segment_count=len(heatmap_segments),
        normalized_seed_count=len(normalized),
        positive_seed_count=len(positive),
        outside_video_count=outside_video_count,
        settings=parsed,
        minimum=minimum,
        maximum=maximum,
        step=step,
        tolerance=tolerance,
    )
    if requested_count <= 0 or video_duration < minimum or not positive:
        return CandidateGenerationResult(candidates=[], summary=base_summary)

    seed_limit = min(len(positive), max(12, requested_count * 8))
    seed_bucket_seconds = max(float(minimum), 1.0)
    seeds = _select_diverse_seeds(
        positive,
        limit=seed_limit,
        bucket_seconds=seed_bucket_seconds,
    )
    variants_per_seed = max(
        2,
        min(24, parsed.max_raw_candidates_per_type // max(len(seeds), 1)),
    )
    targets = _duration_targets(
        minimum,
        maximum,
        step,
        max_variants=variants_per_seed,
    )
    for seed in seeds:
        if minimum <= seed.duration <= maximum:
            targets.append(_round_time(seed.duration))
    targets = sorted(set(targets))

    raw_considered = 0
    invalid_duration = 0
    no_transcript = 0
    edge_shifted = 0
    speech_adjusted = 0
    long_seed_tiled = 0
    ranked_by_key: dict[tuple[str, float, float], _RankedCandidate] = {}
    duplicate_count = 0
    raw_cap_reached = False

    normalized_segments = [
        HeatmapSegment(start_time=float(seed.start), end_time=float(seed.end), value=float(seed.value))
        for seed in normalized
    ]
    for seed in seeds:
        for target in targets:
            windows = _raw_windows(seed, target, video_duration)
            if seed.duration > target and len(windows) > 1:
                long_seed_tiled += 1
            for raw_start, raw_end, shifted in windows:
                if raw_considered >= parsed.max_raw_candidates_per_type:
                    raw_cap_reached = True
                    break
                raw_considered += 1
                edge_shifted += int(shifted)
                start, end, adjusted = _speech_aligned_window(
                    raw_start,
                    raw_end,
                    transcript_segments=transcript_segments,
                    tolerance=tolerance,
                    minimum=minimum,
                    maximum=maximum,
                    video_duration=video_duration,
                )
                speech_adjusted += int(adjusted)
                duration = end - start
                if duration < minimum - 0.001 or duration > maximum + 0.001:
                    invalid_duration += 1
                    continue
                candidate = build_candidate(candidate_type, start, end, transcript_segments)
                if candidate is None:
                    no_transcript += 1
                    continue
                value, overlap_seconds = candidate_heatmap_features(candidate, normalized_segments)
                direct_score = round(
                    min(1.0, value * overlap_seconds / candidate.duration),
                    6,
                )
                coverage_ratio = round(min(1.0, overlap_seconds / candidate.duration), 6)
                candidate = candidate.model_copy(
                    update={
                        "generation_source": "heatmap_interval",
                        "heatmap_seed_start": seed.start,
                        "heatmap_seed_end": seed.end,
                        "heatmap_seed_value": seed.value,
                        "heatmap_value": value,
                        "heatmap_overlap_seconds": overlap_seconds,
                        "heatmap_direct_score": direct_score,
                    }
                )
                ranked = _RankedCandidate(
                    candidate=candidate,
                    seed=seed,
                    direct_score=direct_score,
                    coverage_ratio=coverage_ratio,
                )
                previous = ranked_by_key.get(ranked.key)
                if previous is not None:
                    duplicate_count += 1
                if previous is None or ranked.rank > previous.rank:
                    ranked_by_key[ranked.key] = ranked
            if raw_cap_reached:
                break
        if raw_cap_reached:
            break

    ranked_candidates = list(ranked_by_key.values())
    ranked_candidates, dropped_start_bucket = _limit_by_bucket(
        ranked_candidates,
        bucket_seconds=parsed.candidate_start_bucket_seconds,
        limit=parsed.max_candidates_per_start_bucket,
        use_center=False,
    )
    ranked_candidates, dropped_time_bucket = _limit_by_bucket(
        ranked_candidates,
        bucket_seconds=parsed.candidate_time_bucket_seconds,
        limit=parsed.max_candidates_per_time_bucket,
        use_center=True,
    )
    effective_limit = min(parsed.max_candidates, parsed.max_kept_candidates_per_type)
    ranked_candidates, dropped_global = _round_robin_timeline_limit(
        ranked_candidates,
        bucket_seconds=parsed.candidate_time_bucket_seconds,
        limit=effective_limit,
    )
    candidates = sorted(
        (item.candidate for item in ranked_candidates),
        key=lambda item: (item.start, item.duration, item.id),
    )
    summary = {
        **base_summary,
        "seeds_used": len(seeds),
        "seed_time_bucket_seconds": seed_bucket_seconds,
        "seed_time_bucket_count": len(
            {
                int(((seed.start + seed.end) / 2) // seed_bucket_seconds)
                for seed in positive
            }
        ),
        "duration_variant_count": len(targets),
        "chunks_processed": 1,
        "raw_candidates_considered": raw_considered,
        "candidates_kept_by_type": {candidate_type: len(candidates)},
        "candidates_dropped_due_to_invalid_duration": invalid_duration,
        "candidates_dropped_due_to_no_transcript": no_transcript,
        "candidates_dropped_due_to_duplicate": duplicate_count,
        "candidates_dropped_due_to_cap": (
            dropped_start_bucket + dropped_time_bucket + dropped_global
        ),
        "edge_shifted_count": edge_shifted,
        "speech_boundary_adjusted_count": speech_adjusted,
        "long_seed_tiled_count": long_seed_tiled,
        "heatmap_value_range": {
            "min": min(seed.value for seed in seeds),
            "max": max(seed.value for seed in seeds),
        },
        "stopped_due_to_raw_candidate_cap": raw_cap_reached,
    }
    if heartbeat is not None:
        heartbeat(summary)
    return CandidateGenerationResult(candidates=candidates, summary=summary)
