from collections.abc import Sequence
from typing import Any

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationResult,
    CandidateType,
    make_candidate_id,
)
from app.candidates.select_candidates import (
    CandidateSelection,
    parse_selection_settings,
)
from app.schemas import ClipTimeRange


MANUAL_SELECTION_REASON = "manual_time_range"


def manual_ranges_for_type(
    settings: dict[str, Any],
    candidate_type: CandidateType,
) -> list[ClipTimeRange]:
    key = "shortClipTimeRanges" if candidate_type == "short" else "normalClipTimeRanges"
    snake_key = "short_clip_time_ranges" if candidate_type == "short" else "normal_clip_time_ranges"
    values = settings.get(key, settings.get(snake_key, []))
    if not isinstance(values, list):
        return []
    return [ClipTimeRange.model_validate(value) for value in values]


def automatic_selection_settings(
    settings: dict[str, Any],
    *,
    manual_normal: bool,
    manual_short: bool,
) -> dict[str, Any]:
    automatic = dict(settings)
    normal_count = int(settings.get("normalClipCount", settings.get("normal_clip_count", 2)) or 0)
    short_count = int(settings.get("shortCount", settings.get("short_count", 3)) or 0)
    if manual_normal:
        automatic["normalClipCount"] = 0
    if manual_short:
        automatic["shortCount"] = 0
    has_automatic_output = (
        normal_count > 0 and not manual_normal
    ) or (
        short_count > 0 and not manual_short
    )
    if not has_automatic_output:
        automatic["useOpenAIScoring"] = False
        automatic["ensureSelectedOpenAIScored"] = False
    return automatic


def validate_manual_ranges_for_duration(
    settings: dict[str, Any],
    *,
    video_duration: float,
) -> None:
    for candidate_type in ("normal", "short"):
        for index, clip_range in enumerate(
            manual_ranges_for_type(settings, candidate_type),
            start=1,
        ):
            if clip_range.start_seconds is None or clip_range.end_seconds is None:
                raise ValueError(f"{candidate_type} range {index} is incomplete")
            if clip_range.end_seconds > video_duration + 0.001:
                raise ValueError(
                    f"{candidate_type} range {index} ends at "
                    f"{clip_range.end_seconds:.3f}s, beyond video duration "
                    f"{video_duration:.3f}s"
                )


def _overlapping_transcript(
    transcript_segments: Sequence[TranscriptSegment],
    *,
    start: float,
    end: float,
) -> tuple[str, int | None, int | None, float]:
    matching = [
        (index, segment)
        for index, segment in enumerate(transcript_segments)
        if segment.end > start and segment.start < end
    ]
    text = " ".join(segment.text.strip() for _, segment in matching if segment.text.strip()).strip()
    speech_seconds = sum(
        max(0.0, min(segment.end, end) - max(segment.start, start))
        for _, segment in matching
    )
    return (
        text,
        matching[0][0] if matching else None,
        matching[-1][0] if matching else None,
        round(speech_seconds, 6),
    )


