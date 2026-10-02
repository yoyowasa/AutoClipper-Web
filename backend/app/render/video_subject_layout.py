"""Face-based video composition, measured in original source pixels."""

from dataclasses import dataclass

from PIL import Image


MAX_VIDEO_UPSCALE = 2.0


@dataclass(frozen=True)
class VideoSubjectLayout:
    left: float
    top: float
    crop_width: float
    crop_height: float
    upscale: float
    fits: bool


def video_subject_layout(size, face, frame, *, mode="standard", scale=1.0, offset_x=0, offset_y=0):
    width, height = size
    cx, cy, _fw, fh = face
    # Bust: face center at 30%, lower edge two face heights below the chin.
    crop_height = fh * height / 0.45 if mode == "close" else fh * height * 2.5 / 0.7
    crop_height /= scale
    crop_width = crop_height * frame["width"] / frame["height"]
    upscale = frame["height"] / crop_height
    left = cx * width - crop_width * float(frame.get("face_target_x", 0.5)) - offset_x / upscale
    top = cy * height - crop_height * 0.3 - offset_y / upscale
    fits = (upscale <= MAX_VIDEO_UPSCALE + 1e-9 and top >= 0 and top + crop_height <= height
            and crop_width <= width)
    # Horizontal edge padding is preferable to moving the face away from its target.
    return VideoSubjectLayout(left, top, crop_width, crop_height, upscale, fits)


def place_video_subject(image: Image.Image, face, frame, *, mode="standard", scale=1, offset_x=0, offset_y=0,
                        mask: Image.Image | None = None):
    layout = video_subject_layout(image.size, face, frame, mode=mode, scale=scale, offset_x=offset_x, offset_y=offset_y)
    portrait = image.convert("RGBA")
    if mask is not None:
        portrait.putalpha(mask)
    # Pillow's extent transform permits subpixel crops and clips/pads at the source edge.
    return portrait.transform(
        (frame["width"], frame["height"]), Image.Transform.EXTENT,
        (layout.left, layout.top, layout.left + layout.crop_width, layout.top + layout.crop_height),
        resample=Image.Resampling.BICUBIC,
    )
