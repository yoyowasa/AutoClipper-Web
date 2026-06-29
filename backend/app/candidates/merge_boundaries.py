import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field, model_validator

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.video.scene_detect import SceneSegment


CandidateType = Literal["short", "normal"]
OpenAIScoreSource = Literal[
    "preselection_pool",
    "finalist_on_demand",
    "fallback_rule_score",
    "not_scored",
]


class Candidate(BaseModel):
    id: str
    type: CandidateType
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    duration: float = Field(ge=0)
    transcript_text: str
    rule_score: float | None = Field(default=None, ge=0, le=100)
    ai_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float | None = Field(default=None, ge=0, le=100)
    should_use: bool | None = None
    title: str | None = None
    overlay_title: str | None = None
    reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    reject_reason: str | None = None
    hard_gate_passed: bool | None = None
    below_quality_threshold: bool | None = None
    quality_warning: str | None = None
    selection_reason: str | None = None
    overlap_relaxed: bool | None = None
    overlap_ratio_used: float | None = Field(default=None, ge=0)
    time_cluster: int | None = None
    used_ai_score: bool | None = None
    openai_scored: bool | None = None
    openai_fallback_used: bool | None = None
    openai_score_source: OpenAIScoreSource | None = None
    openai_not_scored_reason: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "Candidate":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if round(self.end - self.start, 6) != round(self.duration, 6):
            raise ValueError("duration must equal end - start")
        return self


class CandidateGenerationSettings(BaseModel):
    short_min_duration: float = Field(default=20.0, gt=0)
    short_max_duration: float = Field(default=75.0, gt=0)
    normal_min_duration: float = Field(default=90.0, gt=0)
    normal_max_duration: float = Field(default=600.0, gt=0)
    short_step_seconds: float = Field(default=10.0, gt=0)
    normal_step_seconds: float = Field(default=30.0, gt=0)
    speech_boundary_tolerance: float = Field(default=8.0, ge=0)
    max_candidates: int = Field(default=1200, gt=0)

    @model_validator(mode="after")
    def validate_duration_ranges(self) -> "CandidateGenerationSettings":
        if self.short_max_duration < self.short_min_duration:
            raise ValueError("short_max_duration must be >= short_min_duration")
        if self.normal_max_duration < self.normal_min_duration:
            raise ValueError("normal_max_duration must be >= normal_min_duration")
        return self


def parse_generation_settings(settings: CandidateGenerationSettings | dict[str, Any] | None) -> CandidateGenerationSettings:
    if settings is None:
        return CandidateGenerationSettings()
    if isinstance(settings, CandidateGenerationSettings):
        return settings
    normalized: dict[str, Any] = {}
    aliases = {
        "shortMinDuration": "short_min_duration",
        "shortMaxDuration": "short_max_duration",
        "normalMinDuration": "normal_min_duration",
        "normalMaxDuration": "normal_max_duration",
        "shortStepSeconds": "short_step_seconds",
        "normalStepSeconds": "normal_step_seconds",
        "speechBoundaryTolerance": "speech_boundary_tolerance",
        "maxCandidates": "max_candidates",
    }
    for key, value in settings.items():
        normalized[aliases.get(key, key)] = value
    return CandidateGenerationSettings(**normalized)


def infer_timeline_duration(
    transcript_segments: Sequence[TranscriptSegment],
    scene_segments: Sequence[SceneSegment],
    silence_segments: Sequence[SilenceSegment],
) -> float:
    ends = [
        *(segment.end for segment in transcript_segments),
        *(segment.end for segment in scene_segments),
        *(segment.end for segment in silence_segments),
    ]
    return max(ends, default=0.0)


def _round_time(value: float) -> float:
    return round(float(value), 3)


