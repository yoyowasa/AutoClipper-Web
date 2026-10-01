"""Sequential low-resolution scan; only shortlisted frames are extracted again."""

from dataclasses import dataclass
import io
from pathlib import Path
import subprocess
from tempfile import TemporaryFile
from typing import Iterator

import cv2
import numpy as np
from PIL import Image

from app.character_asset_rules import validate_character_asset_dimensions
from app.character_assets import ProcessedCharacterAsset, process_character_asset
from app.render.anime_subject import detect_anime_face
from app.render.render_thumbnail import extract_thumbnail_frame
from app.storage.paths import StoragePaths
from app.video.probe import probe_metadata


SCAN_WIDTH = 960
FACE_MIN_HEIGHT = 0.12
TOP_FACE_MARGIN = 0.3
CHEST_FACE_MARGIN = 2.0
MIN_LAPLACIAN_VARIANCE = 80.0
NEAR_SECONDS = 10
HASH_MAX_DISTANCE = 6
MAX_CANDIDATES = 48


@dataclass(frozen=True)
class FrameCandidate:
    second: int
    face: tuple[float, float, float, float]
    score: float
    face_hash: int


def sequential_frames(video: Path) -> Iterator[tuple[int, Image.Image]]:
    metadata = probe_metadata(video)
    if not metadata.width or not metadata.height:
        raise ValueError("動画の画面サイズを読み取れません。")
    height = round(metadata.height * SCAN_WIDTH / metadata.width)
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an", "-sn", "-dn",
        "-vf", f"fps=1:start_time=0:round=up,scale={SCAN_WIDTH}:{height},setsar=1",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ]
    # stderr goes to a file so it cannot fill a pipe and deadlock the scanner.
    with TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        assert process.stdout is not None
        frame_size = SCAN_WIDTH * height * 3
        try:
            second = 0
            while True:
                data = bytearray()
                while len(data) < frame_size:
                    part = process.stdout.read(frame_size - len(data))
                    if not part:
                        break
                    data.extend(part)
                if not data:
                    break
                if len(data) != frame_size:
                    raise RuntimeError("動画の走査中にフレームが途切れました。")
                yield second, Image.frombytes("RGB", (SCAN_WIDTH, height), bytes(data))
                second += 1
            if process.wait() != 0:
                raise RuntimeError("動画の走査に失敗しました。")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def evaluate_frame(image: Image.Image, second: int) -> FrameCandidate | None:
    face = detect_anime_face(image)
    if face is None:
        return None
    cx, cy, w, h = face
    top, bottom = cy - h / 2, cy + h / 2
    if h < FACE_MIN_HEIGHT or top < h * TOP_FACE_MARGIN or 1 - bottom < h * CHEST_FACE_MARGIN:
        return None
    x0, x1 = max(0, int((cx - w / 2) * image.width)), min(image.width, int((cx + w / 2) * image.width))
    y0, y1 = max(0, int(top * image.height)), min(image.height, int(bottom * image.height))
    if x1 <= x0 or y1 <= y0:
        return None
    gray = np.asarray(image.crop((x0, y0, x1, y1)).convert("L"))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharpness < MIN_LAPLACIAN_VARIANCE:
        return None
    # A 64-bit perceptual difference hash, computed only from the face.
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    face_hash = int.from_bytes(np.packbits(bits).tobytes(), "big")
    return FrameCandidate(second, face, h * min(sharpness, 2000), face_hash)


def thin_candidates(candidates: list[FrameCandidate]) -> list[FrameCandidate]:
    selected: list[FrameCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.second)):
        if any(
            abs(candidate.second - previous.second) <= NEAR_SECONDS
            or (candidate.face_hash ^ previous.face_hash).bit_count() <= HASH_MAX_DISTANCE
            for previous in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) == MAX_CANDIDATES:
            break
    return selected


def scan_candidates(video: Path) -> list[FrameCandidate]:
    # Retain lightweight metadata only; never keep decoded video frames in memory.
    pool: list[FrameCandidate] = []
    for second, image in sequential_frames(video):
        candidate = evaluate_frame(image, second)
        if candidate is not None:
            pool.append(candidate)
    return thin_candidates(pool)


def crop_bust(image: Image.Image, face: tuple[float, float, float, float]) -> tuple[Image.Image, tuple[float, float, float, float]]:
    cx, cy, w, h = face
    face_height = h * image.height
    y0 = max(0, round((cy - h / 2) * image.height - TOP_FACE_MARGIN * face_height))
    y1 = min(image.height, round((cy + h / 2) * image.height + CHEST_FACE_MARGIN * face_height))
    crop_height = y1 - y0
    crop_width = round(crop_height * 3 / 4)
    if crop_width > image.width:
        raise ValueError("胸から上を3:4で切り出せません。")
    x0 = max(0, min(image.width - crop_width, round(cx * image.width - crop_width / 2)))
    if (cx - w / 2) * image.width < x0 or (cx + w / 2) * image.width > x0 + crop_width:
        raise ValueError("顔が切り出し範囲からはみ出します。")
    reason = validate_character_asset_dimensions(crop_width, crop_height)
    if reason:
        raise ValueError(reason)
    return image.crop((x0, y0, x0 + crop_width, y1)), (
        (cx * image.width - x0) / crop_width, (cy * image.height - y0) / crop_height,
        w * image.width / crop_width, h * image.height / crop_height,
    )


def extract_candidate(video: Path, candidate: FrameCandidate, temporary: Path, paths: StoragePaths) -> ProcessedCharacterAsset:
    extract_thumbnail_frame(video, temporary, candidate.second)
    with Image.open(temporary) as source:
        # Detect on the original frame as the fps filter may select a neighboring frame.
        face = detect_anime_face(source)
        if face is None:
            raise ValueError("元解像度のフレームで顔を検出できません。")
        cx, cy, _w, h = face
        if h < FACE_MIN_HEIGHT or cy - h / 2 < h * TOP_FACE_MARGIN or 1 - cy - h / 2 < h * CHEST_FACE_MARGIN:
            raise ValueError("元解像度のフレームが素材の条件を満たしません。")
        crop, normalized = crop_bust(source, face)
        data = io.BytesIO()
        crop.save(data, "PNG")
    return process_character_asset(data.getvalue(), paths, known_face=normalized)
