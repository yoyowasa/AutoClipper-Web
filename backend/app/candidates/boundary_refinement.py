from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, parse_generation_settings
from app.video.scene_detect import SceneSegment


WEAK_CONTINUATION_PREFIXES = (
    "なので",
    "で",
    "それで",
    "だから",
    "ということで",
    "まあ",
    "あの",
    "えっと",
    "それは",
    "これは",
    "そうですね",
)
INCOMPLETE_END_SUFFIXES = (
    "ので",
    "から",
    "けど",
    "ですが",
    "けれども",
    "っていう",
    "という",
    "とか",
    "and",
    "but",
    "because",
)


class BoundaryRefinementSettings(BaseModel):
    enable_boundary_refinement: bool = True
    boundary_leading_padding_seconds: float = Field(default=0.4, ge=0)
    boundary_trailing_padding_seconds: float = Field(default=0.6, ge=0)
    max_boundary_expansion_seconds: float = Field(default=3.0, ge=0)
    allow_boundary_expansion_beyond_max_duration: bool = False


@dataclass(frozen=True)
class BoundaryConstraints:
    min_duration: float
    max_duration: float
    timeline_duration: float


def parse_boundary_refinement_settings(
    settings: BoundaryRefinementSettings | dict[str, Any] | None,
) -> BoundaryRefinementSettings:
    if settings is None:
        return BoundaryRefinementSettings()
    if isinstance(settings, BoundaryRefinementSettings):
        return settings
    aliases = {
        "enableBoundaryRefinement": "enable_boundary_refinement",
        "boundaryLeadingPaddingSeconds": "boundary_leading_padding_seconds",
        "boundaryTrailingPaddingSeconds": "boundary_trailing_padding_seconds",
        "maxBoundaryExpansionSeconds": "max_boundary_expansion_seconds",
        "allowBoundaryExpansionBeyondMaxDuration": "allow_boundary_expansion_beyond_max_duration",
    }
    return BoundaryRefinementSettings(**{aliases.get(key, key): value for key, value in settings.items()})


