"""Thumbnail-only fallback for tilted anime faces; keep other detection unchanged."""

import math

from PIL import Image

from app.render.anime_subject import detect_anime_face


THUMBNAIL_FACE_ROTATIONS = (-10, 10, -15, 15, -20, 20)


def detect_thumbnail_face(image, *, detector=detect_anime_face):
    face = detector(image)
    if face is not None:
        return face
    # Bound work to the same 960px scan resolution, also when validating the
    # saved full-resolution still. Rotation is only a detection aid, not output.
    small = image.convert("RGB")
    small.thumbnail((960, 960))
    width, height = small.size
    for degrees in THUMBNAIL_FACE_ROTATIONS:
        face = detector(small.rotate(degrees, resample=Image.Resampling.BICUBIC))
        if face is None:
            continue
        cx, cy, fw, fh = face
        angle = math.radians(degrees)
        dx, dy = (cx - .5) * width, (cy - .5) * height
        cx = .5 + (math.cos(angle) * dx - math.sin(angle) * dy) / width
        cy = .5 + (math.sin(angle) * dx + math.cos(angle) * dy) / height
        if 0 <= cx - fw / 2 < cx + fw / 2 <= 1 and 0 <= cy - fh / 2 < cy + fh / 2 <= 1:
            return cx, cy, fw, fh
    return None