def merge_boundaries(
    transcript_segments: Sequence[TranscriptSegment],
    scene_segments: Sequence[SceneSegment],
    silence_segments: Sequence[SilenceSegment],
    duration: float | None = None,
) -> list[float]:
    timeline_duration = duration
    if timeline_duration is None:
        timeline_duration = infer_timeline_duration(
            transcript_segments,
            scene_segments,
            silence_segments,
        )
    if timeline_duration <= 0:
        return []

    boundaries = {0.0, _round_time(timeline_duration)}
    for segment in transcript_segments:
        boundaries.add(_round_time(segment.start))
        boundaries.add(_round_time(segment.end))
    for segment in scene_segments:
        boundaries.add(_round_time(segment.start))
        boundaries.add(_round_time(segment.end))
    for segment in silence_segments:
        boundaries.add(_round_time(segment.start))
        boundaries.add(_round_time(segment.end))
        boundaries.add(_round_time((segment.start + segment.end) / 2))

    return sorted(boundary for boundary in boundaries if 0 <= boundary <= timeline_duration)


def speech_segment_at(time_seconds: float, transcript_segments: Sequence[TranscriptSegment]) -> TranscriptSegment | None:
    for segment in transcript_segments:
        if segment.start < time_seconds < segment.end:
            return segment
    return None


def is_inside_speech(time_seconds: float, transcript_segments: Sequence[TranscriptSegment]) -> bool:
    return speech_segment_at(time_seconds, transcript_segments) is not None


def adjust_start_to_speech_boundary(
    time_seconds: float,
    transcript_segments: Sequence[TranscriptSegment],
    tolerance: float,
) -> float:
    segment = speech_segment_at(time_seconds, transcript_segments)
    if segment is None:
        return _round_time(time_seconds)
    if abs(time_seconds - segment.start) <= tolerance:
        return _round_time(segment.start)
    return _round_time(time_seconds)


def adjust_end_to_speech_boundary(
    time_seconds: float,
    transcript_segments: Sequence[TranscriptSegment],
    tolerance: float,
) -> float:
    segment = speech_segment_at(time_seconds, transcript_segments)
    if segment is None:
        return _round_time(time_seconds)
    if abs(segment.end - time_seconds) <= tolerance:
        return _round_time(segment.end)
    return _round_time(time_seconds)


def transcript_text_for_range(
    transcript_segments: Sequence[TranscriptSegment],
    start: float,
    end: float,
) -> str:
    texts = [
        segment.text.strip()
        for segment in transcript_segments
        if segment.text.strip() and segment.end > start and segment.start < end
    ]
    return " ".join(texts).strip()


def make_candidate_id(candidate_type: CandidateType, start: float, end: float, transcript_text: str) -> str:
    digest = hashlib.sha1(f"{candidate_type}:{start:.3f}:{end:.3f}:{transcript_text}".encode("utf-8")).hexdigest()[:10]
    return f"cand_{candidate_type}_{int(start * 1000)}_{int(end * 1000)}_{digest}"


def build_candidate(
    candidate_type: CandidateType,
    start: float,
    end: float,
    transcript_segments: Sequence[TranscriptSegment],
) -> Candidate | None:
    clean_start = _round_time(start)
    clean_end = _round_time(end)
    if clean_end <= clean_start:
        return None

    transcript_text = transcript_text_for_range(transcript_segments, clean_start, clean_end)
    if not transcript_text:
        return None

    duration = _round_time(clean_end - clean_start)
    return Candidate(
        id=make_candidate_id(candidate_type, clean_start, clean_end, transcript_text),
        type=candidate_type,
        start=clean_start,
        end=clean_end,
        duration=duration,
        transcript_text=transcript_text,
    )


def deduplicate_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    by_key: dict[tuple[str, float, float], Candidate] = {}
    for candidate in candidates:
        key = (candidate.type, candidate.start, candidate.end)
        by_key.setdefault(key, candidate)
    return sorted(by_key.values(), key=lambda item: (item.start, item.duration, item.type, item.id))


