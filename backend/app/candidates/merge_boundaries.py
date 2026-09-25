import hashlib
import json
import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.posting_metadata import PostMetadataSource, YouTubeTitleCandidate
from app.video.scene_detect import SceneSegment


CandidateType = Literal["short", "normal"]
DurationBand = tuple[float, float]

NORMAL_DURATION_BANDS: tuple[DurationBand, ...] = (
    (90.0, 180.0),
    (180.0, 300.0),
    (300.0, 600.0),
)
SHORT_DURATION_BANDS: tuple[DurationBand, ...] = (
    (20.0, 35.0),
    (35.0, 50.0),
    (50.0, 75.0),
)
_TOPIC_SILENCE_SECONDS = 1.5
_SEMANTIC_GAP_SECONDS = 0.5
_TOPIC_PREFIX_PATTERN = re.compile(
    r"^(?:さて|では|じゃあ|次(?:に|は)?|ところで|ここから|今回は|今日は|質問|お便り|コメント)"
)
_QUESTION_END_PATTERN = re.compile(
    r"(?:ですか|ますか|でしょうか|なんだろう|なのか|のかな|かな|なぜ|どうして|どう|何|どこ|いつ|誰|どれ)[。…]*$"
)
_COMPLETION_END_PATTERN = re.compile(
    r"(?:ということです|ってことです|なんですよ|と思います|でした|ですね|なんです|わけです|以上)[。…]*$"
)
OpenAIScoreSource = Literal[
    "preselection_pool",
    "finalist_on_demand",
    "fallback_rule_score",
    "not_scored",
]
TitleSource = Literal[
    "openai",
    "transcript_fallback",
    "deterministic_fallback",
    "existing",
    "manual_review",
]
TextFontPreset = Literal[
    "chikara_yowaku", "keifont", "mushin", "ankoku_zonji", "killgo_nb", "tanuki_magic",
    "genei_kiwami_go", "genei_mono_go", "genei_antique",
    "gochi_kakutto", "nikkyou_sans",
    "sans",
    "sans_bold",
    "noto_black",
    "heavy",
    "mplus_extrabold",
    "mplus_rounded_extrabold",
    "chikara",
    "dela_gothic",
    "corporate_logo",
    "serif",
    "mono",
]


