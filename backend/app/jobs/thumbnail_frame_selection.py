from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image

from app.render.render_thumbnail import _primary_face
from app.video.face_detect import FaceDetection


THUMBNAIL_FRAME_RATIOS = (0.08, 0.24, 0.40, 0.56, 0.72, 0.88)
FaceDetector = Callable[[str | Path, float, float, int], Sequence[FaceDetection]]


def detect_thumbnail_faces_for_clip(
    video_path: str | Path, start: float, end: float, sample_count: int,
) -> list[FaceDetection]:
    """Sample this clip using the same anime-face detector as thumbnail rendering."""
    try:
        import cv2
    except ImportError:
        return []
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []
    found: list[FaceDetection] = []
    try:
        for index in range(sample_count):
            second = start + (end - start) * (index + 0.5) / sample_count
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ok, image = capture.read()
            if not ok or image is None:
                continue
            face = _primary_face(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
            if face is not None:
                found.append(FaceDetection(
                    start=second, end=second,
                    center_x=face[0], center_y=face[1], width=face[2], height=face[3],
                ))
    finally:
        capture.release()
    return found


def _usable_face_times(
    detections: Sequence[FaceDetection],
    *,
    start: float,
    end: float,
) -> list[float]:
    """Return sampled times where a usable face is visible anywhere in frame.

    配信画面では同一フレームの衣装やUIを顔として誤検出する場合がある。
    アニメ顔検出で選んだ十分な大きさの検出を人物の顔として使う。
    """
    grouped: dict[float, FaceDetection] = {}
    for detection in detections:
        if not start <= detection.start <= end:
            continue
        if not 0.08 <= detection.center_y <= 0.85:
            continue
        if detection.width < 0.04 or detection.height < 0.07:
            continue
        previous = grouped.get(detection.start)
        current_priority = (
            detection.center_y,
            -(detection.width * detection.height),
        )
        previous_priority = (
            previous.center_y,
            -(previous.width * previous.height),
        ) if previous is not None else (float("inf"), 0.0)
        if current_priority < previous_priority:
            grouped[detection.start] = detection
    centered = {
        second: face for second, face in grouped.items()
        if 0.18 <= face.center_x <= 0.82
    }
    # When centered frames exist, avoid a character clipped at the source edge.
    return sorted(centered or grouped)


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
            break
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
    face_detector: FaceDetector = detect_thumbnail_faces_for_clip,
) -> float:
    """Choose a distinct clip-relative frame with a visible character face."""
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
