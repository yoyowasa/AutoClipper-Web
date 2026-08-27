from pathlib import Path
from dataclasses import dataclass
from typing import Literal, Sequence

from app.render.filters import ass_filter
from app.video.face_detect import FaceDetection, best_face_center
from app.video.person_detect import PersonDetection
from app.video.speaker_detect import SpeakerDetection
from app.video.subject_detect import SubjectDetection


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920

CropLayout = Literal["auto", "face_tracking_crop", "center_crop", "blur_background"]
CropStrategy = Literal[
    "face_tracking_crop",
    "speaker_tracking_crop",
    "person_tracking_crop",
    "subject_tracking_crop",
    "center_crop",
    "blur_background",
]


@dataclass(frozen=True)
class CropPlan:
    strategy_order: tuple[CropStrategy, ...]
    face_center: tuple[float, float] | None = None
    speaker_center: tuple[float, float] | None = None
    person_center: tuple[float, float] | None = None
    subject_center: tuple[float, float] | None = None
    signal_source: str = "none"
    confidence: float = 0.0
    fallback_reason: str | None = None
    crop_x: int | None = None
    crop_y: int | None = None
    detection_count: int = 0
    sampled_frame_count: int = 0
    subject_x: float | None = None
    stability_score: float | None = None
    person_detection_count: int = 0
    person_detection_confidence: float | None = None
    person_box: tuple[float, float, float, float] | None = None
    speaker_window_count: int = 0
    speaker_region_confidence: float | None = None
    speaker_region_box: tuple[float, float, float, float] | None = None


FACE_SAFE_MARGIN_X = 72
FACE_SAFE_MARGIN_TOP = 96
FACE_SAFE_MARGIN_BOTTOM = 360
FACE_TARGET_Y = 0.42
MIN_FACE_AREA = 0.002
SUBJECT_MIN_CONFIDENCE = 0.66
SUBJECT_MIN_STABILITY = 0.55
SUBJECT_CENTER_DEADBAND = 0.08
SUBJECT_CENTER_MIN_CONFIDENCE = 0.82
PERSON_SAFE_MARGIN_X = 96
PERSON_SAFE_MARGIN_TOP = 96
PERSON_SAFE_MARGIN_BOTTOM = 260
PERSON_MIN_CONFIDENCE = 0.68
PERSON_MIN_STABILITY = 0.58
PERSON_MIN_HEIGHT = 0.22
SPEAKER_SAFE_MARGIN_X = 96
SPEAKER_SAFE_MARGIN_TOP = 120
SPEAKER_SAFE_MARGIN_BOTTOM = 340
SPEAKER_MIN_CONFIDENCE = 0.72
SPEAKER_MIN_STABILITY = 0.68
SPEAKER_MIN_HEIGHT = 0.11


