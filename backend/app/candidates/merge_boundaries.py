import hashlib
import json
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field, model_validator

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.title_generation import TitleSource
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
    segment_start_index: int | None = Field(default=None, ge=0)
    segment_end_index: int | None = Field(default=None, ge=0)
    transcript_char_count: int | None = Field(default=None, ge=0)
    speech_seconds: float | None = Field(default=None, ge=0)
    silence_ratio: float | None = Field(default=None, ge=0, le=1)
    rule_score: float | None = Field(default=None, ge=0, le=100)
    ai_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float | None = Field(default=None, ge=0, le=100)
    should_use: bool | None = None
    title: str | None = None
    overlay_title: str | None = None
    title_source: TitleSource | None = None
    filename_safe_title: str | None = None
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
    max_raw_candidates_per_type: int = Field(default=250_000, gt=0)
    max_kept_candidates_per_type: int = Field(default=1200, gt=0)
    max_candidates_per_time_bucket: int = Field(default=100, gt=0)
    candidate_time_bucket_seconds: float = Field(default=300.0, gt=0)
    max_candidate_generation_memory_mb: int = Field(default=12_000, gt=0)
    candidate_chunk_seconds: float = Field(default=600.0, gt=0)
    candidate_chunk_overlap_seconds: float = Field(default=75.0, ge=0)

    @model_validator(mode="after")
    def validate_duration_ranges(self) -> "CandidateGenerationSettings":
        if self.short_max_duration < self.short_min_duration:
            raise ValueError("short_max_duration must be >= short_min_duration")
        if self.normal_max_duration < self.normal_min_duration:
            raise ValueError("normal_max_duration must be >= normal_min_duration")
        return self


class CandidateGenerationMemoryLimitError(RuntimeError):
    def __init__(self, summary: dict[str, Any]) -> None:
        super().__init__("candidate generation exceeded configured memory limit")
        self.summary = summary


@dataclass(frozen=True)
class CandidateGenerationResult:
    candidates: list[Candidate]
    summary: dict[str, Any]


@dataclass(frozen=True)
class _TranscriptRange:
    start_index: int
    end_index: int
    char_count: int
    speech_seconds: float


@dataclass(frozen=True)
class _LightweightCandidate:
    candidate_type: CandidateType
    start: float
    end: float
    duration: float
    segment_start_index: int
    segment_end_index: int
    transcript_char_count: int
    speech_seconds: float
    silence_ratio: float
    rank_score: float

    @property
    def key(self) -> tuple[CandidateType, float, float]:
        return (self.candidate_type, self.start, self.end)


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
        "maxRawCandidatesPerType": "max_raw_candidates_per_type",
        "maxKeptCandidatesPerType": "max_kept_candidates_per_type",
        "maxCandidatesPerTimeBucket": "max_candidates_per_time_bucket",
        "candidateTimeBucketSeconds": "candidate_time_bucket_seconds",
        "maxCandidateGenerationMemoryMb": "max_candidate_generation_memory_mb",
        "candidateChunkSeconds": "candidate_chunk_seconds",
        "candidateChunkOverlapSeconds": "candidate_chunk_overlap_seconds",
    }
    for key, value in settings.items():
        normalized[aliases.get(key, key)] = value
    return CandidateGenerationSettings(**normalized)


def _current_rss_mb() -> float | None:
    proc_status = Path("/proc/self/status")
    if proc_status.is_file():
        try:
            for line in proc_status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return round(float(parts[1]) / 1024, 3)
        except OSError:
            return None
    return None


class _TranscriptIndex:
    def __init__(self, segments: Sequence[TranscriptSegment]) -> None:
        self.segments = list(segments)
        self.starts = [float(segment.start) for segment in self.segments]
        self.ends = [float(segment.end) for segment in self.segments]
        self.texts = [segment.text.strip() for segment in self.segments]
        self.prefix_chars = [0]
        self.prefix_speech = [0.0]
        for segment, text in zip(self.segments, self.texts, strict=True):
            self.prefix_chars.append(self.prefix_chars[-1] + len(text))
            speech_seconds = max(0.0, float(segment.end) - float(segment.start)) if text else 0.0
            self.prefix_speech.append(self.prefix_speech[-1] + speech_seconds)

    def range_for(self, start: float, end: float) -> _TranscriptRange:
        start_index = bisect_right(self.ends, start)
        end_index = bisect_left(self.starts, end)
        if end_index < start_index:
            end_index = start_index
        return _TranscriptRange(
            start_index=start_index,
            end_index=end_index,
            char_count=self.prefix_chars[end_index] - self.prefix_chars[start_index],
            speech_seconds=self.prefix_speech[end_index] - self.prefix_speech[start_index],
        )

    def text_for_indices(self, start_index: int, end_index: int) -> str:
        return " ".join(text for text in self.texts[start_index:end_index] if text).strip()


