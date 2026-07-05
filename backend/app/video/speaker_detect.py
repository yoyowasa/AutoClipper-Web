from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.video.face_detect import FaceDetection, detect_faces_for_clip
from app.video.person_detect import PersonDetection, detect_person_for_clip


@dataclass(frozen=True)
class DialogueWindow:
    start: float
    end: float
    text_length: int = 0


@dataclass(frozen=True)
class SpeakerRegion:
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    source: str


@dataclass(frozen=True)
class SpeakerDetection:
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    stability_score: float
    window_count: int
    detection_count: int
    box: tuple[float, float, float, float]
    ambiguous: bool = False
    source: str = "dialogue_face_person"


FaceDetector = Callable[[str | Path, float, float], list[FaceDetection]]
PersonDetector = Callable[[str | Path, float, float], PersonDetection | None]

MIN_FACE_AREA = 0.002
MIN_REGION_HEIGHT = 0.12


def _clamp_ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def dialogue_windows_for_clip(
    clip_start: float,
    clip_end: float,
    transcript_segments: Sequence[TranscriptSegment] | None,
    *,
    max_windows: int = 5,
    min_window_seconds: float = 0.5,
) -> list[DialogueWindow]:
    if not transcript_segments or clip_end <= clip_start:
        return []

    windows: list[tuple[float, DialogueWindow]] = []
    for segment in transcript_segments:
        text = segment.text.strip()
        if not text:
            continue
        start = max(float(segment.start), clip_start)
        end = min(float(segment.end), clip_end)
        if end <= start:
            continue
        if end - start < min_window_seconds:
            midpoint = (start + end) / 2
            half = min_window_seconds / 2
            start = max(clip_start, midpoint - half)
            end = min(clip_end, midpoint + half)
        score = (end - start) * max(len(text), 1)
        windows.append((score, DialogueWindow(start=start, end=end, text_length=len(text))))

    windows.sort(key=lambda item: item[0], reverse=True)
    selected = [window for _score, window in windows[:max_windows]]
    selected.sort(key=lambda window: window.start)
    return selected


def _face_area(face: FaceDetection) -> float:
    return max(face.width, 0.0) * max(face.height, 0.0)


def _region_area(region: SpeakerRegion) -> float:
    return max(region.width, 0.0) * max(region.height, 0.0)


def _primary_face_region(detections: Sequence[FaceDetection]) -> tuple[SpeakerRegion | None, bool, int]:
    candidates = [face for face in detections if _face_area(face) >= MIN_FACE_AREA and face.height >= MIN_REGION_HEIGHT]
    if not candidates:
        return None, False, 0

    candidates.sort(key=lambda face: (_face_area(face), face.confidence), reverse=True)
    primary = candidates[0]
    competing = [
        face
        for face in candidates[1:]
        if _face_area(face) >= _face_area(primary) * 0.7 and abs(face.center_x - primary.center_x) > 0.10
    ]
    return (
        SpeakerRegion(
            center_x=_clamp_ratio(primary.center_x),
            center_y=_clamp_ratio(primary.center_y),
            width=_clamp_ratio(primary.width),
            height=_clamp_ratio(primary.height),
            confidence=_clamp_ratio(primary.confidence),
            source="dialogue_face",
        ),
        bool(competing),
        len(candidates),
    )


def _person_region(signal: PersonDetection | None) -> tuple[SpeakerRegion | None, bool, int]:
    if signal is None:
        return None, False, 0
    return (
        SpeakerRegion(
            center_x=signal.center_x,
            center_y=signal.center_y,
            width=signal.width,
            height=signal.height,
            confidence=signal.confidence,
            source="dialogue_person",
        ),
        signal.ambiguous,
        signal.detection_count,
    )


def aggregate_speaker_regions(
    regions: Sequence[SpeakerRegion],
    *,
    window_count: int,
    detection_count: int,
    ambiguous_windows: int = 0,
    min_detection_windows: int = 2,
) -> SpeakerDetection | None:
    if len(regions) < min_detection_windows or window_count <= 0:
        return None

    centers_x = [region.center_x for region in regions]
    centers_y = [region.center_y for region in regions]
    widths = [region.width for region in regions]
    heights = [region.height for region in regions]
    confidences = [region.confidence for region in regions]
    center_stability = 1.0 - min(pstdev(centers_x) / 0.12, 1.0)
    size_stability = 1.0 - min(pstdev([width + height for width, height in zip(widths, heights, strict=True)]) / 0.16, 1.0)
    stability = _clamp_ratio(center_stability * 0.72 + size_stability * 0.28)
    coverage = len(regions) / max(window_count, 1)
    ambiguity_penalty = min(ambiguous_windows / max(window_count, 1), 1.0) * 0.55
    confidence = _clamp_ratio(fmean(confidences) * 0.42 + stability * 0.36 + coverage * 0.22 - ambiguity_penalty)
    center_x = _clamp_ratio(fmean(centers_x))
    center_y = _clamp_ratio(fmean(centers_y))
    width = _clamp_ratio(fmean(widths))
    height = _clamp_ratio(fmean(heights))
    left = _clamp_ratio(center_x - width / 2)
    top = _clamp_ratio(center_y - height / 2)
    right = _clamp_ratio(center_x + width / 2)
    bottom = _clamp_ratio(center_y + height / 2)
    return SpeakerDetection(
        center_x=center_x,
        center_y=center_y,
        width=width,
        height=height,
        confidence=confidence,
        stability_score=stability,
        window_count=window_count,
        detection_count=detection_count,
        box=(left, top, right, bottom),
        ambiguous=ambiguous_windows > 0,
    )


def detect_speaker_for_clip(
    video_path: str | Path,
    start: float,
    end: float,
    dialogue_windows: Sequence[DialogueWindow] | None,
    *,
    face_detector: FaceDetector = detect_faces_for_clip,
    person_detector: PersonDetector = detect_person_for_clip,
) -> SpeakerDetection | None:
    windows = [window for window in dialogue_windows or [] if window.end > window.start]
    if not windows or end <= start:
        return None

    regions: list[SpeakerRegion] = []
    ambiguous_windows = 0
    detection_count = 0
    for window in windows:
        window_start = max(start, window.start)
        window_end = min(end, window.end)
        if window_end <= window_start:
            continue

        faces = face_detector(video_path, window_start, window_end)
        face_region, face_ambiguous, face_count = _primary_face_region(faces)
        detection_count += face_count
        if face_ambiguous:
            ambiguous_windows += 1
            continue
        if face_region is not None:
            regions.append(face_region)
            continue

        person_signal = person_detector(video_path, window_start, window_end)
        person, person_ambiguous, person_count = _person_region(person_signal)
        detection_count += person_count
        if person_ambiguous:
            ambiguous_windows += 1
            continue
        if person is not None:
            regions.append(person)

    return aggregate_speaker_regions(
        regions,
        window_count=len(windows),
        detection_count=detection_count,
        ambiguous_windows=ambiguous_windows,
    )
