from pathlib import Path
from dataclasses import dataclass
from typing import Literal, Sequence

from app.render.filters import ass_filter
from app.video.face_detect import FaceDetection, best_face_center
from app.video.subject_detect import SubjectDetection


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920

CropLayout = Literal["auto", "face_tracking_crop", "center_crop", "blur_background"]
CropStrategy = Literal["face_tracking_crop", "subject_tracking_crop", "center_crop", "blur_background"]


@dataclass(frozen=True)
class CropPlan:
    strategy_order: tuple[CropStrategy, ...]
    face_center: tuple[float, float] | None = None
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


FACE_SAFE_MARGIN_X = 72
FACE_SAFE_MARGIN_TOP = 96
FACE_SAFE_MARGIN_BOTTOM = 360
FACE_TARGET_Y = 0.42
MIN_FACE_AREA = 0.002
SUBJECT_MIN_CONFIDENCE = 0.66
SUBJECT_MIN_STABILITY = 0.55
SUBJECT_CENTER_DEADBAND = 0.08
SUBJECT_CENTER_MIN_CONFIDENCE = 0.82


def _destructive_center_crop_risk(source_width: int | None, source_height: int | None) -> bool:
    if source_width is None or source_height is None or source_width <= 0 or source_height <= 0:
        return True
    return (source_width / source_height) > (SHORT_WIDTH / SHORT_HEIGHT)


def _no_subject_signal_plan(
    fallback_reason: str,
    source_width: int | None,
    source_height: int | None,
    detection_count: int = 0,
    confidence: float = 0.0,
    sampled_frame_count: int = 0,
    subject_x: float | None = None,
    stability_score: float | None = None,
) -> CropPlan:
    if _destructive_center_crop_risk(source_width, source_height):
        return CropPlan(
            strategy_order=("blur_background", "center_crop"),
            signal_source="full_frame_fallback",
            confidence=confidence,
            fallback_reason=fallback_reason,
            detection_count=detection_count,
            sampled_frame_count=sampled_frame_count,
            subject_x=subject_x,
            stability_score=stability_score,
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
    )


def _append_subtitles(video_filter: str, subtitle_path: str | Path | None) -> str:
    if subtitle_path is None:
        return video_filter
    return f"{video_filter},{ass_filter(subtitle_path)}"


def build_center_crop_filter(subtitle_path: str | Path | None = None) -> str:
    return _append_subtitles(
        (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT}"
        ),
        subtitle_path,
    )


def _scaled_dimensions(source_width: int, source_height: int) -> tuple[int, int]:
    source_aspect = source_width / source_height
    target_aspect = SHORT_WIDTH / SHORT_HEIGHT
    if source_aspect > target_aspect:
        return round(source_width * (SHORT_HEIGHT / source_height)), SHORT_HEIGHT
    return SHORT_WIDTH, round(source_height * (SHORT_WIDTH / source_width))


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
) -> bool:
    left, right, top, bottom = bounds
    group_width = right - left + FACE_SAFE_MARGIN_X * 2
    group_height = bottom - top + FACE_SAFE_MARGIN_TOP + FACE_SAFE_MARGIN_BOTTOM
    return group_width <= min(SHORT_WIDTH, scaled_width) and group_height <= min(SHORT_HEIGHT, scaled_height)