class _SilenceIndex:
    def __init__(self, segments: Sequence[SilenceSegment]) -> None:
        self.starts = [float(segment.start) for segment in segments]
        self.ends = [float(segment.end) for segment in segments]

    def overlap_seconds(self, start: float, end: float) -> float:
        if not self.starts:
            return 0.0
        index = max(0, bisect_right(self.ends, start) - 1)
        total = 0.0
        while index < len(self.starts) and self.starts[index] < end:
            overlap_start = max(start, self.starts[index])
            overlap_end = min(end, self.ends[index])
            if overlap_end > overlap_start:
                total += overlap_end - overlap_start
            index += 1
        return total


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


def _candidate_rank_score(
    *,
    duration: float,
    min_duration: float,
    max_duration: float,
    transcript_char_count: int,
    speech_seconds: float,
    silence_ratio: float,
) -> float:
    midpoint = (min_duration + max_duration) / 2
    duration_span = max(max_duration - min_duration, 1.0)
    duration_fit = max(0.0, 1.0 - abs(duration - midpoint) / duration_span)
    speech_density = min(1.0, speech_seconds / max(duration, 1.0))
    text_signal = min(1.0, transcript_char_count / 600)
    silence_signal = max(0.0, 1.0 - silence_ratio)
    return (
        speech_density * 45.0
        + text_signal * 25.0
        + duration_fit * 20.0
        + silence_signal * 10.0
    )


def _materialize_candidate(
    lightweight: _LightweightCandidate,
    transcript_index: _TranscriptIndex,
) -> Candidate | None:
    transcript_text = transcript_index.text_for_indices(
        lightweight.segment_start_index,
        lightweight.segment_end_index,
    )
    if not transcript_text:
        return None
    return Candidate(
        id=make_candidate_id(
            lightweight.candidate_type,
            lightweight.start,
            lightweight.end,
            transcript_text,
        ),
        type=lightweight.candidate_type,
        start=lightweight.start,
        end=lightweight.end,
        duration=lightweight.duration,
        transcript_text=transcript_text,
        segment_start_index=lightweight.segment_start_index,
        segment_end_index=lightweight.segment_end_index,
        transcript_char_count=lightweight.transcript_char_count,
        speech_seconds=round(lightweight.speech_seconds, 6),
        silence_ratio=round(lightweight.silence_ratio, 6),
    )