def _round_time(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _timeline_duration(
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    explicit_duration: float | None,
    fallback_end: float,
) -> float:
    values = [
        fallback_end,
        *(float(segment.end) for segment in transcript_segments),
        *(float(segment.end) for segment in silence_segments),
        *(float(segment.end) for segment in scene_segments),
    ]
    if explicit_duration is not None:
        values.append(float(explicit_duration))
    return max(values, default=fallback_end)


def _constraints_for_candidate(
    candidate: Candidate,
    settings: dict[str, Any] | BoundaryRefinementSettings | None,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    timeline_duration: float | None,
) -> BoundaryConstraints:
    generation_settings = parse_generation_settings(settings if isinstance(settings, dict) else None)
    if candidate.type == "short":
        min_duration = generation_settings.short_min_duration
        max_duration = generation_settings.short_max_duration
    else:
        min_duration = generation_settings.normal_min_duration
        max_duration = generation_settings.normal_max_duration
    return BoundaryConstraints(
        min_duration=float(min_duration),
        max_duration=float(max_duration),
        timeline_duration=_timeline_duration(
            transcript_segments,
            silence_segments,
            scene_segments,
            timeline_duration,
            fallback_end=candidate.end,
        ),
    )


def _segment_containing(
    time_seconds: float,
    transcript_segments: Sequence[TranscriptSegment],
) -> tuple[int, TranscriptSegment] | None:
    for index, segment in enumerate(transcript_segments):
        if float(segment.start) < time_seconds < float(segment.end):
            return index, segment
    return None


def _overlapping_segments(
    start: float,
    end: float,
    transcript_segments: Sequence[TranscriptSegment],
) -> list[tuple[int, TranscriptSegment]]:
    return [
        (index, segment)
        for index, segment in enumerate(transcript_segments)
        if segment.text.strip() and float(segment.end) > start and float(segment.start) < end
    ]


def _scene_containing(time_seconds: float, scene_segments: Sequence[SceneSegment]) -> SceneSegment | None:
    for scene in scene_segments:
        if float(scene.start) <= time_seconds <= float(scene.end):
            return scene
    return None


def _silence_touching_before(time_seconds: float, silence_segments: Sequence[SilenceSegment]) -> SilenceSegment | None:
    candidates = [
        segment
        for segment in silence_segments
        if float(segment.start) <= time_seconds and time_seconds - 0.2 <= float(segment.end) <= time_seconds + 0.2
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda segment: float(segment.end))


def _silence_touching_after(time_seconds: float, silence_segments: Sequence[SilenceSegment]) -> SilenceSegment | None:
    candidates = [
        segment
        for segment in silence_segments
        if float(segment.end) >= time_seconds and time_seconds - 0.2 <= float(segment.start) <= time_seconds + 0.2
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda segment: float(segment.start))


def _starts_with_weak_marker(text: str) -> bool:
    clean = text.strip().lstrip("、。，．.!！?？ ")
    return any(clean.startswith(prefix) for prefix in WEAK_CONTINUATION_PREFIXES)


def _ends_incomplete(text: str) -> bool:
    clean = text.strip().rstrip("、。，．.!！?？ ")
    lowered = clean.lower()
    return any(lowered.endswith(suffix) for suffix in INCOMPLETE_END_SUFFIXES)


def _transcript_text_for_range(
    transcript_segments: Sequence[TranscriptSegment],
    start: float,
    end: float,
) -> str:
    return " ".join(
        segment.text.strip()
        for segment in transcript_segments
        if segment.text.strip() and float(segment.end) > start and float(segment.start) < end
    ).strip()


def _speech_seconds_for_range(
    transcript_segments: Sequence[TranscriptSegment],
    start: float,
    end: float,
) -> float:
    total = 0.0
    for segment in transcript_segments:
        if not segment.text.strip():
            continue
        overlap_start = max(start, float(segment.start))
        overlap_end = min(end, float(segment.end))
        if overlap_end > overlap_start:
            total += overlap_end - overlap_start
    return total


def _silence_seconds_for_range(
    silence_segments: Sequence[SilenceSegment],
    start: float,
    end: float,
) -> float:
    total = 0.0
    for segment in silence_segments:
        overlap_start = max(start, float(segment.start))
        overlap_end = min(end, float(segment.end))
        if overlap_end > overlap_start:
            total += overlap_end - overlap_start
    return total


def _apply_duration_constraints(
    *,
    original_start: float,
    original_end: float,
    desired_start: float,
    desired_end: float,
    constraints: BoundaryConstraints,
    settings: BoundaryRefinementSettings,
) -> tuple[float, float]:
    start = max(0.0, desired_start)
    end = min(constraints.timeline_duration, desired_end)
    if end <= start:
        return original_start, original_end

    original_duration = original_end - original_start
    if not settings.allow_boundary_expansion_beyond_max_duration:
        max_duration = max(constraints.max_duration, constraints.min_duration)
        if end - start > max_duration:
            budget = max(0.0, max_duration - original_duration)
            start_expansion = max(0.0, original_start - start)
            end_expansion = max(0.0, end - original_end)
            total_expansion = start_expansion + end_expansion
            if total_expansion > 0:
                start_ratio = start_expansion / total_expansion
                allowed_start = min(start_expansion, budget * start_ratio)
                allowed_end = min(end_expansion, max(0.0, budget - allowed_start))
                start = original_start - allowed_start
                end = original_end + allowed_end

    if end - start < constraints.min_duration:
        deficit = constraints.min_duration - (end - start)
        end = min(constraints.timeline_duration, end + deficit)
        if end - start < constraints.min_duration:
            start = max(0.0, start - (constraints.min_duration - (end - start)))

    if end <= start:
        return original_start, original_end
    return _round_time(start), _round_time(end)


def _metadata_update(
    candidate: Candidate,
    *,
    start: float,
    end: float,
    reasons: Sequence[str],
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
) -> dict[str, Any]:
    duration = _round_time(end - start)
    transcript_text = _transcript_text_for_range(transcript_segments, start, end) or candidate.transcript_text
    speech_seconds = _speech_seconds_for_range(transcript_segments, start, end)
    silence_seconds = _silence_seconds_for_range(silence_segments, start, end)
    expansion = max(0.0, candidate.start - start) + max(0.0, end - candidate.end)
    return {
        "start": start,
        "end": end,
        "duration": duration,
        "transcript_text": transcript_text,
        "transcript_char_count": len(transcript_text),
        "speech_seconds": round(speech_seconds, 6) if speech_seconds > 0 else candidate.speech_seconds,
        "silence_ratio": round(min(1.0, silence_seconds / max(duration, 1.0)), 6),
        "original_start": _round_time(candidate.original_start if candidate.original_start is not None else candidate.start),
        "original_end": _round_time(candidate.original_end if candidate.original_end is not None else candidate.end),
        "refined_start": start,
        "refined_end": end,
        "boundary_refined": bool(reasons and (start != candidate.start or end != candidate.end)),
        "boundary_refinement_reason": ", ".join(reasons) if reasons else "unchanged",
        "boundary_expansion_seconds": round(expansion, 6),
    }


def refine_candidate_boundaries(
    candidate: Candidate,
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment] = (),
    scene_segments: Sequence[SceneSegment] = (),
    settings: BoundaryRefinementSettings | dict[str, Any] | None = None,
    timeline_duration: float | None = None,
) -> Candidate:
    boundary_settings = parse_boundary_refinement_settings(settings)
    constraints = _constraints_for_candidate(
        candidate,
        settings if isinstance(settings, dict) else None,
        transcript_segments,
        silence_segments,
        scene_segments,
        timeline_duration,
    )
    original_start = float(candidate.start)
    original_end = float(candidate.end)

    if not boundary_settings.enable_boundary_refinement:
        return candidate.model_copy(
            update={
                "original_start": _round_time(
                    candidate.original_start if candidate.original_start is not None else original_start
                ),
                "original_end": _round_time(
                    candidate.original_end if candidate.original_end is not None else original_end
                ),
                "refined_start": _round_time(original_start),
                "refined_end": _round_time(original_end),
                "boundary_refined": False,
                "boundary_refinement_reason": "disabled",
                "boundary_expansion_seconds": 0.0,
            }
        )

    desired_start = original_start
    desired_end = original_end
    reasons: list[str] = []
    max_expansion = float(boundary_settings.max_boundary_expansion_seconds)
    min_start = max(0.0, original_start - max_expansion)
    max_end = min(constraints.timeline_duration, original_end + max_expansion)
    overlaps = _overlapping_segments(original_start, original_end, transcript_segments)

    containing_start = _segment_containing(original_start, transcript_segments)
    if containing_start is not None:
        _, segment = containing_start
        desired_start = min(desired_start, float(segment.start))
        reasons.append("start_to_transcript_segment_start")

    if overlaps:
        first_index, first_segment = overlaps[0]
        if _starts_with_weak_marker(first_segment.text) and first_index > 0:
            previous = transcript_segments[first_index - 1]
            if original_start - float(previous.start) <= max_expansion:
                desired_start = min(desired_start, float(previous.start))
                reasons.append("weak_continuation_expanded_start")

    scene = _scene_containing(original_start, scene_segments)
    if scene is not None and float(scene.start) < desired_start and original_start - float(scene.start) <= max_expansion:
        desired_start = float(scene.start)
        reasons.append("start_to_scene_boundary")

    if desired_start < original_start and boundary_settings.boundary_leading_padding_seconds > 0:
        silence = _silence_touching_before(desired_start, silence_segments)
        desired_start -= boundary_settings.boundary_leading_padding_seconds
        if silence is not None and float(silence.start) <= desired_start <= float(silence.end):
            reasons.append("leading_padding_in_silence")
        else:
            reasons.append("leading_padding")

    containing_end = _segment_containing(original_end, transcript_segments)
    if containing_end is not None:
        _, segment = containing_end
        desired_end = max(desired_end, float(segment.end))
        reasons.append("end_to_transcript_segment_end")

    if overlaps:
        last_index, last_segment = overlaps[-1]
        if _ends_incomplete(last_segment.text) and last_index + 1 < len(transcript_segments):
            following = transcript_segments[last_index + 1]
            if float(following.end) - original_end <= max_expansion:
                desired_end = max(desired_end, float(following.end))
                reasons.append("incomplete_ending_expanded_end")

    scene = _scene_containing(original_end, scene_segments)
    if scene is not None and float(scene.end) > desired_end and float(scene.end) - original_end <= max_expansion:
        desired_end = float(scene.end)
        reasons.append("end_to_scene_boundary")

    if desired_end > original_end and boundary_settings.boundary_trailing_padding_seconds > 0:
        silence = _silence_touching_after(desired_end, silence_segments)
        desired_end += boundary_settings.boundary_trailing_padding_seconds
        if silence is not None and float(silence.start) <= desired_end <= float(silence.end):
            reasons.append("trailing_padding_in_silence")
        else:
            reasons.append("trailing_padding")

    desired_start = max(min_start, desired_start)
    desired_end = min(max_end, desired_end)
    refined_start, refined_end = _apply_duration_constraints(
        original_start=original_start,
        original_end=original_end,
        desired_start=desired_start,
        desired_end=desired_end,
        constraints=constraints,
        settings=boundary_settings,
    )
    if refined_start == original_start and refined_end == original_end:
        reasons = []

    return candidate.model_copy(
        update=_metadata_update(
            candidate,
            start=refined_start,
            end=refined_end,
            reasons=reasons,
            transcript_segments=transcript_segments,
            silence_segments=silence_segments,
        )
    )


def refine_selected_candidates(
    candidates: Sequence[Candidate],
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment] = (),
    scene_segments: Sequence[SceneSegment] = (),
    settings: BoundaryRefinementSettings | dict[str, Any] | None = None,
    timeline_duration: float | None = None,
) -> list[Candidate]:
    return [
        refine_candidate_boundaries(
            candidate,
            transcript_segments=transcript_segments,
            silence_segments=silence_segments,
            scene_segments=scene_segments,
            settings=settings,
            timeline_duration=timeline_duration,
        )
        for candidate in candidates
    ]