class ClipTextStyle(BaseModel):
    font_preset: TextFontPreset | None = Field(default="sans_bold", alias="fontPreset")
    font_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[^,\r\n]+$",
        alias="fontName",
    )
    bold: bool | None = None
    font_size: int = Field(default=76, ge=12, le=220, alias="fontSize")
    primary_color: str = Field(
        default="#FFFFFF",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="primaryColor",
    )
    outline_color: str = Field(
        default="#000000",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        alias="outlineColor",
    )
    outline_width: int = Field(default=5, ge=0, le=20, alias="outlineWidth")
    outer_outline_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$", alias="outerOutlineColor")
    outer_outline_width: int = Field(default=0, ge=0, le=20, alias="outerOutlineWidth")
    x_percent: float = Field(default=50, ge=5, le=95, alias="xPercent")
    y_percent: float = Field(default=85, ge=5, le=95, alias="yPercent")
    position_mode: Literal["explicit", "layout"] = Field(
        default="explicit",
        alias="positionMode",
    )

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class SubtitleStyleOverride(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    style: ClipTextStyle

    @model_validator(mode="after")
    def valid_range(self) -> "SubtitleStyleOverride":
        if self.end <= self.start:
            raise ValueError("subtitle style range must have positive duration")
        return self


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
    heatmap_value: float | None = Field(default=None, ge=0, le=1)
    heatmap_overlap_seconds: float | None = Field(default=None, ge=0)
    heatmap_score: float | None = Field(default=None, ge=0, le=10)
    heatmap_direct_score: float | None = Field(default=None, ge=0, le=1)
    generation_source: Literal["heatmap_interval"] | None = None
    heatmap_seed_start: float | None = Field(default=None, ge=0)
    heatmap_seed_end: float | None = Field(default=None, ge=0)
    heatmap_seed_value: float | None = Field(default=None, ge=0, le=1)
    rule_score: float | None = Field(default=None, ge=0, le=100)
    ai_score: float | None = Field(default=None, ge=0, le=100)
    final_score: float | None = Field(default=None, ge=0, le=100)
    should_use: bool | None = None
    title: str | None = None
    overlay_title: str | None = None
    title_source: TitleSource | None = None
    hook_text: str | None = None
    hook_duration_seconds: float | None = Field(default=None, ge=1, le=8)
    hook_scene_start: float | None = Field(default=None, ge=0)
    hook_scene_end: float | None = Field(default=None, ge=0)
    thumbnail_kicker: str = Field(default="", max_length=40)
    thumbnail_line1: str = Field(default="", max_length=60)
    thumbnail_line2: str = Field(default="", max_length=60)
    thumbnail_frame_seconds: float | None = Field(default=None, ge=0)
    title_candidates: list[YouTubeTitleCandidate] = Field(default_factory=list)
    recommended_title_id: str | None = None
    selected_title_id: str | None = None
    youtube_description: str | None = Field(default=None, max_length=2000)
    youtube_hashtags: list[str] = Field(default_factory=list, max_length=12)
    youtube_tags: list[str] = Field(default_factory=list, max_length=40)
    description_evidence_segment_ids: list[str] = Field(default_factory=list, max_length=64)
    post_metadata_source: PostMetadataSource | None = None
    post_metadata_revision_hash: str | None = Field(default=None, min_length=64, max_length=64)
    title_style: ClipTextStyle | None = None
    hook_style: ClipTextStyle | None = None
    subtitle_style: ClipTextStyle | None = None
    subtitle_styles: list[SubtitleStyleOverride] = Field(default_factory=list, max_length=1000)
    framing_offset_x: float = Field(default=0.0, ge=-100, le=100)
    framing_offset_y: float = Field(default=0.0, ge=-100, le=100)
    framing_zoom: float = Field(default=1.0, ge=1.0, le=3.0)
    short_layout: Literal["auto", "face_tracking_crop", "center_crop", "blur_background"] | None = None
    reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    moment_key: str | None = Field(default=None, min_length=1, max_length=80)
    topic_key: str | None = Field(default=None, min_length=1, max_length=80)
    parent_start: float | None = Field(default=None, ge=0)
    parent_end: float | None = Field(default=None, ge=0)
    evidence_segment_ids: list[str] | None = Field(default=None, max_length=128)
    heatmap_segment_ids: list[str] | None = Field(default=None, max_length=16)
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
    original_start: float | None = Field(default=None, ge=0)
    original_end: float | None = Field(default=None, ge=0)
    refined_start: float | None = Field(default=None, ge=0)
    refined_end: float | None = Field(default=None, ge=0)
    boundary_refined: bool | None = None
    boundary_refinement_reason: str | None = None
    boundary_expansion_seconds: float | None = Field(default=None, ge=0)
    clip_plan_recommended_start: float | None = Field(default=None, ge=0)
    clip_plan_recommended_end: float | None = Field(default=None, ge=0)
    clip_plan_boundary_adjusted: bool | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "Candidate":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if round(self.end - self.start, 6) != round(self.duration, 6):
            raise ValueError("duration must equal end - start")
        title_candidate_ids = [candidate.id for candidate in self.title_candidates]
        if len(title_candidate_ids) != len(set(title_candidate_ids)):
            raise ValueError("duplicate YouTube title candidate id")
        if self.recommended_title_id and self.recommended_title_id not in title_candidate_ids:
            raise ValueError("recommended title id is not in title candidates")
        if self.selected_title_id and self.selected_title_id not in title_candidate_ids:
            raise ValueError("selected title id is not in title candidates")
        if len(self.youtube_hashtags) != len(set(self.youtube_hashtags)):
            raise ValueError("duplicate YouTube hashtag")
        if any(not hashtag.startswith("#") for hashtag in self.youtube_hashtags):
            raise ValueError("YouTube hashtags must start with #")
        if len(self.youtube_tags) != len({tag.casefold() for tag in self.youtube_tags}):
            raise ValueError("duplicate YouTube tag")
        if len(",".join(self.youtube_tags)) > 500:
            raise ValueError("YouTube tags must be 500 characters or fewer")
        hook_start = self.hook_scene_start
        hook_end = self.hook_scene_end
        if (hook_start is None) != (hook_end is None):
            raise ValueError("hook scene requires both start and end")
        if hook_start is not None and hook_end is not None:
            if hook_end <= hook_start:
                raise ValueError("hook scene end must be greater than start")
            if not 0.5 <= hook_end - hook_start <= 3.0:
                raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
            if hook_start < self.start - 0.001 or hook_end > self.end + 0.001:
                raise ValueError("hook scene must stay within the selected clip")
        if (self.parent_start is None) != (self.parent_end is None):
            raise ValueError("parent range requires both start and end")
        if self.parent_start is not None and self.parent_end is not None:
            if self.parent_end <= self.parent_start:
                raise ValueError("parent end must be greater than start")
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
    max_candidates_per_start_bucket: int = Field(default=5, gt=0)
    candidate_start_bucket_seconds: float = Field(default=15.0, gt=0)
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
    topic_key: str

    @property
    def key(self) -> tuple[CandidateType, float, float]:
        return (self.candidate_type, self.start, self.end)


@dataclass(frozen=True)
class _BoundarySignals:
    start_scores: dict[float, int]
    end_scores: dict[float, int]
    topic_starts: tuple[float, ...]


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
        "maxCandidatesPerStartBucket": "max_candidates_per_start_bucket",
        "candidateStartBucketSeconds": "candidate_start_bucket_seconds",
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


def duration_bands_for_range(
    candidate_type: CandidateType,
    min_duration: float,
    max_duration: float,
) -> tuple[DurationBand, ...]:
    """Split the configured hard range at the product's meaningful duration bands."""
    if max_duration < min_duration:
        return ()
    preset = NORMAL_DURATION_BANDS if candidate_type == "normal" else SHORT_DURATION_BANDS
    internal_edges = sorted(
        {
            edge
            for band in preset
            for edge in band
            if min_duration < edge < max_duration
        }
    )
    edges = [float(min_duration), *internal_edges, float(max_duration)]
    bands = tuple(
        (_round_time(lower), _round_time(upper))
        for lower, upper in zip(edges, edges[1:])
        if upper > lower
    )
    if bands:
        return bands
    return ((_round_time(min_duration), _round_time(max_duration)),)


def duration_band_index(duration: float, bands: Sequence[DurationBand]) -> int:
    for index, (lower, upper) in enumerate(bands):
        if duration >= lower - 0.001 and (
            duration < upper - 0.001 or (index == len(bands) - 1 and duration <= upper + 0.001)
        ):
            return index
    return max(0, len(bands) - 1)


def duration_band_label(band: DurationBand) -> str:
    lower, upper = band
    return f"{lower:g}-{upper:g}"


def _looks_like_question(text: str) -> bool:
    clean = re.sub(r"\s+", "", text.strip())
    if not clean:
        return False
    return "?" in clean or "？" in clean or _QUESTION_END_PATTERN.search(clean) is not None


def _looks_like_completion(text: str) -> bool:
    clean = re.sub(r"\s+", "", text.strip())
    if not clean:
        return False
    return clean.endswith(("。", "！", "!", "？", "?")) or _COMPLETION_END_PATTERN.search(clean) is not None


def _looks_like_topic_start(text: str) -> bool:
    clean = re.sub(r"\s+", "", text.strip())
    return bool(clean and _TOPIC_PREFIX_PATTERN.search(clean))


def _record_boundary(target: dict[float, int], time_seconds: float, score: int) -> None:
    clean = _round_time(time_seconds)
    target[clean] = max(score, target.get(clean, 0))


def _semantic_boundary_signals(
    transcript_segments: Sequence[TranscriptSegment],
    scene_segments: Sequence[SceneSegment],
    silence_segments: Sequence[SilenceSegment],
    timeline_duration: float,
) -> _BoundarySignals:
    start_scores: dict[float, int] = {0.0: 6}
    end_scores: dict[float, int] = {_round_time(timeline_duration): 6}
    topic_starts = {0.0}

    ordered_transcript = sorted(transcript_segments, key=lambda segment: (segment.start, segment.end))
    for index, segment in enumerate(ordered_transcript):
        start = _round_time(segment.start)
        end = _round_time(segment.end)
        # Whisper segments remain valid fallback boundaries, while semantic cues rank higher.
        _record_boundary(start_scores, start, 1)
        _record_boundary(end_scores, end, 1)
        if index == 0:
            _record_boundary(start_scores, start, 5)
            topic_starts.add(start)
        if index == len(ordered_transcript) - 1:
            _record_boundary(end_scores, end, 5)
        text = segment.text.strip()
        if _looks_like_question(text):
            _record_boundary(start_scores, start, 6)
            _record_boundary(end_scores, end, 4)
            topic_starts.add(start)
        if _looks_like_topic_start(text):
            _record_boundary(start_scores, start, 5)
            topic_starts.add(start)
        if _looks_like_completion(text):
            _record_boundary(end_scores, end, 5)

        if index > 0:
            previous = ordered_transcript[index - 1]
            gap = max(0.0, float(segment.start) - float(previous.end))
            if gap >= _SEMANTIC_GAP_SECONDS:
                score = 5 if gap >= _TOPIC_SILENCE_SECONDS else 3
                _record_boundary(end_scores, previous.end, score)
                _record_boundary(start_scores, segment.start, score)
            if gap >= _TOPIC_SILENCE_SECONDS:
                topic_starts.add(start)

    for segment in silence_segments:
        _record_boundary(end_scores, segment.start, 6)
        _record_boundary(start_scores, segment.end, 6)
        if segment.duration >= _TOPIC_SILENCE_SECONDS:
            topic_starts.add(_round_time(segment.end))

    # Scene cuts are weak fallback signals. They never outrank speech completion or silence.
    for segment in scene_segments:
        _record_boundary(start_scores, segment.start, 2)
        _record_boundary(end_scores, segment.end, 2)

    valid_topic_starts = tuple(
        sorted(value for value in topic_starts if 0 <= value < timeline_duration)
    )
    return _BoundarySignals(
        start_scores={key: value for key, value in start_scores.items() if 0 <= key < timeline_duration},
        end_scores={key: value for key, value in end_scores.items() if 0 < key <= timeline_duration},
        topic_starts=valid_topic_starts,
    )


def _topic_key_for_range(start: float, end: float, topic_starts: Sequence[float]) -> str:
    early_limit = min(end, start + 15.0)
    next_index = bisect_left(topic_starts, start)
    if next_index < len(topic_starts) and topic_starts[next_index] <= early_limit:
        anchor = topic_starts[next_index]
    else:
        anchor = topic_starts[next_index - 1] if next_index > 0 else 0.0
    return f"topic_{int(round(anchor * 1000))}"


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
        segment.text.strip() for segment in transcript_segments if segment.text.strip() and segment.end > start and segment.start < end
    ]
    return " ".join(texts).strip()