class _BoundedCandidateKeeper:
    def __init__(
        self,
        *,
        settings: CandidateGenerationSettings,
        candidate_type: CandidateType,
        max_candidates: int,
        timeline_duration: float,
        transcript_segment_count: int,
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.candidate_type = candidate_type
        self.effective_kept_limit = min(max_candidates, settings.max_kept_candidates_per_type)
        self.timeline_duration = timeline_duration
        self.transcript_segment_count = transcript_segment_count
        self.heartbeat = heartbeat
        self.buckets: dict[int, dict[tuple[CandidateType, float, float], _LightweightCandidate]] = {}
        self.chunks_processed = 0
        self.raw_candidates_considered = 0
        self.dropped_due_to_cap = 0
        self.dropped_due_to_duplicate = 0
        self.dropped_due_to_no_transcript = 0
        self.dropped_due_to_invalid_duration = 0
        self.memory_guard_triggered = False
        self.peak_memory_mb: float | None = None

    def bucket_index(self, start: float) -> int:
        return int(start // self.settings.candidate_time_bucket_seconds)

    def _update_memory(self) -> None:
        current = _current_rss_mb()
        if current is None:
            return
        if self.peak_memory_mb is None or current > self.peak_memory_mb:
            self.peak_memory_mb = current
        if current > self.settings.max_candidate_generation_memory_mb:
            self.memory_guard_triggered = True
            raise CandidateGenerationMemoryLimitError(self.summary())

    def maybe_heartbeat(self) -> None:
        if self.raw_candidates_considered % 1000 != 0:
            return
        self._update_memory()
        if self.heartbeat is not None:
            self.heartbeat(self.summary())

    def consider(self, candidate: _LightweightCandidate) -> bool:
        self.raw_candidates_considered += 1
        bucket = self.buckets.setdefault(self.bucket_index(candidate.start), {})
        if candidate.key in bucket:
            self.dropped_due_to_duplicate += 1
            self.maybe_heartbeat()
            return True

        if len(bucket) < self.settings.max_candidates_per_time_bucket:
            bucket[candidate.key] = candidate
            self.maybe_heartbeat()
            return True

        worst_key, worst_candidate = min(
            bucket.items(),
            key=lambda item: (
                item[1].rank_score,
                item[1].transcript_char_count,
                -item[1].duration,
                -item[1].start,
            ),
        )
        if candidate.rank_score > worst_candidate.rank_score:
            bucket.pop(worst_key)
            bucket[candidate.key] = candidate
        self.dropped_due_to_cap += 1
        self.maybe_heartbeat()
        return True

    def materialize(self, transcript_index: _TranscriptIndex) -> list[Candidate]:
        lightweight_candidates = [
            candidate
            for bucket in self.buckets.values()
            for candidate in bucket.values()
        ]
        candidates = [
            materialized
            for candidate in lightweight_candidates
            if (materialized := _materialize_candidate(candidate, transcript_index)) is not None
        ]
        deduplicated = deduplicate_candidates(candidates)
        if len(deduplicated) > self.effective_kept_limit:
            self.dropped_due_to_cap += len(deduplicated) - self.effective_kept_limit
        return limit_candidates_by_timeline(deduplicated, self.effective_kept_limit)

    def summary(self) -> dict[str, Any]:
        kept_before_materialize = sum(len(bucket) for bucket in self.buckets.values())
        return {
            "type": self.candidate_type,
            "video_duration": round(self.timeline_duration, 6),
            "transcript_segment_count": self.transcript_segment_count,
            "chunks_processed": self.chunks_processed,
            "raw_candidates_considered": self.raw_candidates_considered,
            "candidates_kept_before_materialize": kept_before_materialize,
            "candidates_dropped_due_to_cap": self.dropped_due_to_cap,
            "candidates_dropped_due_to_duplicate": self.dropped_due_to_duplicate,
            "candidates_dropped_due_to_no_transcript": self.dropped_due_to_no_transcript,
            "candidates_dropped_due_to_invalid_duration": self.dropped_due_to_invalid_duration,
            "peak_memory_mb": self.peak_memory_mb,
            "memory_guard_triggered": self.memory_guard_triggered,
            "configured_caps": {
                "maxRawCandidatesPerType": self.settings.max_raw_candidates_per_type,
                "maxKeptCandidatesPerType": self.settings.max_kept_candidates_per_type,
                "maxCandidatesPerTimeBucket": self.settings.max_candidates_per_time_bucket,
                "candidateTimeBucketSeconds": self.settings.candidate_time_bucket_seconds,
                "maxCandidateGenerationMemoryMb": self.settings.max_candidate_generation_memory_mb,
                "candidateChunkSeconds": self.settings.candidate_chunk_seconds,
                "candidateChunkOverlapSeconds": self.settings.candidate_chunk_overlap_seconds,
                "effectiveKeptLimit": self.effective_kept_limit,
            },
        }


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


def _chunk_ranges(
    timeline_duration: float,
    chunk_seconds: float,
    overlap_seconds: float,
) -> list[tuple[float, float]]:
    if timeline_duration <= 0:
        return []
    if chunk_seconds >= timeline_duration:
        return [(0.0, timeline_duration)]
    ranges: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < timeline_duration:
        chunk_end = min(timeline_duration, cursor + chunk_seconds)
        ranges.append((cursor, min(timeline_duration, chunk_end + overlap_seconds)))
        cursor = chunk_end
    return ranges


def _raw_start_candidates(
    boundaries: Sequence[float],
    transcript_segments: Sequence[TranscriptSegment],
    chunk_start: float,
    chunk_end: float,
) -> list[float]:
    starts = {
        boundary
        for boundary in boundaries[:-1]
        if chunk_start <= boundary < chunk_end
    }
    starts.update(
        segment.start
        for segment in transcript_segments
        if chunk_start <= segment.start < chunk_end
    )
    return sorted(starts)


def generate_window_candidates_with_summary(
    candidate_type: CandidateType,
    transcript_segments: Sequence[TranscriptSegment],
    scene_segments: Sequence[SceneSegment],
    silence_segments: Sequence[SilenceSegment],
    min_duration: float,
    max_duration: float,
    step_seconds: float,
    speech_boundary_tolerance: float,
    max_candidates: int,
    settings: CandidateGenerationSettings | None = None,
    heartbeat: Callable[[dict[str, Any]], None] | None = None,
) -> CandidateGenerationResult:
    parsed_settings = settings or CandidateGenerationSettings(max_candidates=max_candidates)
    timeline_duration = infer_timeline_duration(
        transcript_segments,
        scene_segments,
        silence_segments,
    )
    if timeline_duration <= 0:
        return CandidateGenerationResult(
            candidates=[],
            summary={
                "type": candidate_type,
                "video_duration": 0.0,
                "transcript_segment_count": len(transcript_segments),
                "chunks_processed": 0,
                "raw_candidates_considered": 0,
                "candidates_kept_by_type": {candidate_type: 0},
                "candidates_dropped_due_to_cap": 0,
                "candidates_dropped_due_to_duplicate": 0,
                "peak_memory_mb": _current_rss_mb(),
                "memory_guard_triggered": False,
                "configured_caps": parsed_settings.model_dump(),
            },
        )

    boundaries = merge_boundaries(
        transcript_segments,
        scene_segments,
        silence_segments,
        duration=timeline_duration,
    )
    if not boundaries:
        return CandidateGenerationResult(
            candidates=[],
            summary={
                "type": candidate_type,
                "video_duration": round(timeline_duration, 6),
                "transcript_segment_count": len(transcript_segments),
                "chunks_processed": 0,
                "raw_candidates_considered": 0,
                "candidates_kept_by_type": {candidate_type: 0},
                "candidates_dropped_due_to_cap": 0,
                "candidates_dropped_due_to_duplicate": 0,
                "peak_memory_mb": _current_rss_mb(),
                "memory_guard_triggered": False,
                "configured_caps": parsed_settings.model_dump(),
            },
        )

    transcript_index = _TranscriptIndex(transcript_segments)
    silence_index = _SilenceIndex(silence_segments)
    keeper = _BoundedCandidateKeeper(
        settings=parsed_settings,
        candidate_type=candidate_type,
        max_candidates=max_candidates,
        timeline_duration=timeline_duration,
        transcript_segment_count=len(transcript_segments),
        heartbeat=heartbeat,
    )
    chunk_ranges = _chunk_ranges(
        timeline_duration,
        parsed_settings.candidate_chunk_seconds,
        parsed_settings.candidate_chunk_overlap_seconds,
    )
    chunk_count = max(len(chunk_ranges), 1)
    base_raw_candidate_cap = parsed_settings.max_raw_candidates_per_type // chunk_count
    raw_candidate_cap_remainder = parsed_settings.max_raw_candidates_per_type % chunk_count
    raw_candidate_caps_by_chunk = [
        max(1, base_raw_candidate_cap + (1 if index < raw_candidate_cap_remainder else 0))
        for index in range(chunk_count)
    ]
    for chunk_index, (chunk_start, chunk_end) in enumerate(chunk_ranges):
        keeper.chunks_processed += 1
        raw_candidate_cap_for_chunk = raw_candidate_caps_by_chunk[chunk_index]
        chunk_raw_candidates = 0
        chunk_cap_reached = False
        raw_starts = _raw_start_candidates(
            boundaries,
            transcript_segments,
            chunk_start,
            chunk_end,
        )
        for raw_start in raw_starts:
            if chunk_cap_reached:
                break
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
                duration = _round_time(end - start)
                if duration < min_duration or duration > max_duration:
                    keeper.dropped_due_to_invalid_duration += 1
                    continue
                if is_inside_speech(end, transcript_segments):
                    continue

                transcript_range = transcript_index.range_for(start, end)
                if transcript_range.char_count <= 0:
                    keeper.dropped_due_to_no_transcript += 1
                    continue
                if chunk_raw_candidates >= raw_candidate_cap_for_chunk:
                    keeper.dropped_due_to_cap += 1
                    chunk_cap_reached = True
                    break
                silence_seconds = silence_index.overlap_seconds(start, end)
                silence_ratio = max(0.0, min(1.0, silence_seconds / max(duration, 1.0)))
                keeper.consider(
                    _LightweightCandidate(
                        candidate_type=candidate_type,
                        start=_round_time(start),
                        end=_round_time(end),
                        duration=duration,
                        segment_start_index=transcript_range.start_index,
                        segment_end_index=transcript_range.end_index,
                        transcript_char_count=transcript_range.char_count,
                        speech_seconds=round(transcript_range.speech_seconds, 6),
                        silence_ratio=round(silence_ratio, 6),
                        rank_score=_candidate_rank_score(
                            duration=duration,
                            min_duration=min_duration,
                            max_duration=max_duration,
                            transcript_char_count=transcript_range.char_count,
                            speech_seconds=transcript_range.speech_seconds,
                            silence_ratio=silence_ratio,
                        ),
                    )
                )
                chunk_raw_candidates += 1

    candidates = keeper.materialize(transcript_index)
    summary = keeper.summary()
    summary["candidates_kept_by_type"] = {candidate_type: len(candidates)}
    summary["raw_candidate_caps_by_chunk"] = raw_candidate_caps_by_chunk
    summary["stopped_due_to_raw_candidate_cap"] = False
    return CandidateGenerationResult(candidates=candidates, summary=summary)


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
    return generate_window_candidates_with_summary(
        candidate_type,
        transcript_segments=transcript_segments,
        scene_segments=scene_segments,
        silence_segments=silence_segments,
        min_duration=min_duration,
        max_duration=max_duration,
        step_seconds=step_seconds,
        speech_boundary_tolerance=speech_boundary_tolerance,
        max_candidates=max_candidates,
    ).candidates


def merge_candidate_generation_summaries(
    summaries: Sequence[dict[str, Any]],
    *,
    video_duration: float,
    transcript_segment_count: int,
) -> dict[str, Any]:
    by_type = {str(summary.get("type")): summary for summary in summaries}
    configured_caps = next(
        (summary.get("configured_caps") for summary in summaries if isinstance(summary.get("configured_caps"), dict)),
        {},
    )
    return {
        "video_duration": round(video_duration, 6),
        "transcript_segment_count": transcript_segment_count,
        "chunks_processed": sum(int(summary.get("chunks_processed") or 0) for summary in summaries),
        "raw_candidates_considered": sum(int(summary.get("raw_candidates_considered") or 0) for summary in summaries),
        "candidates_kept_by_type": {
            candidate_type: int((summary.get("candidates_kept_by_type") or {}).get(candidate_type, 0))
            for candidate_type, summary in by_type.items()
        },
        "candidates_dropped_due_to_cap": sum(
            int(summary.get("candidates_dropped_due_to_cap") or 0) for summary in summaries
        ),
        "candidates_dropped_due_to_duplicate": sum(
            int(summary.get("candidates_dropped_due_to_duplicate") or 0) for summary in summaries
        ),
        "candidates_dropped_due_to_no_transcript": sum(
            int(summary.get("candidates_dropped_due_to_no_transcript") or 0) for summary in summaries
        ),
        "candidates_dropped_due_to_invalid_duration": sum(
            int(summary.get("candidates_dropped_due_to_invalid_duration") or 0) for summary in summaries
        ),
        "peak_memory_mb": max(
            [float(summary["peak_memory_mb"]) for summary in summaries if summary.get("peak_memory_mb") is not None],
            default=None,
        ),
        "memory_guard_triggered": any(bool(summary.get("memory_guard_triggered")) for summary in summaries),
        "configured_caps": configured_caps,
        "by_type": by_type,
    }


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
