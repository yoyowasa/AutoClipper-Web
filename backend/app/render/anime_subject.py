"""Local anime-face detection and a single-character matte for thumbnails."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.config import get_settings


ANIME_FACE_CASCADE_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets/thumbnail_templates/raden_normal_v1/lbpcascade_animeface.xml"
)
ANIME_MATTE_FILENAME = "isnet-anime.onnx"
Face = tuple[float, float, float, float]


@lru_cache(maxsize=1)
def _anime_cascade():
    import cv2

    detector = cv2.CascadeClassifier(str(ANIME_FACE_CASCADE_PATH))
    return None if detector.empty() else detector


def detect_anime_face(image: Image.Image) -> Face | None:
    """Pick the largest visible anime face, including one at the frame center."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    detector = _anime_cascade()
    if detector is None:
        return None
    source = np.asarray(image.convert("RGB"))
    height, width = source.shape[:2]
    scale = min(1.0, 960 / width)
    if scale < 1:
        source = cv2.resize(source, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    boxes = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
    faces = [
        ((x + box_width / 2) / gray.shape[1], (y + box_height / 2) / gray.shape[0],
         box_width / gray.shape[1], box_height / gray.shape[0])
        for x, y, box_width, box_height in boxes
    ]
    usable = [face for face in faces if 0.08 <= face[1] <= 0.85 and face[2] >= 0.035 and face[3] >= 0.06]
    return max(usable, key=lambda face: (face[2] * face[3], -abs(face[0] - 0.5))) if usable else None


def anime_matte_path() -> Path:
    return Path(get_settings().storage_root).resolve() / "models" / ANIME_MATTE_FILENAME


@lru_cache(maxsize=2)
def _matte_session(model_path: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    return ort.InferenceSession(model_path, sess_options=options, providers=["CPUExecutionProvider"])


def anime_character_mask(image: Image.Image, face: Face, *, model_path: Path | None = None) -> Image.Image | None:
    """Matte the connected character containing the detected face.

    The model is installed separately in storage/models, so it is never checked
    into Git. Missing weights leave the existing frame crop available.
    """
    path = model_path or anime_matte_path()
    if not path.is_file():
        return None
    try:
        import cv2
        import numpy as np
        session = _matte_session(str(path))
    except (ImportError, OSError):
        return None

    sample = np.asarray(image.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    sample -= np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
    tensor = sample.transpose(2, 0, 1)[None]
    prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    spread = float(prediction.max() - prediction.min())
    if spread < 1e-6:
        return None
    normalized = (prediction - prediction.min()) / spread
    mask = Image.fromarray((normalized * 255).astype("uint8")).resize(image.size, Image.Resampling.LANCZOS)
    alpha = np.asarray(mask)
    binary = (alpha >= 64).astype("uint8")
    count, labels, stats, _centers = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return None
    face_x, face_y, face_width, face_height = face
    left = max(0, round((face_x - face_width / 2) * image.width))
    top = max(0, round((face_y - face_height / 2) * image.height))
    right = min(image.width, round((face_x + face_width / 2) * image.width))
    bottom = min(image.height, round((face_y + face_height / 2) * image.height))
    face_labels = labels[top:bottom, left:right]
    overlaps = np.bincount(face_labels.ravel(), minlength=count)
    overlaps[0] = 0
    chosen = int(np.argmax(overlaps))
    if overlaps[chosen] < max(20, face_labels.size * 0.02) or stats[chosen, cv2.CC_STAT_AREA] < image.width * image.height * 0.015:
        return None
    # Preserve soft hair edges immediately adjacent to the selected component.
    component = cv2.dilate((labels == chosen).astype("uint8"), np.ones((5, 5), dtype="uint8"))
    selected = np.where(component != 0, alpha, 0).astype("float32")
    # Video-frame edges can already cut off sleeves or a torso. Soften those
    # source edges instead of exposing a straight rectangle on the template.
    edge = min(45, image.width // 25, image.height // 20)
    if edge > 0:
        if np.count_nonzero(selected[-1]) > image.width * 0.02:
            selected[-edge:] *= np.linspace(1, 0, edge, dtype="float32")[:, None]
        if np.count_nonzero(selected[:, -1]) > image.height * 0.02:
            selected[:, -edge:] *= np.linspace(1, 0, edge, dtype="float32")[None, :]
        if np.count_nonzero(selected[:, 0]) > image.height * 0.02:
            selected[:, :edge] *= np.linspace(0, 1, edge, dtype="float32")[None, :]
    return Image.fromarray(selected.astype("uint8"))