def limit_candidates_by_timeline(candidates: Sequence[Candidate], max_candidates: int) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: (item.start, item.duration, item.type, item.id))
    if len(ordered) <= max_candidates:
        return ordered

    min_start = min(candidate.start for candidate in ordered)
    max_end = max(candidate.end for candidate in ordered)
    span = max(max_end - min_start, 1.0)
    bucket_count = min(max_candidates, max(1, int(span // 60) + 1))
    buckets: list[list[Candidate]] = [[] for _ in range(bucket_count)]
    for candidate in ordered:
        index = int(((candidate.start - min_start) / span) * bucket_count)
        buckets[min(index, bucket_count - 1)].append(candidate)

    limited: list[Candidate] = []
    while len(limited) < max_candidates and any(buckets):
        for bucket in buckets:
            if not bucket:
                continue
            limited.append(bucket.pop(0))
            if len(limited) >= max_candidates:
                break
    return sorted(limited, key=lambda item: (item.start, item.duration, item.type, item.id))


def _duration_targets(min_duration: float, max_duration: float, step_seconds: float) -> list[float]:
    targets = {float(min_duration), float(max_duration)}
    current = float(min_duration)
    while current <= max_duration:
        targets.add(round(current, 3))
        current += step_seconds
    return sorted(targets)


def _candidate_end_targets(
    start: float,
    boundaries: Sequence[float],
    min_duration: float,
    max_duration: float,
    step_seconds: float,
    timeline_duration: float,
) -> list[float]:
    targets = {
        boundary
        for boundary in boundaries
        if min_duration <= boundary - start <= max_duration
    }
    for duration in _duration_targets(min_duration, max_duration, step_seconds):
        target = start + duration
        if target <= timeline_duration:
            targets.add(_round_time(target))
    return sorted(targets)


def generate_window_candidates(
    candidate_type: CandidateType,
    transcript_segments: Sequence[TranscriptSegment],
    scene_segments: Sequence[SceneSegment],
    silence_segments: Sequence[SilenceSegment],
    min_duration: float,
    max_duration: float,
    step_seconds: float,
    speech_boundary_tolerance: float,
    max_candidates: int,
) -> list[Candidate]:
    timeline_duration = infer_timeline_duration(
        transcript_segments,
        scene_segments,
        silence_segments,
    )
    if timeline_duration <= 0:
        return []

    boundaries = merge_boundaries(
        transcript_segments,
        scene_segments,
        silence_segments,
        duration=timeline_duration,
    )
    if not boundaries:
        return []

    raw_starts = sorted({*boundaries[:-1], *(segment.start for segment in transcript_segments)})
    candidates: list[Candidate] = []
    for raw_start in raw_starts:
        start = adjust_start_to_speech_boundary(
            raw_start,
            transcript_segments,
            tolerance=speech_boundary_tolerance,
        )
        if start >= timeline_duration or is_inside_speech(start, transcript_segments):
            continue

        for raw_end in _candidate_end_targets(
            start,
            boundaries,
            min_duration=min_duration,
            max_duration=max_duration,
            step_seconds=step_seconds,
            timeline_duration=timeline_duration,
        ):
            end = adjust_end_to_speech_boundary(
                raw_end,
                transcript_segments,
                tolerance=speech_boundary_tolerance,
            )
            if end > timeline_duration:
                end = timeline_duration
            duration = end - start
            if duration < min_duration or duration > max_duration:
                continue
            if is_inside_speech(end, transcript_segments):
                continue

            candidate = build_candidate(candidate_type, start, end, transcript_segments)
            if candidate is not None:
                candidates.append(candidate)

    return limit_candidates_by_timeline(deduplicate_candidates(candidates), max_candidates)


def candidates_to_jsonable(candidates: Sequence[Candidate]) -> list[dict[str, Any]]:
    return [candidate.model_dump(exclude_none=True) for candidate in candidates]


def write_candidates(candidates: Sequence[Candidate], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(candidates_to_jsonable(candidates), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
