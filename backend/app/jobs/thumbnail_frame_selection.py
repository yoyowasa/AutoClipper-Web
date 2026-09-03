from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from app.video.face_detect import FaceDetection, detect_faces_for_clip


THUMBNAIL_FRAME_RATIOS = (0.08, 0.24, 0.40, 0.56, 0.72, 0.88)
FaceDetector = Callable[[str | Path, float, float, int], Sequence[FaceDetection]]


def _usable_face_times(
    detections: Sequence[FaceDetection],
    *,
    start: float,
    end: float,
) -> list[float]:
    """Return sampled times where a usable, right-side face is visible."""
    grouped: dict[float, FaceDetection] = {}
    for detection in detections:
        if not start <= detection.start <= end:
            continue
        if detection.center_x < 0.48 or not 0.38 <= detection.center_y <= 0.86:
            continue
        if detection.width < 0.03 or detection.height < 0.03:
            continue
        previous = grouped.get(detection.start)
        score = detection.width * detection.height * (0.75 + detection.center_x * 0.25)
        previous_score = (
            previous.width * previous.height * (0.75 + previous.center_x * 0.25)
            if previous is not None
            else -1.0
        )
        if score > previous_score:
            grouped[detection.start] = detection
    return sorted(grouped)


def _candidate_times(
    face_times: Sequence[float],
    *,
    start: float,
    end: float,
) -> list[float]:
    duration = max(0.0, end - start)
    targets = [start + duration * ratio for ratio in THUMBNAIL_FRAME_RATIOS]
    if not face_times:
        return targets

    remaining = list(face_times)
    selected: list[float] = []
    for target in targets:
        if not remaining:
            selected.append(target)
            continue
        closest = min(remaining, key=lambda value: abs(value - target))
        selected.append(closest)
        remaining.remove(closest)
    return selected


def select_thumbnail_frame_seconds(
    video_path: str | Path,
    *,
    clip_start: float,
    clip_end: float,
    variant_index: int,
    face_detector: FaceDetector = detect_faces_for_clip,
) -> float:
    """Choose a distinct clip-relative frame, preferring visible right-side faces."""
    start = max(0.0, float(clip_start))
    end = max(start, float(clip_end))
    duration = end - start
    if duration <= 0:
        return 0.0

    detections = face_detector(video_path, start, end, 24)
    frame_times = _candidate_times(
        _usable_face_times(detections, start=start, end=end),
        start=start,
        end=end,
    )
    selected = frame_times[max(0, int(variant_index)) % len(frame_times)]
    return round(min(duration, max(0.0, selected - start)), 3)