def make_candidate_id(candidate_type: CandidateType, start: float, end: float, transcript_text: str) -> str:
    digest = hashlib.sha1(f"{candidate_type}:{start:.3f}:{end:.3f}:{transcript_text}".encode("utf-8")).hexdigest()[:10]
    return f"cand_{candidate_type}_{int(start * 1000)}_{int(end * 1000)}_{digest}"


def _candidate_rank_score(
    *,
    duration: float,
    transcript_char_count: int,
    speech_seconds: float,
    silence_ratio: float,
) -> float:
    speech_density = min(1.0, speech_seconds / max(duration, 1.0))
    text_signal = min(1.0, transcript_char_count / 600)
    silence_signal = max(0.0, 1.0 - silence_ratio)
    return speech_density * 45.0 + text_signal * 35.0 + silence_signal * 20.0


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
        topic_key=lightweight.topic_key,
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
        duration_bands: Sequence[DurationBand],
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.candidate_type = candidate_type
        self.effective_kept_limit = min(max_candidates, settings.max_kept_candidates_per_type)
        self.timeline_duration = timeline_duration
        self.transcript_segment_count = transcript_segment_count
        self.duration_bands = tuple(duration_bands)
        self.heartbeat = heartbeat
        self.buckets: dict[
            tuple[int, int],
            dict[tuple[CandidateType, float, float], _LightweightCandidate],
        ] = {}
        self.chunks_processed = 0
        self.raw_candidates_considered = 0
        self.dropped_due_to_cap = 0
        self.dropped_due_to_duplicate = 0
        self.dropped_due_to_no_transcript = 0
        self.dropped_due_to_invalid_duration = 0
        self.considered_by_duration_band = [0 for _ in self.duration_bands]
        self.memory_guard_triggered = False
        self.peak_memory_mb: float | None = None

    def bucket_index(self, start: float) -> int:
        return int(start // self.settings.candidate_time_bucket_seconds)

    def start_bucket_index(self, start: float) -> int:
        return int(start // self.settings.candidate_start_bucket_seconds)

    def duration_band_index(self, duration: float) -> int:
        return duration_band_index(duration, self.duration_bands)

    @staticmethod
    def _reserved_band_limit(total_limit: int, band_index: int, band_count: int) -> int:
        base, remainder = divmod(total_limit, max(1, band_count))
        return max(1, base + (1 if band_index < remainder else 0))

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
        band_index = self.duration_band_index(candidate.duration)
        self.considered_by_duration_band[band_index] += 1
        bucket = self.buckets.setdefault((self.bucket_index(candidate.start), band_index), {})
        if candidate.key in bucket:
            self.dropped_due_to_duplicate += 1
            self.maybe_heartbeat()
            return True

        same_start_bucket = [
            (key, item) for key, item in bucket.items() if self.start_bucket_index(item.start) == self.start_bucket_index(candidate.start)
        ]
        start_bucket_limit = self._reserved_band_limit(
            self.settings.max_candidates_per_start_bucket,
            band_index,
            len(self.duration_bands),
        )
        if len(same_start_bucket) >= start_bucket_limit:
            worst_key, worst_candidate = min(
                same_start_bucket,
                key=lambda item: (
                    item[1].rank_score,
                    item[1].transcript_char_count,
                    item[1].duration,
                    -item[1].start,
                ),
            )
            if candidate.rank_score > worst_candidate.rank_score:
                bucket.pop(worst_key)
                bucket[candidate.key] = candidate
            self.dropped_due_to_cap += 1
            self.maybe_heartbeat()
            return True

        time_bucket_limit = self._reserved_band_limit(
            self.settings.max_candidates_per_time_bucket,
            band_index,
            len(self.duration_bands),
        )
        if len(bucket) < time_bucket_limit:
            bucket[candidate.key] = candidate
            self.maybe_heartbeat()
            return True

        worst_key, worst_candidate = min(
            bucket.items(),
            key=lambda item: (
                item[1].rank_score,
                item[1].transcript_char_count,
                item[1].duration,
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
        lightweight_candidates = [candidate for bucket in self.buckets.values() for candidate in bucket.values()]
        candidates = [
            materialized
            for candidate in lightweight_candidates
            if (materialized := _materialize_candidate(candidate, transcript_index)) is not None
        ]
        deduplicated = deduplicate_candidates(candidates)
        if len(deduplicated) > self.effective_kept_limit:
            self.dropped_due_to_cap += len(deduplicated) - self.effective_kept_limit
        return limit_candidates_by_timeline_and_duration_band(
            deduplicated,
            self.effective_kept_limit,
            self.duration_bands,
        )

    def summary(self) -> dict[str, Any]:
        kept_before_materialize = sum(len(bucket) for bucket in self.buckets.values())
        kept_by_duration_band = {
            duration_band_label(band): sum(
                len(bucket)
                for (time_bucket, band_index), bucket in self.buckets.items()
                if band_index == index
            )
            for index, band in enumerate(self.duration_bands)
        }
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
                "maxCandidatesPerStartBucket": self.settings.max_candidates_per_start_bucket,
                "candidateStartBucketSeconds": self.settings.candidate_start_bucket_seconds,
                "maxCandidateGenerationMemoryMb": self.settings.max_candidate_generation_memory_mb,
                "candidateChunkSeconds": self.settings.candidate_chunk_seconds,
                "candidateChunkOverlapSeconds": self.settings.candidate_chunk_overlap_seconds,
                "effectiveKeptLimit": self.effective_kept_limit,
            },
            "duration_bands": [
                {
                    "label": duration_band_label(band),
                    "min_duration": band[0],
                    "max_duration": band[1],
                    "considered": self.considered_by_duration_band[index],
                    "kept_before_materialize": kept_by_duration_band[duration_band_label(band)],
                }
                for index, band in enumerate(self.duration_bands)
            ],
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


def limit_candidates_by_timeline_and_duration_band(
    candidates: Sequence[Candidate],
    max_candidates: int,
    duration_bands: Sequence[DurationBand],
) -> list[Candidate]:
    """Reserve room for every populated duration band before applying the global cap."""
    ordered = sorted(candidates, key=lambda item: (item.start, item.duration, item.type, item.id))
    if len(ordered) <= max_candidates:
        return ordered

    groups: dict[int, list[Candidate]] = {}
    for candidate in ordered:
        band_index = duration_band_index(candidate.duration, duration_bands)
        groups.setdefault(band_index, []).append(candidate)

    band_order = sorted(groups)
    base_quota, quota_remainder = divmod(max_candidates, len(band_order))
    limited: list[Candidate] = []
    selected_ids: set[str] = set()
    for order_index, band_index in enumerate(band_order):
        quota = base_quota + (1 if order_index < quota_remainder else 0)
        selected = limit_candidates_by_timeline(groups[band_index], quota)
        limited.extend(selected)
        selected_ids.update(candidate.id for candidate in selected)

    if len(limited) < max_candidates:
        remaining = [candidate for candidate in ordered if candidate.id not in selected_ids]
        limited.extend(
            limit_candidates_by_timeline(remaining, max_candidates - len(limited))
        )
    return sorted(limited, key=lambda item: (item.start, item.duration, item.type, item.id))


def _candidate_end_targets(
    start: float,
    boundaries: Sequence[float],
    min_duration: float,
    max_duration: float,
) -> list[float]:
    minimum_end = start + min_duration
    maximum_end = start + max_duration
    left = bisect_left(boundaries, minimum_end)
    right = bisect_right(boundaries, maximum_end)
    return list(boundaries[left:right])


def _spread_across_timeline(values: Sequence[float], limit: int) -> list[float]:
    if limit <= 0 or not values:
        return []
    if len(values) <= limit:
        return list(values)
    if limit == 1:
        return [values[len(values) // 2]]
    indices = {round(index * (len(values) - 1) / (limit - 1)) for index in range(limit)}
    return [values[index] for index in sorted(indices)]


def _prioritize_end_targets(
    targets: Sequence[float],
    *,
    start: float,
    duration_bands: Sequence[DurationBand],
    boundary_scores: dict[float, int],
    limit: int,
    rotation: int = 0,
) -> list[float]:
    if limit <= 0:
        return []
    groups: dict[int, list[float]] = {}
    for end in targets:
        band_index = duration_band_index(end - start, duration_bands)
        groups.setdefault(band_index, []).append(end)
    for group in groups.values():
        group.sort(key=lambda end: (-boundary_scores.get(_round_time(end), 0), end))

    band_order = sorted(groups)
    if band_order:
        offset = rotation % len(band_order)
        band_order = band_order[offset:] + band_order[:offset]
    prioritized: list[float] = []
    while len(prioritized) < limit and any(groups.values()):
        for band_index in band_order:
            group = groups[band_index]
            if not group:
                continue
            prioritized.append(group.pop(0))
            if len(prioritized) >= limit:
                break
    return prioritized


def _configured_duration_range(
    *,
    min_duration: float,
    max_duration: float,
    step_seconds: float,
    speech_boundary_tolerance: float,
) -> dict[str, float | bool]:
    return {
        "min_duration": round(float(min_duration), 6),
        "max_duration": round(float(max_duration), 6),
        "step_seconds": round(float(step_seconds), 6),
        "target_step_applied": False,
        "speech_boundary_tolerance": round(float(speech_boundary_tolerance), 6),
    }


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
    chunk_start: float,
    chunk_end: float,
) -> list[float]:
    return sorted(boundary for boundary in boundaries if chunk_start <= boundary < chunk_end)


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
    duration_bands = duration_bands_for_range(candidate_type, min_duration, max_duration)
    configured_duration_range = _configured_duration_range(
        min_duration=min_duration,
        max_duration=max_duration,
        step_seconds=step_seconds,
        speech_boundary_tolerance=speech_boundary_tolerance,
    )
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
                "configured_duration_range": configured_duration_range,
                "duration_bands": [
                    {
                        "label": duration_band_label(band),
                        "min_duration": band[0],
                        "max_duration": band[1],
                        "considered": 0,
                        "kept_before_materialize": 0,
                        "kept": 0,
                    }
                    for band in duration_bands
                ],
                "duration_band_counts": {
                    duration_band_label(band): 0 for band in duration_bands
                },
                "boundary_policy": "semantic_transcript_question_completion_silence",
            },
        )

    boundary_signals = _semantic_boundary_signals(
        transcript_segments,
        scene_segments,
        silence_segments,
        timeline_duration,
    )
    start_boundaries = sorted(
        boundary for boundary, score in boundary_signals.start_scores.items() if score >= 5
    )
    end_boundaries = sorted(
        boundary for boundary, score in boundary_signals.end_scores.items() if score >= 4
    )
    if len(start_boundaries) < 2:
        start_boundaries = sorted(boundary_signals.start_scores)
    if len(end_boundaries) < 2:
        end_boundaries = sorted(boundary_signals.end_scores)
    if not start_boundaries or not end_boundaries:
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
                "configured_duration_range": configured_duration_range,
                "duration_bands": [
                    {
                        "label": duration_band_label(band),
                        "min_duration": band[0],
                        "max_duration": band[1],
                        "considered": 0,
                        "kept_before_materialize": 0,
                        "kept": 0,
                    }
                    for band in duration_bands
                ],
                "duration_band_counts": {
                    duration_band_label(band): 0 for band in duration_bands
                },
                "boundary_policy": "semantic_transcript_question_completion_silence",
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
        duration_bands=duration_bands,
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
        max(1, base_raw_candidate_cap + (1 if index < raw_candidate_cap_remainder else 0)) for index in range(chunk_count)
    ]
    exact_duration_fallback_candidates_considered = 0
    for chunk_index, (chunk_start, chunk_end) in enumerate(chunk_ranges):
        keeper.chunks_processed += 1
        raw_candidate_cap_for_chunk = raw_candidate_caps_by_chunk[chunk_index]
        chunk_raw_candidates = 0
        chunk_cap_reached = False
        raw_starts = _raw_start_candidates(
            start_boundaries,
            chunk_start,
            chunk_end,
        )
        adjusted_starts: list[float] = []
        seen_starts: set[float] = set()
        for raw_start in raw_starts:
            start = adjust_start_to_speech_boundary(
                raw_start,
                transcript_segments,
                tolerance=speech_boundary_tolerance,
            )
            if start in seen_starts or start >= timeline_duration or is_inside_speech(start, transcript_segments):
                continue
            seen_starts.add(start)
            adjusted_starts.append(start)

        if len(adjusted_starts) > raw_candidate_cap_for_chunk:
            keeper.dropped_due_to_cap += len(adjusted_starts) - raw_candidate_cap_for_chunk
            adjusted_starts = _spread_across_timeline(
                adjusted_starts,
                raw_candidate_cap_for_chunk,
            )

        start_count = max(1, len(adjusted_starts))
        base_budget = raw_candidate_cap_for_chunk // start_count
        budget_remainder = raw_candidate_cap_for_chunk % start_count
        for start_index, start in enumerate(adjusted_starts):
            if chunk_cap_reached:
                break

            end_targets = _candidate_end_targets(
                start,
                end_boundaries,
                min_duration=min_duration,
                max_duration=max_duration,
            )
            exact_duration_fallback_targets: set[float] = set()
            if abs(max_duration - min_duration) <= 0.001:
                exact_end = _round_time(start + min_duration)
                if exact_end <= timeline_duration + 0.001 and exact_end not in {
                    _round_time(value) for value in end_targets
                }:
                    end_targets.append(exact_end)
                    end_targets.sort()
                    exact_duration_fallback_targets.add(exact_end)
            start_budget = base_budget + (1 if start_index < budget_remainder else 0)
            prioritized_targets = _prioritize_end_targets(
                end_targets,
                start=start,
                duration_bands=duration_bands,
                boundary_scores=boundary_signals.end_scores,
                limit=max(1, start_budget),
                rotation=start_index,
            )
            keeper.dropped_due_to_cap += max(0, len(end_targets) - len(prioritized_targets))
            for raw_end in prioritized_targets:
                is_exact_duration_fallback = (
                    _round_time(raw_end) in exact_duration_fallback_targets
                )
                end = (
                    _round_time(raw_end)
                    if is_exact_duration_fallback
                    else adjust_end_to_speech_boundary(
                        raw_end,
                        transcript_segments,
                        tolerance=speech_boundary_tolerance,
                    )
                )
                if end > timeline_duration:
                    end = timeline_duration
                duration = _round_time(end - start)
                if duration < min_duration or duration > max_duration:
                    keeper.dropped_due_to_invalid_duration += 1
                    continue
                if not is_exact_duration_fallback and is_inside_speech(
                    end,
                    transcript_segments,
                ):
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
                            transcript_char_count=transcript_range.char_count,
                            speech_seconds=transcript_range.speech_seconds,
                            silence_ratio=silence_ratio,
                        ),
                        topic_key=_topic_key_for_range(
                            start,
                            end,
                            boundary_signals.topic_starts,
                        ),
                    )
                )
                if is_exact_duration_fallback:
                    exact_duration_fallback_candidates_considered += 1
                chunk_raw_candidates += 1

    candidates = keeper.materialize(transcript_index)
    summary = keeper.summary()
    summary["configured_duration_range"] = configured_duration_range
    summary["candidates_kept_by_type"] = {candidate_type: len(candidates)}
    duration_band_counts = {
        duration_band_label(band): sum(
            1 for candidate in candidates if duration_band_index(candidate.duration, duration_bands) == index
        )
        for index, band in enumerate(duration_bands)
    }
    summary["duration_band_counts"] = duration_band_counts
    for band_summary in summary["duration_bands"]:
        band_summary["kept"] = duration_band_counts[band_summary["label"]]
    summary["boundary_policy"] = "semantic_transcript_question_completion_silence"
    summary["exact_duration_fallback_candidates_considered"] = (
        exact_duration_fallback_candidates_considered
    )
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
    configured_duration_ranges = {
        candidate_type: duration_range
        for candidate_type, summary in by_type.items()
        if isinstance(duration_range := summary.get("configured_duration_range"), dict)
    }
    duration_bands_by_type = {
        candidate_type: duration_bands
        for candidate_type, summary in by_type.items()
        if isinstance(duration_bands := summary.get("duration_bands"), list)
    }
    duration_band_counts_by_type = {
        candidate_type: duration_band_counts
        for candidate_type, summary in by_type.items()
        if isinstance(duration_band_counts := summary.get("duration_band_counts"), dict)
    }
    return {
        "video_duration": round(video_duration, 6),
        "transcript_segment_count": transcript_segment_count,
        "chunks_processed": sum(int(summary.get("chunks_processed") or 0) for summary in summaries),
        "raw_candidates_considered": sum(int(summary.get("raw_candidates_considered") or 0) for summary in summaries),
        "candidates_kept_by_type": {
            candidate_type: int((summary.get("candidates_kept_by_type") or {}).get(candidate_type, 0))
            for candidate_type, summary in by_type.items()
        },
        "candidates_dropped_due_to_cap": sum(int(summary.get("candidates_dropped_due_to_cap") or 0) for summary in summaries),
        "candidates_dropped_due_to_duplicate": sum(int(summary.get("candidates_dropped_due_to_duplicate") or 0) for summary in summaries),
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
        "configured_duration_ranges": configured_duration_ranges,
        "duration_bands_by_type": duration_bands_by_type,
        "duration_band_counts_by_type": duration_band_counts_by_type,
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
