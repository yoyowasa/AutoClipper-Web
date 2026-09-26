from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image

from app.render.anime_subject import detect_anime_face
from app.video.face_detect import FaceDetection, detect_faces_for_clip


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
            face = detect_anime_face(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
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
        # A face at the lower edge is usually only the top of a head; it cannot
        # provide a usable isolated character for the thumbnail.
        if not 0.08 <= detection.center_y <= 0.72:
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
    count: int = 6,
) -> list[float]:
    duration = max(0.0, end - start)
    ratios = THUMBNAIL_FRAME_RATIOS if count == 6 else tuple((index + 0.5) / count for index in range(count))
    targets = [start + duration * ratio for ratio in ratios]
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


def thumbnail_face_times(
    video_path: str | Path, *, clip_start: float, clip_end: float,
    minimum_count: int = 6, face_detector: FaceDetector = detect_thumbnail_faces_for_clip,
) -> list[float]:
    """Search the whole clip, then inspect around sparse face detections.

    The first pass is cheap for a continuously visible presenter. If a face
    only appears briefly, a denser full-clip pass prevents early blank scenes
    from becoming the only candidates.
    """
    if clip_end <= clip_start:
        return []
    duration = clip_end - clip_start
    detections = list(face_detector(video_path, clip_start, clip_end, 24))
    times = _usable_face_times(detections, start=clip_start, end=clip_end)
    if not times:
        detections = list(face_detector(video_path, clip_start, clip_end, 48))
        times = _usable_face_times(detections, start=clip_start, end=clip_end)
    if not times:
        dense_count = max(96, min(240, round(duration / 2.5)))
        detections = list(face_detector(video_path, clip_start, clip_end, dense_count))
        times = _usable_face_times(detections, start=clip_start, end=clip_end)
    if not times and face_detector is detect_thumbnail_faces_for_clip:
        # Keep real-person videos supported, but only after the anime search
        # has exhausted the clip. Haar detections must not win early over a
        # character who appears later.
        detections = list(detect_faces_for_clip(video_path, clip_start, clip_end, 48))
        times = _usable_face_times(detections, start=clip_start, end=clip_end)
    if times and len(times) < minimum_count:
        radius = duration / 48
        for second in times[:minimum_count]:
            left = max(clip_start, second - radius)
            right = min(clip_end, second + radius)
            detections.extend(face_detector(video_path, left, right, 7))
        times = _usable_face_times(detections, start=clip_start, end=clip_end)
    return sorted({round(second, 3) for second in times})


def thumbnail_frame_candidates(
    video_path: str | Path, *, clip_start: float, clip_end: float,
    count: int = 8, face_detector: FaceDetector = detect_thumbnail_faces_for_clip,
) -> list[float]:
    times = thumbnail_face_times(
        video_path, clip_start=clip_start, clip_end=clip_end,
        minimum_count=count, face_detector=face_detector,
    )
    selected = _candidate_times(times, start=clip_start, end=clip_end, count=count)
    if not selected:
        return []
    # The gallery contract has a fixed count; repeat verified frames rather
    # than add unverified blank frames when a character is only briefly shown.
    return [round(selected[index % len(selected)] - clip_start, 3) for index in range(count)]


def thumbnail_frame_near(
    video_path: str | Path, *, clip_start: float, clip_end: float,
    preferred_seconds: float, face_detector: FaceDetector = detect_thumbnail_faces_for_clip,
) -> float:
    """Keep an AI-selected frame if it has a usable face; otherwise find one."""
    duration = max(0.0, clip_end - clip_start)
    preferred = min(duration, max(0.0, preferred_seconds))
    timestamp = clip_start + preferred
    at_preferred = face_detector(video_path, timestamp, timestamp, 1)
    preferred_faces = [
        face for face in at_preferred
        if 0.18 <= face.center_x <= 0.82
    ]
    if _usable_face_times(preferred_faces, start=timestamp, end=timestamp):
        return round(preferred, 3)
    times = thumbnail_face_times(
        video_path, clip_start=clip_start, clip_end=clip_end,
        minimum_count=1, face_detector=face_detector,
    )
    if not times:
        return round(preferred, 3)
    return round(min(times, key=lambda second: abs(second - timestamp)) - clip_start, 3)


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

    frame_times = _candidate_times(
        thumbnail_face_times(
            video_path, clip_start=start, clip_end=end, face_detector=face_detector,
        ),
        start=start,
        end=end,
    )
    selected = frame_times[max(0, int(variant_index)) % len(frame_times)]
    return round(min(duration, max(0.0, selected - start)), 3)