def _destructive_center_crop_risk(
    source_width: int | None,
    source_height: int | None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> bool:
    if source_width is None or source_height is None or source_width <= 0 or source_height <= 0:
        return True
    if target_width <= 0 or target_height <= 0:
        return True

    source_aspect_product = source_width * target_height
    target_aspect_product = target_width * source_height
    if (target_width, target_height) == (SHORT_WIDTH, SHORT_HEIGHT):
        return source_aspect_product > target_aspect_product
    return source_aspect_product != target_aspect_product


def _no_subject_signal_plan(
    fallback_reason: str,
    source_width: int | None,
    source_height: int | None,
    detection_count: int = 0,
    confidence: float = 0.0,
    sampled_frame_count: int = 0,
    subject_x: float | None = None,
    stability_score: float | None = None,
    person_detection_count: int = 0,
    person_detection_confidence: float | None = None,
    person_box: tuple[float, float, float, float] | None = None,
    speaker_window_count: int = 0,
    speaker_region_confidence: float | None = None,
    speaker_region_box: tuple[float, float, float, float] | None = None,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan:
    if _destructive_center_crop_risk(
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    ):
        return CropPlan(
            strategy_order=("blur_background", "center_crop"),
            signal_source="full_frame_fallback",
            confidence=confidence,
            fallback_reason=fallback_reason,
            detection_count=detection_count,
            sampled_frame_count=sampled_frame_count,
            subject_x=subject_x,
            stability_score=stability_score,
            person_detection_count=person_detection_count,
            person_detection_confidence=person_detection_confidence,
            person_box=person_box,
            speaker_window_count=speaker_window_count,
            speaker_region_confidence=speaker_region_confidence,
            speaker_region_box=speaker_region_box,
        )
    return CropPlan(
        strategy_order=("center_crop", "blur_background"),
        signal_source="center_fallback",
        confidence=confidence,
        fallback_reason=fallback_reason,
        detection_count=detection_count,
        sampled_frame_count=sampled_frame_count,
        subject_x=subject_x,
        stability_score=stability_score,
        person_detection_count=person_detection_count,
        person_detection_confidence=person_detection_confidence,
        person_box=person_box,
        speaker_window_count=speaker_window_count,
        speaker_region_confidence=speaker_region_confidence,
        speaker_region_box=speaker_region_box,
    )


def _append_subtitles(video_filter: str, subtitle_path: str | Path | None) -> str:
    if subtitle_path is None:
        return video_filter
    return f"{video_filter},{ass_filter(subtitle_path)}"


def _framing_scale(value: int, zoom: float) -> int:
    if not 1.0 <= zoom <= 1.6:
        raise ValueError("framing zoom must be between 1.0 and 1.6")
    scaled = max(2, round(value * zoom))
    return scaled if scaled % 2 == 0 else scaled + 1


def _framing_center(value: float, offset: float) -> float:
    if not -100 <= offset <= 100:
        raise ValueError("framing offset must be between -100 and 100")
    return min(max(value + offset / 200, 0.0), 1.0)


def build_center_crop_filter(
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    scale_width = _framing_scale(target_width, framing_zoom)
    scale_height = _framing_scale(target_height, framing_zoom)
    if framing_offset_x == 0 and framing_offset_y == 0:
        crop = f"crop={target_width}:{target_height}"
    else:
        x_ratio = 0.5 + framing_offset_x / 200
        y_ratio = 0.5 + framing_offset_y / 200
        crop = (
            f"crop={target_width}:{target_height}:"
            f"(iw-ow)*{x_ratio:.4f}:(ih-oh)*{y_ratio:.4f}"
        )
    return _append_subtitles(
        (
            f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
            f"{crop}"
        ),
        subtitle_path,
    )


def _scaled_dimensions(
    source_width: int,
    source_height: int,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> tuple[int, int]:
    source_aspect = source_width / source_height
    target_aspect = target_width / target_height
    if source_aspect > target_aspect:
        return round(source_width * (target_height / source_height)), target_height
    return target_width, round(source_height * (target_width / source_width))


def resolve_tracking_crop_geometry(
    source_width: int,
    source_height: int,
    center: tuple[float, float],
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> tuple[int, int, int, int]:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")

    scale_width = _framing_scale(target_width, framing_zoom)
    scale_height = _framing_scale(target_height, framing_zoom)
    scaled_width, scaled_height = _scaled_dimensions(
        source_width,
        source_height,
        target_width=scale_width,
        target_height=scale_height,
    )
    center_x, center_y = center
    center_x = _framing_center(center_x, framing_offset_x)
    center_y = _framing_center(center_y, framing_offset_y)
    crop_x = round(scaled_width * center_x - target_width / 2)
    crop_y = round(scaled_height * center_y - target_height / 2)
    crop_x = min(max(crop_x, 0), max(0, scaled_width - target_width))
    crop_y = min(max(crop_y, 0), max(0, scaled_height - target_height))
    return scale_width, scale_height, crop_x, crop_y


def _clamp_int(value: float | int, minimum: int, maximum: int) -> int:
    return min(max(round(float(value)), minimum), maximum)


def _dominant_face_area(detections: Sequence[FaceDetection]) -> float:
    return max((max(face.width, 0.0) * max(face.height, 0.0) for face in detections), default=0.0)


def _face_bounds_scaled(detections: Sequence[FaceDetection], scaled_width: int, scaled_height: int) -> tuple[float, ...]:
    left = min((face.center_x - face.width / 2) * scaled_width for face in detections)
    right = max((face.center_x + face.width / 2) * scaled_width for face in detections)
    top = min((face.center_y - face.height / 2) * scaled_height for face in detections)
    bottom = max((face.center_y + face.height / 2) * scaled_height for face in detections)
    return left, right, top, bottom


def _face_group_fits_short_crop(
    bounds: tuple[float, ...],
    scaled_width: int,
    scaled_height: int,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> bool:
    left, right, top, bottom = bounds
    group_width = right - left + FACE_SAFE_MARGIN_X * 2
    group_height = bottom - top + FACE_SAFE_MARGIN_TOP + FACE_SAFE_MARGIN_BOTTOM
    return group_width <= min(target_width, scaled_width) and group_height <= min(target_height, scaled_height)


def _plan_face_tracking_crop(
    detections: Sequence[FaceDetection],
    source_width: int,
    source_height: int,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan:
    scaled_width, scaled_height = _scaled_dimensions(
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    )
    weighted_center = best_face_center(detections)
    if weighted_center is None:
        return _no_subject_signal_plan(
            "no_face_center",
            source_width,
            source_height,
            detection_count=len(detections),
            target_width=target_width,
            target_height=target_height,
        )

    dominant_area = _dominant_face_area(detections)
    if dominant_area < MIN_FACE_AREA:
        return _no_subject_signal_plan(
            "weak_face_signal",
            source_width,
            source_height,
            confidence=dominant_area / MIN_FACE_AREA,
            detection_count=len(detections),
            target_width=target_width,
            target_height=target_height,
        )

    bounds = _face_bounds_scaled(detections, scaled_width, scaled_height)
    if not _face_group_fits_short_crop(
        bounds,
        scaled_width,
        scaled_height,
        target_width=target_width,
        target_height=target_height,
    ):
        return CropPlan(
            strategy_order=("blur_background", "center_crop"),
            signal_source="face_detection",
            confidence=0.65,
            fallback_reason="face_group_too_wide_for_9x16_crop",
            detection_count=len(detections),
        )

    left, right, top, bottom = bounds
    max_crop_x = max(0, scaled_width - target_width)
    max_crop_y = max(0, scaled_height - target_height)
    center_x, center_y = weighted_center
    crop_x = round(scaled_width * min(max(center_x, 0.0), 1.0) - target_width / 2)
    crop_y = round(scaled_height * min(max(center_y, 0.0), 1.0) - target_height * FACE_TARGET_Y)

    if left - FACE_SAFE_MARGIN_X < crop_x:
        crop_x = round(left - FACE_SAFE_MARGIN_X)
    if right + FACE_SAFE_MARGIN_X > crop_x + target_width:
        crop_x = round(right + FACE_SAFE_MARGIN_X - target_width)
    if top - FACE_SAFE_MARGIN_TOP < crop_y:
        crop_y = round(top - FACE_SAFE_MARGIN_TOP)
    if bottom + FACE_SAFE_MARGIN_BOTTOM > crop_y + target_height:
        crop_y = round(bottom + FACE_SAFE_MARGIN_BOTTOM - target_height)

    crop_x = _clamp_int(crop_x, 0, max_crop_x)
    crop_y = _clamp_int(crop_y, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + target_width / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + target_height / 2) / scaled_height, 0.0), 1.0),
    )
    face_span = max(right - left, bottom - top)
    confidence = min(
        max(
            0.55 + dominant_area * 5 + min(len(detections), 5) * 0.04 - face_span / max(scaled_width, scaled_height),
            0.0,
        ),
        1.0,
    )

    return CropPlan(
        strategy_order=("face_tracking_crop", "center_crop", "blur_background"),
        face_center=planned_center,
        signal_source="face_detection",
        confidence=confidence,
        crop_x=crop_x,
        crop_y=crop_y,
        detection_count=len(detections),
    )


def _plan_subject_tracking_crop(
    subject_signal: SubjectDetection | None,
    source_width: int,
    source_height: int,
    fallback_reason: str,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan | None:
    if subject_signal is None:
        return None
    if source_width <= 0 or source_height <= 0:
        return None
    if subject_signal.confidence < SUBJECT_MIN_CONFIDENCE or subject_signal.stability_score < SUBJECT_MIN_STABILITY:
        return None
    if (
        abs(subject_signal.center_x - 0.5) < SUBJECT_CENTER_DEADBAND
        and subject_signal.confidence < SUBJECT_CENTER_MIN_CONFIDENCE
    ):
        return None

    scaled_width, scaled_height = _scaled_dimensions(
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    )
    max_crop_x = max(0, scaled_width - target_width)
    max_crop_y = max(0, scaled_height - target_height)
    if max_crop_x <= 0 and max_crop_y <= 0:
        return None

    center_x = min(max(subject_signal.center_x, 0.0), 1.0)
    crop_x = _clamp_int(scaled_width * center_x - target_width / 2, 0, max_crop_x)
    crop_y = _clamp_int((scaled_height - target_height) / 2, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + target_width / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + target_height / 2) / scaled_height, 0.0), 1.0),
    )
    return CropPlan(
        strategy_order=("subject_tracking_crop", "blur_background", "center_crop"),
        subject_center=planned_center,
        signal_source=subject_signal.source,
        confidence=subject_signal.confidence,
        fallback_reason=fallback_reason,
        crop_x=crop_x,
        crop_y=crop_y,
        sampled_frame_count=subject_signal.sampled_frames,
        subject_x=center_x,
        stability_score=subject_signal.stability_score,
    )


def _plan_speaker_tracking_crop(
    speaker_signal: SpeakerDetection | None,
    source_width: int,
    source_height: int,
    fallback_reason: str,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan | None:
    if speaker_signal is None:
        return None
    if source_width <= 0 or source_height <= 0:
        return None
    if speaker_signal.ambiguous:
        return None
    if speaker_signal.confidence < SPEAKER_MIN_CONFIDENCE or speaker_signal.stability_score < SPEAKER_MIN_STABILITY:
        return None
    if speaker_signal.height < SPEAKER_MIN_HEIGHT:
        return None

    scaled_width, scaled_height = _scaled_dimensions(
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    )
    max_crop_x = max(0, scaled_width - target_width)
    max_crop_y = max(0, scaled_height - target_height)
    if max_crop_x <= 0 and max_crop_y <= 0:
        return None

    left, top, right, bottom = speaker_signal.box
    left *= scaled_width
    right *= scaled_width
    top *= scaled_height
    bottom *= scaled_height
    region_width = right - left + SPEAKER_SAFE_MARGIN_X * 2
    region_height = bottom - top + SPEAKER_SAFE_MARGIN_TOP + SPEAKER_SAFE_MARGIN_BOTTOM
    if region_width > min(target_width, scaled_width) or region_height > min(target_height, scaled_height):
        return None

    crop_x = round(scaled_width * speaker_signal.center_x - target_width / 2)
    crop_y = round(scaled_height * speaker_signal.center_y - target_height * FACE_TARGET_Y)
    if left - SPEAKER_SAFE_MARGIN_X < crop_x:
        crop_x = round(left - SPEAKER_SAFE_MARGIN_X)
    if right + SPEAKER_SAFE_MARGIN_X > crop_x + target_width:
        crop_x = round(right + SPEAKER_SAFE_MARGIN_X - target_width)
    if top - SPEAKER_SAFE_MARGIN_TOP < crop_y:
        crop_y = round(top - SPEAKER_SAFE_MARGIN_TOP)
    if bottom + SPEAKER_SAFE_MARGIN_BOTTOM > crop_y + target_height:
        crop_y = round(bottom + SPEAKER_SAFE_MARGIN_BOTTOM - target_height)

    crop_x = _clamp_int(crop_x, 0, max_crop_x)
    crop_y = _clamp_int(crop_y, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + target_width / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + target_height / 2) / scaled_height, 0.0), 1.0),
    )
    return CropPlan(
        strategy_order=("speaker_tracking_crop", "blur_background", "center_crop"),
        speaker_center=planned_center,
        signal_source=speaker_signal.source,
        confidence=speaker_signal.confidence,
        fallback_reason=fallback_reason,
        crop_x=crop_x,
        crop_y=crop_y,
        detection_count=speaker_signal.detection_count,
        sampled_frame_count=speaker_signal.window_count,
        stability_score=speaker_signal.stability_score,
        speaker_window_count=speaker_signal.window_count,
        speaker_region_confidence=speaker_signal.confidence,
        speaker_region_box=speaker_signal.box,
    )


