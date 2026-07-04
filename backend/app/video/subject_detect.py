from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class SubjectDetection:
    center_x: float
    confidence: float
    stability_score: float
    sampled_frames: int
    source: str = "motion_edge_saliency"


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


def _gray_frame(frame: Any, cv2: Any, np: Any, max_width: int) -> Any | None:
    if frame is None:
        return None
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    height, width = gray.shape[:2]
    if width <= 0 or height <= 0:
        return None
    if width > max_width:
        scale = max_width / width
        gray = cv2.resize(gray, (max_width, max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
    return np.asarray(gray)


def _smooth(values: Any, np: Any, window: int) -> Any:
    if window <= 1:
        return values
    kernel = np.ones(window, dtype="float32") / window
    return np.convolve(values, kernel, mode="same")


def _energy_center(gray_frames: Sequence[Any], cv2: Any, np: Any) -> tuple[float, float, float] | None:
    energies: list[Any] = []
    centers: list[float] = []
    previous: Any | None = None

    for gray in gray_frames:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 48, 144).astype("float32") / 255.0
        if previous is None:
            motion = np.zeros_like(edges, dtype="float32")
        else:
            diff = cv2.absdiff(blurred, previous)
            motion = np.clip(diff.astype("float32") / 48.0, 0.0, 1.0)
        previous = blurred

        height, width = edges.shape[:2]
        if width <= 0 or height <= 0:
            continue
        vertical_weight = np.ones((height, 1), dtype="float32")
        vertical_weight[: max(1, round(height * 0.08)), :] *= 0.35
        vertical_weight[round(height * 0.76) :, :] *= 0.45
        energy = (edges * 0.65 + motion * 1.35) * vertical_weight
        column_energy = energy.sum(axis=0)
        if float(column_energy.sum()) <= 1e-6:
            continue
        smoothed = _smooth(column_energy, np, max(3, width // 28))
        total = float(smoothed.sum())
        xs = np.arange(width, dtype="float32")
        center_x = float((smoothed * xs).sum() / total) / max(width - 1, 1)
        energies.append(smoothed)
        centers.append(_clamp_ratio(center_x))

    if not energies or not centers:
        return None

    combined = np.mean(np.stack(energies), axis=0)
    total_energy = float(combined.sum())
    if total_energy <= 1e-6:
        return None

    width = int(combined.shape[0])
    crop_width = min(width, max(1, round(width * 9 / 16)))
    window = _smooth(combined, np, max(3, crop_width // 4))
    peak_index = int(np.argmax(window))
    peak_value = float(window[peak_index])
    sorted_values = np.sort(window)
    second_peak = float(sorted_values[max(0, len(sorted_values) - crop_width // 2 - 1)])
    dominance = (peak_value - second_peak) / max(peak_value, 1e-6)
    concentration = peak_value / max(float(window.sum()), 1e-6) * crop_width
    stability = 1.0 - min(float(np.std(np.asarray(centers, dtype="float32"))) / 0.16, 1.0)
    center_x = float(np.mean(np.asarray(centers, dtype="float32")))
    confidence = min(max(0.18 + dominance * 0.38 + concentration * 0.24 + stability * 0.20, 0.0), 1.0)
    return _clamp_ratio(center_x), _clamp_ratio(confidence), _clamp_ratio(stability)


def estimate_subject_from_frames(
    frames: Sequence[Any],
    *,
    max_width: int = 320,
) -> SubjectDetection | None:
    cv2 = _load_cv2()
    np = _load_numpy()
    if cv2 is None or np is None:
        return None

    gray_frames = [
        gray
        for frame in frames
        if (gray := _gray_frame(frame, cv2=cv2, np=np, max_width=max_width)) is not None
    ]
    if len(gray_frames) < 2:
        return None

    estimated = _energy_center(gray_frames, cv2=cv2, np=np)
    if estimated is None:
        return None
    center_x, confidence, stability_score = estimated
    return SubjectDetection(
        center_x=center_x,
        confidence=confidence,
        stability_score=stability_score,
        sampled_frames=len(gray_frames),
    )


def detect_subject_for_clip(
    video_path: str | Path,
    start: float,
    end: float,
    sample_count: int = 5,
    max_width: int = 320,
) -> SubjectDetection | None:
    cv2 = _load_cv2()
    if cv2 is None:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    frames: list[Any] = []
    try:
        for time_seconds in _sample_times(start, end, sample_count):
            capture.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
            ok, frame = capture.read()
            if ok and frame is not None:
                frames.append(frame)
    finally:
        capture.release()

    return estimate_subject_from_frames(frames, max_width=max_width)