def _plan_face_tracking_crop(
    detections: Sequence[FaceDetection],
    source_width: int,
    source_height: int,
) -> CropPlan:
    scaled_width, scaled_height = _scaled_dimensions(source_width, source_height)
    weighted_center = best_face_center(detections)
    if weighted_center is None:
        return _no_subject_signal_plan(
            "no_face_center",
            source_width,
            source_height,
            detection_count=len(detections),
        )

    dominant_area = _dominant_face_area(detections)
    if dominant_area < MIN_FACE_AREA:
        return _no_subject_signal_plan(
            "weak_face_signal",
            source_width,
            source_height,
            confidence=dominant_area / MIN_FACE_AREA,
            detection_count=len(detections),
        )

    bounds = _face_bounds_scaled(detections, scaled_width, scaled_height)
    if not _face_group_fits_short_crop(bounds, scaled_width, scaled_height):
        return CropPlan(
            strategy_order=("blur_background", "center_crop"),
            signal_source="face_detection",
            confidence=0.65,
            fallback_reason="face_group_too_wide_for_9x16_crop",
            detection_count=len(detections),
        )

    left, right, top, bottom = bounds
    max_crop_x = max(0, scaled_width - SHORT_WIDTH)
    max_crop_y = max(0, scaled_height - SHORT_HEIGHT)
    center_x, center_y = weighted_center
    crop_x = round(scaled_width * min(max(center_x, 0.0), 1.0) - SHORT_WIDTH / 2)
    crop_y = round(scaled_height * min(max(center_y, 0.0), 1.0) - SHORT_HEIGHT * FACE_TARGET_Y)

    if left - FACE_SAFE_MARGIN_X < crop_x:
        crop_x = round(left - FACE_SAFE_MARGIN_X)
    if right + FACE_SAFE_MARGIN_X > crop_x + SHORT_WIDTH:
        crop_x = round(right + FACE_SAFE_MARGIN_X - SHORT_WIDTH)
    if top - FACE_SAFE_MARGIN_TOP < crop_y:
        crop_y = round(top - FACE_SAFE_MARGIN_TOP)
    if bottom + FACE_SAFE_MARGIN_BOTTOM > crop_y + SHORT_HEIGHT:
        crop_y = round(bottom + FACE_SAFE_MARGIN_BOTTOM - SHORT_HEIGHT)

    crop_x = _clamp_int(crop_x, 0, max_crop_x)
    crop_y = _clamp_int(crop_y, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + SHORT_WIDTH / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + SHORT_HEIGHT / 2) / scaled_height, 0.0), 1.0),
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

    scaled_width, scaled_height = _scaled_dimensions(source_width, source_height)
    max_crop_x = max(0, scaled_width - SHORT_WIDTH)
    max_crop_y = max(0, scaled_height - SHORT_HEIGHT)
    if max_crop_x <= 0 and max_crop_y <= 0:
        return None

    center_x = min(max(subject_signal.center_x, 0.0), 1.0)
    crop_x = _clamp_int(scaled_width * center_x - SHORT_WIDTH / 2, 0, max_crop_x)
    crop_y = _clamp_int((scaled_height - SHORT_HEIGHT) / 2, 0, max_crop_y)
    planned_center = (
        min(max((crop_x + SHORT_WIDTH / 2) / scaled_width, 0.0), 1.0),
        min(max((crop_y + SHORT_HEIGHT / 2) / scaled_height, 0.0), 1.0),
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
    subject_signal: SubjectDetection | None = None,
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
        )
    if not detections:
        if layout == "auto":
            subject_plan = _plan_subject_tracking_crop(
                subject_signal,
                source_width,
                source_height,
                fallback_reason="no_face_subject_signal",
            )
            if subject_plan is not None:
                return subject_plan
            if subject_signal is not None:
                return _no_subject_signal_plan(
                    _subject_fallback_reason(subject_signal),
                    source_width,
                    source_height,
                    confidence=subject_signal.confidence,
                    sampled_frame_count=subject_signal.sampled_frames,
                    subject_x=subject_signal.center_x,
                    stability_score=subject_signal.stability_score,
                )
        return _no_subject_signal_plan("no_face_detections", source_width, source_height)

    face_plan = _plan_face_tracking_crop(detections, source_width, source_height)
    if layout == "auto" and face_plan.fallback_reason == "weak_face_signal":
        subject_plan = _plan_subject_tracking_crop(
            subject_signal,
            source_width,
            source_height,
            fallback_reason="weak_face_subject_signal",
        )
        if subject_plan is not None:
            return subject_plan
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
) -> str:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")

    scaled_width, scaled_height = _scaled_dimensions(source_width, source_height)
    center_x, center_y = face_center
    crop_x = round(scaled_width * min(max(center_x, 0.0), 1.0) - SHORT_WIDTH / 2)
    crop_y = round(scaled_height * min(max(center_y, 0.0), 1.0) - SHORT_HEIGHT / 2)
    crop_x = min(max(crop_x, 0), max(0, scaled_width - SHORT_WIDTH))
    crop_y = min(max(crop_y, 0), max(0, scaled_height - SHORT_HEIGHT))

    return _append_subtitles(
        (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_subject_tracking_crop_filter(
    source_width: int,
    source_height: int,
    subject_center: tuple[float, float],
    subtitle_path: str | Path | None = None,
) -> str:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")

    scaled_width, scaled_height = _scaled_dimensions(source_width, source_height)
    center_x, center_y = subject_center
    crop_x = round(scaled_width * min(max(center_x, 0.0), 1.0) - SHORT_WIDTH / 2)
    crop_y = round(scaled_height * min(max(center_y, 0.0), 1.0) - SHORT_HEIGHT / 2)
    crop_x = min(max(crop_x, 0), max(0, scaled_width - SHORT_WIDTH))
    crop_y = min(max(crop_y, 0), max(0, scaled_height - SHORT_HEIGHT))

    return _append_subtitles(
        (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT}:{crop_x}:{crop_y}"
        ),
        subtitle_path,
    )


def build_blur_background_filter(subtitle_path: str | Path | None = None) -> str:
    return _append_subtitles(
        (
            "split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},gblur=sigma=24[bg];"
            f"[fgsrc]scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        ),
        subtitle_path,
    )


def strategy_order(
    layout: CropLayout,
    detections: Sequence[FaceDetection] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
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
            subject_signal=subject_signal,
        ).strategy_order
    )


def build_crop_filter(
    strategy: CropStrategy,
    subtitle_path: str | Path | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    face_center: tuple[float, float] | None = None,
    subject_center: tuple[float, float] | None = None,
) -> str:
    if strategy == "center_crop":
        return build_center_crop_filter(subtitle_path)
    if strategy == "blur_background":
        return build_blur_background_filter(subtitle_path)
    if strategy == "subject_tracking_crop":
        if source_width is None or source_height is None or subject_center is None:
            raise ValueError("subject_tracking_crop requires source dimensions and subject center")
        return build_subject_tracking_crop_filter(
            source_width,
            source_height,
            subject_center,
            subtitle_path=subtitle_path,
        )
    if source_width is None or source_height is None or face_center is None:
        raise ValueError("face_tracking_crop requires source dimensions and face center")
    return build_face_tracking_crop_filter(
        source_width,
        source_height,
        face_center,
        subtitle_path=subtitle_path,
    )
