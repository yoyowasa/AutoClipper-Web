"""Find audible subtitle gaps without decoding audio or changing review content."""

import json
import logging
import math
from collections.abc import Iterable, Sequence
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.audio.silence_detect import SilenceSegment, silence_output_path

if TYPE_CHECKING:
    from app.jobs.subtitle_review import SubtitleReviewDocument


MIN_SUBTITLE_GAP_SECONDS = 3.0
MIN_SUBTITLE_GAP_SOUND_RATIO = 0.6
_EPSILON = 1e-9
logger = logging.getLogger(__name__)


class SubtitleGap(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    source_start: float = Field(ge=0, alias="sourceStart")
    source_end: float = Field(ge=0, alias="sourceEnd")
    acknowledged: bool = False

    model_config = ConfigDict(populate_by_name=True)


def _merge_ranges(ranges: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(ranges):
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def detect_subtitle_gaps(
    *,
    clip_id: str,
    clip_start: float,
    clip_end: float,
    subtitle_ranges: Sequence[tuple[float, float]],
    silence_ranges: Sequence[tuple[float, float]],
    hook_duration: float = 0.0,
    acknowledged_ids: Iterable[str] = (),
) -> list[SubtitleGap]:
    """Return whole uncovered intervals with at least 60 percent non-silence.

    Inputs use source-video seconds. Outputs use player seconds after the hook
    insert, so the hook itself is never inspected or marked as a subtitle gap.
    """
    covered = _merge_ranges(
        (max(clip_start, start), min(clip_end, end))
        for start, end in subtitle_ranges
        if start < clip_end and end > clip_start
    )
    empty: list[tuple[float, float]] = []
    cursor = clip_start
    for start, end in covered:
        if start > cursor:
            empty.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < clip_end:
        empty.append((cursor, clip_end))

    silences = _merge_ranges(silence_ranges)
    acknowledged = set(acknowledged_ids)
    gaps: list[SubtitleGap] = []
    silence_index = 0
    for start, end in empty:
        duration = end - start
        if duration + _EPSILON < MIN_SUBTITLE_GAP_SECONDS:
            continue
        while silence_index < len(silences) and silences[silence_index][1] <= start:
            silence_index += 1
        silent_seconds = 0.0
        for silence_start, silence_end in silences[silence_index:]:
            if silence_start >= end:
                break
            silent_seconds += max(0.0, min(end, silence_end) - max(start, silence_start))
        sound_seconds = duration - silent_seconds
        if sound_seconds + _EPSILON < duration * MIN_SUBTITLE_GAP_SOUND_RATIO:
            continue
        player_start = start - clip_start + hook_duration
        player_end = end - clip_start + hook_duration
        # Include both source and player coordinates: a changed boundary or
        # hook insert must not inherit acknowledgement of a different interval.
        key = f"{clip_id}:{start:.9f}:{end:.9f}:{player_start:.9f}:{player_end:.9f}"
        gap_id = "gap_" + sha256(key.encode("utf-8")).hexdigest()[:24]
        gaps.append(SubtitleGap(
            id=gap_id, start=player_start, end=player_end,
            sourceStart=start, sourceEnd=end, acknowledged=gap_id in acknowledged,
        ))
    return gaps


def _load_silence_ranges(output_dir: Path) -> list[tuple[float, float]] | None:
    path = silence_output_path(output_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("silence segments must be a list")
        segments = [SilenceSegment.model_validate(item) for item in payload]
    except (OSError, ValueError):
        # Optional analysis must not make otherwise valid legacy reviews unreadable.
        logger.warning("Subtitle gap analysis skipped: silence artifact is unreadable: %s", path.name)
        return None
    return [(segment.start, segment.end) for segment in segments]


def refresh_review_gaps(document: "SubtitleReviewDocument", output_dir: Path) -> None:
    silence_ranges = _load_silence_ranges(output_dir)
    segments_by_id = {segment.id: segment for segment in document.segments}
    for clip in document.clips:
        if silence_ranges is None:
            clip.gaps = []
            continue
        subtitles = [segments_by_id[segment_id] for segment_id in clip.segment_ids if segment_id in segments_by_id]
        hook_duration = (
            clip.hook_scene_end - clip.hook_scene_start
            if clip.type == "short" and clip.hook_scene_start is not None and clip.hook_scene_end is not None
            else 0.0
        )
        subtitle_ranges = [(segment.start, segment.end) for segment in subtitles if segment.text.strip()]
        if clip.type == "short" and clip.hook_text.strip():
            # The renderer intentionally suppresses ordinary subtitles while
            # hook text is shown, including the body after an inserted hook.
            suppression_end = clip.start + max(0.0, clip.hook_duration_seconds - hook_duration)
            subtitle_ranges.append((clip.start, suppression_end))
        clip.gaps = detect_subtitle_gaps(
            clip_id=clip.id, clip_start=clip.start, clip_end=clip.end,
            subtitle_ranges=subtitle_ranges,
            silence_ranges=silence_ranges, hook_duration=hook_duration,
            acknowledged_ids=[gap.id for gap in clip.gaps if gap.acknowledged],
        )