def _speaker_fallback_reason(speaker_signal: SpeakerDetection) -> str:
    if speaker_signal.ambiguous:
        return "ambiguous_speaker_signal"
    return "weak_speaker_signal"


def _plan_person_tracking_crop(
    person_signal: PersonDetection | None,
    source_width: int,
    source_height: int,
    fallback_reason: str,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan | None:
    if person_signal is None:
        return None
    if source_width <= 0 or source_height <= 0:
        return None
    if person_signal.ambiguous:
        return None
    if person_signal.confidence < PERSON_MIN_CONFIDENCE or person_signal.stability_score < PERSON_MIN_STABILITY:
        return None
    if person_signal.height < PERSON_MIN_HEIGHT:
        return None

    scaled_width, scaled_height = _scaled_dimensions(
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    )
    max_crop_x = max(0, scaled_width - target_width)
    max_crop_y = max(0, scaled_height - target_height)
    if max_crop_x <= 0 and max_crop_y <= 0:
        return None

    left, top, right, bottom = person_signal.box
    left *= scaled_width
    right *= scaled_width
    top *= scaled_height
    bottom *= scaled_height
    person_width = right - left + PERSON_SAFE_MARGIN_X * 2
    person_height = bottom - top + PERSON_SAFE_MARGIN_TOP + PERSON_SAFE_MARGIN_BOTTOM
    if person_width > min(target_width, scaled_width) or person_height > min(target_height, scaled_height):
        return None

    crop_x = round(scaled_width * person_signal.center_x - target_width / 2)
    crop_y = round(scaled_height * person_signal.center_y - target_height / 2)
    if left - PERSON_SAFE_MARGIN_X < crop_x:
        crop_x = round(left - PERSON_SAFE_MARGIN_X)
    if right + PERSON_SAFE_MARGIN_X > crop_x + target_width:
        crop_x = round(right + PERSON_SAFE_MARGIN_X - target_width)
    if top - PERSON_SAFE_MARGIN_TOP < crop_y:
        crop_y = round(top - PERSON_SAFE_MARGIN_TOP)
    if bottom + PERSON_SAFE_MARGIN_BOTTOM > crop_y + target_height:
        crop_y = round(bottom + PERSON_SAFE_MARGIN_BOTTOM - target_height)

    crop_x = _clamp_int(crop_x, 0, max_crop_x)
    crop_y = _clamp_int(crop_y, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + target_width / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + target_height / 2) / scaled_height, 0.0), 1.0),
    )
    return CropPlan(
        strategy_order=("person_tracking_crop", "blur_background", "center_crop"),
        person_center=planned_center,
        signal_source=person_signal.source,
        confidence=person_signal.confidence,
        fallback_reason=fallback_reason,
        crop_x=crop_x,
        crop_y=crop_y,
        sampled_frame_count=person_signal.sampled_frames,
        stability_score=person_signal.stability_score,
        person_detection_count=person_signal.detection_count,
        person_detection_confidence=person_signal.confidence,
        person_box=person_signal.box,
    )


