from pathlib import Path
from typing import Literal, Sequence

from app.render.filters import ass_filter
from app.video.face_detect import FaceDetection, best_face_center


SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920

CropLayout = Literal["auto", "face_tracking_crop", "center_crop", "blur_background"]
CropStrategy = Literal["face_tracking_crop", "center_crop", "blur_background"]


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
) -> list[CropStrategy]:
    can_face_track = (
        bool(detections)
        and source_width is not None
        and source_height is not None
        and source_width > 0
        and source_height > 0
        and best_face_center(detections) is not None
    )
    if layout == "blur_background":
        return ["blur_background"]
    if layout == "center_crop":
        return ["center_crop", "blur_background"]
    if layout == "face_tracking_crop":
        return ["face_tracking_crop", "center_crop", "blur_background"] if can_face_track else [
            "center_crop",
            "blur_background",
        ]
    if can_face_track:
        return ["face_tracking_crop", "center_crop", "blur_background"]
    return ["center_crop", "blur_background"]


def build_crop_filter(
    strategy: CropStrategy,
    subtitle_path: str | Path | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
    face_center: tuple[float, float] | None = None,
) -> str:
    if strategy == "center_crop":
        return build_center_crop_filter(subtitle_path)
    if strategy == "blur_background":
        return build_blur_background_filter(subtitle_path)
    if source_width is None or source_height is None or face_center is None:
        raise ValueError("face_tracking_crop requires source dimensions and face center")
    return build_face_tracking_crop_filter(
        source_width,
        source_height,
        face_center,
        subtitle_path=subtitle_path,
    )