def build_manual_candidates(
    candidate_type: CandidateType,
    ranges: Sequence[ClipTimeRange],
    transcript_segments: Sequence[TranscriptSegment],
) -> CandidateGenerationResult:
    candidates: list[Candidate] = []
    for clip_range in ranges:
        if clip_range.start_seconds is None or clip_range.end_seconds is None:
            raise ValueError("manual clip range is incomplete")
        start = round(float(clip_range.start_seconds), 6)
        end = round(float(clip_range.end_seconds), 6)
        transcript_text, start_index, end_index, speech_seconds = _overlapping_transcript(
            transcript_segments,
            start=start,
            end=end,
        )
        candidates.append(
            Candidate(
                id=make_candidate_id(candidate_type, start, end, transcript_text),
                type=candidate_type,
                start=start,
                end=end,
                duration=round(end - start, 6),
                transcript_text=transcript_text,
                segment_start_index=start_index,
                segment_end_index=end_index,
                transcript_char_count=len(transcript_text),
                speech_seconds=speech_seconds,
                rule_score=100.0,
                final_score=100.0,
                should_use=True,
                reason="User-specified exact time range.",
                hard_gate_passed=True,
                below_quality_threshold=False,
                selection_reason=MANUAL_SELECTION_REASON,
                used_ai_score=False,
                openai_scored=False,
                openai_fallback_used=False,
                openai_score_source="not_scored",
                openai_not_scored_reason=MANUAL_SELECTION_REASON,
                original_start=start,
                original_end=end,
                refined_start=start,
                refined_end=end,
                boundary_refined=False,
                boundary_refinement_reason="manual_time_range_locked",
                boundary_expansion_seconds=0.0,
            )
        )

    durations = [candidate.duration for candidate in candidates]
    summary = {
        "type": candidate_type,
        "strategy": "manual_time_ranges",
        "chunks_processed": 0,
        "raw_candidates_considered": len(candidates),
        "candidates_kept_by_type": {candidate_type: len(candidates)},
        "candidates_dropped_due_to_cap": 0,
        "candidates_dropped_due_to_duplicate": 0,
        "candidates_dropped_due_to_no_transcript": 0,
        "candidates_dropped_due_to_invalid_duration": 0,
        "peak_memory_mb": None,
        "memory_guard_triggered": False,
        "configured_duration_range": {
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "source": "manual_time_ranges",
        },
        "manual_ranges": [
            {
                "start_seconds": candidate.start,
                "end_seconds": candidate.end,
                "duration": candidate.duration,
            }
            for candidate in candidates
        ],
    }
    return CandidateGenerationResult(candidates=candidates, summary=summary)


def merge_manual_candidates_into_selection(
    automatic_selection: CandidateSelection,
    *,
    settings: dict[str, Any],
    manual_normal_candidates: Sequence[Candidate],
    manual_short_candidates: Sequence[Candidate],
) -> CandidateSelection:
    parsed = parse_selection_settings(settings)
    normal_clips = (
        list(manual_normal_candidates)
        if manual_normal_candidates
        else automatic_selection.normal_clips
    )
    shorts = (
        list(manual_short_candidates)
        if manual_short_candidates
        else automatic_selection.shorts
    )
    selected = [*normal_clips, *shorts]
    unfilled = dict(automatic_selection.unfilled_requested_counts)
    unfilled_reasons = dict(automatic_selection.unfilled_reason_counts)
    if manual_normal_candidates:
        unfilled["normal"] = 0
        unfilled_reasons.pop("normal", None)
    if manual_short_candidates:
        unfilled["short"] = 0
        unfilled_reasons.pop("short", None)

    normal_hard_gate_passed = (
        len(manual_normal_candidates)
        if manual_normal_candidates
        else automatic_selection.normal_hard_gate_passed_count
    )
    short_hard_gate_passed = (
        len(manual_short_candidates)
        if manual_short_candidates
        else automatic_selection.short_hard_gate_passed_count
    )
    time_cluster_count = dict(automatic_selection.time_cluster_count)
    selected_clusters = dict(automatic_selection.selected_clusters)
    if manual_normal_candidates:
        time_cluster_count["normal"] = len(manual_normal_candidates)
        selected_clusters["normal"] = list(range(len(manual_normal_candidates)))
    if manual_short_candidates:
        time_cluster_count["short"] = len(manual_short_candidates)
        selected_clusters["short"] = list(range(len(manual_short_candidates)))

    return automatic_selection.model_copy(
        update={
            "normal_clips": normal_clips,
            "shorts": shorts,
            "requested_normal_count": parsed.normal_clip_count,
            "requested_short_count": parsed.short_count,
            "hard_gate_passed_count": (
                automatic_selection.hard_gate_passed_count
                + len(manual_normal_candidates)
                + len(manual_short_candidates)
            ),
            "normal_hard_gate_passed_count": normal_hard_gate_passed,
            "short_hard_gate_passed_count": short_hard_gate_passed,
            "selected_above_threshold_count": sum(
                1 for candidate in selected if candidate.below_quality_threshold is False
            ),
            "selected_below_threshold_backfill_count": sum(
                1 for candidate in selected if candidate.below_quality_threshold is True
            ),
            "time_cluster_count": time_cluster_count,
            "selected_clusters": selected_clusters,
            "unfilled_requested_counts": unfilled,
            "unfilled_reason_counts": unfilled_reasons,
        }
    )