def _person_fallback_reason(person_signal: PersonDetection) -> str:
    if person_signal.ambiguous:
        return "ambiguous_person_signal"
    return "weak_person_signal"


def _subject_fallback_reason(subject_signal: SubjectDetection) -> str:
    if (
        abs(subject_signal.center_x - 0.5) < SUBJECT_CENTER_DEADBAND
        and subject_signal.confidence < SUBJECT_CENTER_MIN_CONFIDENCE
    ):
        return "ambiguous_subject_signal"
    return "weak_subject_signal"


def plan_short_crop(
    layout: CropLayout,
    detections: Sequence[FaceDetection] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    speaker_signal: SpeakerDetection | None = None,
    person_signal: PersonDetection | None = None,
    subject_signal: SubjectDetection | None = None,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
) -> CropPlan:
    if layout == "blur_background":
        return CropPlan(strategy_order=("blur_background",), signal_source="forced_layout", confidence=1.0)
    if layout == "center_crop":
        return CropPlan(strategy_order=("center_crop", "blur_background"), signal_source="forced_layout", confidence=1.0)
    if source_width is None or source_height is None or source_width <= 0 or source_height <= 0:
        return _no_subject_signal_plan(
            "missing_source_dimensions",
            source_width,
            source_height,
            detection_count=len(detections or []),
            target_width=target_width,
            target_height=target_height,
        )
    if not detections:
        if layout == "auto":
            speaker_plan = _plan_speaker_tracking_crop(
                speaker_signal,
                source_width,
                source_height,
                fallback_reason="no_face_speaker_signal",
                target_width=target_width,
                target_height=target_height,
            )
            if speaker_plan is not None:
                return speaker_plan
            person_plan = _plan_person_tracking_crop(
                person_signal,
                source_width,
                source_height,
                fallback_reason="no_face_person_signal",
                target_width=target_width,
                target_height=target_height,
            )
            if person_plan is not None:
                return person_plan
            subject_plan = _plan_subject_tracking_crop(
                subject_signal,
                source_width,
                source_height,
                fallback_reason="no_face_subject_signal",
                target_width=target_width,
                target_height=target_height,
            )
            if subject_plan is not None:
                return subject_plan
            if person_signal is not None:
                return _no_subject_signal_plan(
                    _person_fallback_reason(person_signal),
                    source_width,
                    source_height,
                    confidence=person_signal.confidence,
                    sampled_frame_count=person_signal.sampled_frames,
                    stability_score=person_signal.stability_score,
                    person_detection_count=person_signal.detection_count,
                    person_detection_confidence=person_signal.confidence,
                    person_box=person_signal.box,
                    target_width=target_width,
                    target_height=target_height,
                )
            if speaker_signal is not None:
                return _no_subject_signal_plan(
                    _speaker_fallback_reason(speaker_signal),
                    source_width,
                    source_height,
                    confidence=speaker_signal.confidence,
                    detection_count=speaker_signal.detection_count,
                    sampled_frame_count=speaker_signal.window_count,
                    stability_score=speaker_signal.stability_score,
                    speaker_window_count=speaker_signal.window_count,
                    speaker_region_confidence=speaker_signal.confidence,
                    speaker_region_box=speaker_signal.box,
                    target_width=target_width,
                    target_height=target_height,
                )
            if subject_signal is not None:
                return _no_subject_signal_plan(
                    _subject_fallback_reason(subject_signal),
                    source_width,
                    source_height,
                    confidence=subject_signal.confidence,
                    sampled_frame_count=subject_signal.sampled_frames,
                    subject_x=subject_signal.center_x,
                    stability_score=subject_signal.stability_score,
                    target_width=target_width,
                    target_height=target_height,
                )
        return _no_subject_signal_plan(
            "no_face_detections",
            source_width,
            source_height,
            target_width=target_width,
            target_height=target_height,
        )

    face_plan = _plan_face_tracking_crop(
        detections,
        source_width,
        source_height,
        target_width=target_width,
        target_height=target_height,
    )
    if layout == "auto" and face_plan.fallback_reason == "face_group_too_wide_for_9x16_crop":
        speaker_plan = _plan_speaker_tracking_crop(
            speaker_signal,
            source_width,
            source_height,
            fallback_reason="wide_face_group_speaker_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if speaker_plan is not None:
            return speaker_plan
        person_plan = _plan_person_tracking_crop(
            person_signal,
            source_width,
            source_height,
            fallback_reason="wide_face_group_person_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if person_plan is not None:
            return person_plan
        subject_plan = _plan_subject_tracking_crop(
            subject_signal,
            source_width,
            source_height,
            fallback_reason="wide_face_group_subject_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if subject_plan is not None:
            return subject_plan
        if person_signal is not None:
            return _no_subject_signal_plan(
                _person_fallback_reason(person_signal),
                source_width,
                source_height,
                confidence=person_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=person_signal.sampled_frames,
                stability_score=person_signal.stability_score,
                person_detection_count=person_signal.detection_count,
                person_detection_confidence=person_signal.confidence,
                person_box=person_signal.box,
                target_width=target_width,
                target_height=target_height,
            )
        if speaker_signal is not None:
            return _no_subject_signal_plan(
                _speaker_fallback_reason(speaker_signal),
                source_width,
                source_height,
                confidence=speaker_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=speaker_signal.window_count,
                stability_score=speaker_signal.stability_score,
                speaker_window_count=speaker_signal.window_count,
                speaker_region_confidence=speaker_signal.confidence,
                speaker_region_box=speaker_signal.box,
                target_width=target_width,
                target_height=target_height,
            )
        if subject_signal is not None:
            return _no_subject_signal_plan(
                _subject_fallback_reason(subject_signal),
                source_width,
                source_height,
                confidence=subject_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=subject_signal.sampled_frames,
                subject_x=subject_signal.center_x,
                stability_score=subject_signal.stability_score,
                target_width=target_width,
                target_height=target_height,
            )
    if layout == "auto" and face_plan.fallback_reason == "weak_face_signal":
        speaker_plan = _plan_speaker_tracking_crop(
            speaker_signal,
            source_width,
            source_height,
            fallback_reason="weak_face_speaker_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if speaker_plan is not None:
            return speaker_plan
        person_plan = _plan_person_tracking_crop(
            person_signal,
            source_width,
            source_height,
            fallback_reason="weak_face_person_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if person_plan is not None:
            return person_plan
        subject_plan = _plan_subject_tracking_crop(
            subject_signal,
            source_width,
            source_height,
            fallback_reason="weak_face_subject_signal",
            target_width=target_width,
            target_height=target_height,
        )
        if subject_plan is not None:
            return subject_plan
        if person_signal is not None:
            return _no_subject_signal_plan(
                _person_fallback_reason(person_signal),
                source_width,
                source_height,
                confidence=person_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=person_signal.sampled_frames,
                stability_score=person_signal.stability_score,
                person_detection_count=person_signal.detection_count,
                person_detection_confidence=person_signal.confidence,
                person_box=person_signal.box,
                target_width=target_width,
                target_height=target_height,
            )
        if speaker_signal is not None:
            return _no_subject_signal_plan(
                _speaker_fallback_reason(speaker_signal),
                source_width,
                source_height,
                confidence=speaker_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=speaker_signal.window_count,
                stability_score=speaker_signal.stability_score,
                speaker_window_count=speaker_signal.window_count,
                speaker_region_confidence=speaker_signal.confidence,
                speaker_region_box=speaker_signal.box,
                target_width=target_width,
                target_height=target_height,
            )
        if subject_signal is not None:
            return _no_subject_signal_plan(
                _subject_fallback_reason(subject_signal),
                source_width,
                source_height,
                confidence=subject_signal.confidence,
                detection_count=len(detections),
                sampled_frame_count=subject_signal.sampled_frames,
                subject_x=subject_signal.center_x,
                stability_score=subject_signal.stability_score,
                target_width=target_width,
                target_height=target_height,
            )
    if (
        layout == "face_tracking_crop"
        and face_plan.strategy_order[0] == "blur_background"
        and face_plan.fallback_reason == "face_group_too_wide_for_9x16_crop"
    ):
        return CropPlan(
            strategy_order=("face_tracking_crop", "center_crop", "blur_background"),
            face_center=best_face_center(detections),
            signal_source="face_detection",
            confidence=face_plan.confidence,
            fallback_reason="forced_face_tracking_despite_wide_face_group",
            detection_count=len(detections),
        )
    return face_plan


def build_face_tracking_crop_filter(
    source_width: int,
    source_height: int,
    face_center: tuple[float, float],
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    scale_width, scale_height, crop_x, crop_y = resolve_tracking_crop_geometry(
        source_width,
        source_height,
        face_center,
        target_width=target_width,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )

    return _append_subtitles(
        (
            f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_subject_tracking_crop_filter(
    source_width: int,
    source_height: int,
    subject_center: tuple[float, float],
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    scale_width, scale_height, crop_x, crop_y = resolve_tracking_crop_geometry(
        source_width,
        source_height,
        subject_center,
        target_width=target_width,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )

    return _append_subtitles(
        (
            f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_person_tracking_crop_filter(
    source_width: int,
    source_height: int,
    person_center: tuple[float, float],
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    scale_width, scale_height, crop_x, crop_y = resolve_tracking_crop_geometry(
        source_width,
        source_height,
        person_center,
        target_width=target_width,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )

    return _append_subtitles(
        (
            f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_speaker_tracking_crop_filter(
    source_width: int,
    source_height: int,
    speaker_center: tuple[float, float],
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    scale_width, scale_height, crop_x, crop_y = resolve_tracking_crop_geometry(
        source_width,
        source_height,
        speaker_center,
        target_width=target_width,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )

    return _append_subtitles(
        (
            f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_blur_background_filter(
    subtitle_path: str | Path | None = None,
    *,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    foreground_width = _framing_scale(target_width, framing_zoom)
    foreground_height = _framing_scale(target_height, framing_zoom)
    overlay_x = f"(W-w)/2-(w-W)*{framing_offset_x / 200:.4f}"
    overlay_y = f"(H-h)/2-(h-H)*{framing_offset_y / 200:.4f}"
    return _append_subtitles(
        (
            "split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height},gblur=sigma=24[bg];"
            f"[fgsrc]scale={foreground_width}:{foreground_height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay={overlay_x}:{overlay_y}"
        ),
        subtitle_path,
    )


def strategy_order(
    layout: CropLayout,
    detections: Sequence[FaceDetection] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    speaker_signal: SpeakerDetection | None = None,
    person_signal: PersonDetection | None = None,
    subject_signal: SubjectDetection | None = None,
) -> list[CropStrategy]:
    if layout == "blur_background":
        return ["blur_background"]
    if layout == "center_crop":
        return ["center_crop", "blur_background"]
    return list(
        plan_short_crop(
            layout,
            detections=detections,
            source_width=source_width,
            source_height=source_height,
            speaker_signal=speaker_signal,
            person_signal=person_signal,
            subject_signal=subject_signal,
        ).strategy_order
    )


def build_crop_filter(
    strategy: CropStrategy,
    subtitle_path: str | Path | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    face_center: tuple[float, float] | None = None,
    speaker_center: tuple[float, float] | None = None,
    person_center: tuple[float, float] | None = None,
    subject_center: tuple[float, float] | None = None,
    target_width: int = SHORT_WIDTH,
    target_height: int = SHORT_HEIGHT,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    if strategy == "center_crop":
        return build_center_crop_filter(
            subtitle_path,
            target_width=target_width,
            target_height=target_height,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
    if strategy == "blur_background":
        return build_blur_background_filter(
            subtitle_path,
            target_width=target_width,
            target_height=target_height,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
    if strategy == "speaker_tracking_crop":
        if source_width is None or source_height is None or speaker_center is None:
            raise ValueError("speaker_tracking_crop requires source dimensions and speaker center")
        return build_speaker_tracking_crop_filter(
            source_width,
            source_height,
            speaker_center,
            subtitle_path=subtitle_path,
            target_width=target_width,
            target_height=target_height,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
    if strategy == "person_tracking_crop":
        if source_width is None or source_height is None or person_center is None:
            raise ValueError("person_tracking_crop requires source dimensions and person center")
        return build_person_tracking_crop_filter(
            source_width,
            source_height,
            person_center,
            subtitle_path=subtitle_path,
            target_width=target_width,
            target_height=target_height,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
    if strategy == "subject_tracking_crop":
        if source_width is None or source_height is None or subject_center is None:
            raise ValueError("subject_tracking_crop requires source dimensions and subject center")
        return build_subject_tracking_crop_filter(
            source_width,
            source_height,
            subject_center,
            subtitle_path=subtitle_path,
            target_width=target_width,
            target_height=target_height,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
    if source_width is None or source_height is None or face_center is None:
        raise ValueError("face_tracking_crop requires source dimensions and face center")
    return build_face_tracking_crop_filter(
        source_width,
        source_height,
        face_center,
        subtitle_path=subtitle_path,
        target_width=target_width,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )
