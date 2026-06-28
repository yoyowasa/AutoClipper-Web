from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class FaceDetection:
    start: float
    end: float
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float = 1.0


def _clamp_ratio(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def best_face_center(detections: Sequence[FaceDetection]) -> tuple[float, float] | None:
    if not detections:
        return None

    total_weight = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    for detection in detections:
        area = max(detection.width, 0.01) * max(detection.height, 0.01)
        weight = max(detection.confidence, 0.01) * area
        total_weight += weight
        weighted_x += _clamp_ratio(detection.center_x) * weight
        weighted_y += _clamp_ratio(detection.center_y) * weight

    if total_weight <= 0:
        return None
    return weighted_x / total_weight, weighted_y / total_weight


def _sample_times(start: float, end: float, sample_count: int) -> list[float]:
    if sample_count <= 0 or end <= start:
        return []
    if sample_count == 1:
        return [(start + end) / 2]
    step = (end - start) / (sample_count - 1)
    return [start + step * index for index in range(sample_count)]


def detect_faces_for_clip(
    video_path: str | Path,
    start: float,
    end: float,
    sample_count: int = 5,
) -> list[FaceDetection]:
    try:
        import cv2
    except ImportError:
        return []

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        return []

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []

    detections: list[FaceDetection] = []
    try:
        for time_seconds in _sample_times(start, end, sample_count):
            capture.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue

            frame_height, frame_width = frame.shape[:2]
            if frame_width <= 0 or frame_height <= 0:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(40, 40),
            )
            for x, y, width, height in faces:
                detections.append(
                    FaceDetection(
                        start=time_seconds,
                        end=time_seconds,
                        center_x=(float(x) + float(width) / 2) / frame_width,
                        center_y=(float(y) + float(height) / 2) / frame_height,
                        width=float(width) / frame_width,
                        height=float(height) / frame_height,
                    )
                )
    finally:
        capture.release()

    return detections
