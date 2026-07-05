from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class PersonBox:
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float = 1.0


@dataclass(frozen=True)
class PersonDetection:
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    stability_score: float
    sampled_frames: int
    detection_count: int
    box: tuple[float, float, float, float]
    ambiguous: bool = False
    source: str = "person_detection"


def _clamp_ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _sample_times(start: float, end: float, sample_count: int) -> list[float]:
    if sample_count <= 0 or end <= start:
        return []
    if sample_count == 1:
        return [(start + end) / 2]
    step = (end - start) / (sample_count - 1)
    return [start + step * index for index in range(sample_count)]


def _load_cv2() -> Any | None:
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def _load_numpy() -> Any | None:
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def _create_hog_detector(cv2: Any) -> Any | None:
    if not hasattr(cv2, "HOGDescriptor") or not hasattr(cv2, "HOGDescriptor_getDefaultPeopleDetector"):
        return None
    detector = cv2.HOGDescriptor()
    detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    return detector


def _box_area(box: PersonBox) -> float:
    return max(box.width, 0.0) * max(box.height, 0.0)


def aggregate_person_detections(
    boxes_by_frame: Sequence[Sequence[PersonBox]],
    *,
    min_detection_frames: int = 2,
) -> PersonDetection | None:
    np = _load_numpy()
    if np is None:
        return None

    selected: list[PersonBox] = []
    ambiguous_frames = 0
    detection_count = 0
    for frame_boxes in boxes_by_frame:
        candidates = [box for box in frame_boxes if _box_area(box) >= 0.015 and box.height >= 0.18]
        detection_count += len(candidates)
        if not candidates:
            continue
        candidates.sort(key=lambda box: (_box_area(box), box.confidence), reverse=True)
        primary = candidates[0]
        competing = [
            box
            for box in candidates[1:]
            if _box_area(box) >= _box_area(primary) * 0.55 and abs(box.center_x - primary.center_x) > 0.12
        ]
        if competing:
            ambiguous_frames += 1
        selected.append(primary)

    if len(selected) < min_detection_frames:
        return None

    centers_x = np.asarray([box.center_x for box in selected], dtype="float32")
    centers_y = np.asarray([box.center_y for box in selected], dtype="float32")
    widths = np.asarray([box.width for box in selected], dtype="float32")
    heights = np.asarray([box.height for box in selected], dtype="float32")
    confidences = np.asarray([box.confidence for box in selected], dtype="float32")
    center_stability = 1.0 - min(float(np.std(centers_x)) / 0.14, 1.0)
    size_stability = 1.0 - min(float(np.std(widths + heights)) / 0.18, 1.0)
    stability = _clamp_ratio(center_stability * 0.7 + size_stability * 0.3)
    coverage = len(selected) / max(len(boxes_by_frame), 1)
    ambiguity_penalty = min(ambiguous_frames / max(len(selected), 1), 1.0) * 0.45
    confidence = _clamp_ratio(float(np.mean(confidences)) * 0.45 + stability * 0.30 + coverage * 0.25 - ambiguity_penalty)
    center_x = _clamp_ratio(float(np.mean(centers_x)))
    center_y = _clamp_ratio(float(np.mean(centers_y)))
    width = _clamp_ratio(float(np.mean(widths)))
    height = _clamp_ratio(float(np.mean(heights)))
    left = _clamp_ratio(center_x - width / 2)
    top = _clamp_ratio(center_y - height / 2)
    right = _clamp_ratio(center_x + width / 2)
    bottom = _clamp_ratio(center_y + height / 2)
    return PersonDetection(
        center_x=center_x,
        center_y=center_y,
        width=width,
        height=height,
        confidence=confidence,
        stability_score=stability,
        sampled_frames=len(boxes_by_frame),
        detection_count=detection_count,
        box=(left, top, right, bottom),
        ambiguous=ambiguous_frames > 0,
    )


def _detect_people_in_frame(frame: Any, cv2: Any, detector: Any, max_width: int) -> list[PersonBox]:
    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return []
    scale = 1.0
    resized = frame
    if width > max_width:
        scale = max_width / width
        resized = cv2.resize(frame, (max_width, max(1, round(height * scale))), interpolation=cv2.INTER_AREA)

    boxes, weights = detector.detectMultiScale(
        resized,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )
    results: list[PersonBox] = []
    for index, (x, y, box_width, box_height) in enumerate(boxes):
        weight = float(weights[index]) if index < len(weights) else 1.0
        confidence = _clamp_ratio((weight + 0.5) / 2.0)
        original_x = float(x) / scale
        original_y = float(y) / scale
        original_width = float(box_width) / scale
        original_height = float(box_height) / scale
        results.append(
            PersonBox(
                center_x=_clamp_ratio((original_x + original_width / 2) / width),
                center_y=_clamp_ratio((original_y + original_height / 2) / height),
                width=_clamp_ratio(original_width / width),
                height=_clamp_ratio(original_height / height),
                confidence=confidence,
            )
        )
    return results


def detect_person_for_clip(
    video_path: str | Path,
    start: float,
    end: float,
    sample_count: int = 3,
    max_width: int = 416,
) -> PersonDetection | None:
    cv2 = _load_cv2()
    if cv2 is None:
        return None
    detector = _create_hog_detector(cv2)
    if detector is None:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    boxes_by_frame: list[list[PersonBox]] = []
    try:
        for time_seconds in _sample_times(start, end, sample_count):
            capture.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                boxes_by_frame.append([])
                continue
            boxes_by_frame.append(_detect_people_in_frame(frame, cv2=cv2, detector=detector, max_width=max_width))
    finally:
        capture.release()

    return aggregate_person_detections(boxes_by_frame)
