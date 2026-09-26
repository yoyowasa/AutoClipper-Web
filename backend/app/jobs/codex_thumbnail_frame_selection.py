"""Rank actual source frames against saved thumbnail copy via the host Codex bridge."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageOps

from app.render.render_thumbnail import extract_thumbnail_frame
from app.scoring.thumbnail_frame_rank import CodexThumbnailFrameRanker, ThumbnailFrameRanking


FRAME_COUNT = 8
FrameExtractor = Callable[[str | Path, str | Path, float], Path]


def _candidate_seconds(duration: float) -> list[float]:
    if duration <= 0:
        raise ValueError("サムネ候補の動画範囲が空です。")
    return [round(duration * (index + 0.5) / FRAME_COUNT, 3) for index in range(FRAME_COUNT)]


def _nearby_subtitles(segments: list[dict[str, Any]], second: float) -> list[str]:
    nearby = sorted(
        segments,
        key=lambda item: abs(((float(item["start"]) + float(item["end"])) / 2) - second),
    )
    return [str(item["text"])[:100] for item in nearby[:2]]


def _contact_sheet(frames: list[Path], output: Path, *, first_id: int) -> Path:
    sheet = Image.new("RGB", (1280, 720), "#111111")
    draw = ImageDraw.Draw(sheet)
    for offset, frame in enumerate(frames):
        x, y = (offset % 2) * 640, (offset // 2) * 360
        with Image.open(frame) as original:
            tile = ImageOps.contain(original.convert("RGB"), (640, 340))
            sheet.paste(tile, (x + (640 - tile.width) // 2, y + 20 + (340 - tile.height) // 2))
        draw.rectangle((x, y, x + 639, y + 20), fill="#111111")
        draw.text((x + 8, y + 3), f"FRAME {first_id + offset}", fill="white")
    sheet.save(output, format="JPEG", quality=86)
    return output


def select_codex_thumbnail_frame_seconds(
    video_path: str | Path,
    *,
    clip_start: float,
    clip_end: float,
    current_frame_seconds: float,
    variant_index: int,
    storage_root: str | Path,
    temp_root: str | Path,
    job_id: str,
    export_id: str,
    text: dict[str, str],
    design: str,
    segments: list[dict[str, Any]],
    extractor: FrameExtractor = extract_thumbnail_frame,
    ranker: Any = None,
) -> float:
    """Return one clip-relative timestamp; do not change source video or presets."""
    duration = float(clip_end) - float(clip_start)
    seconds = _candidate_seconds(duration)
    temporary_root = Path(temp_root)
    temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="codex-thumbnail-", dir=temporary_root) as directory:
        work = Path(directory)
        frames = [
            extractor(video_path, work / f"frame_{index}.jpg", clip_start + second)
            for index, second in enumerate(seconds)
        ]
        sheets = [
            _contact_sheet(frames[index:index + 4], work / f"sheet_{index // 4}.jpg", first_id=index)
            for index in (0, 4)
        ]
        payload = {
            "thumbnailText": text,
            "template": design,
            "clipDurationSeconds": round(duration, 3),
            "candidateFrames": [
                {"frameId": index, "clipSecond": second, "nearbySubtitles": _nearby_subtitles(segments, second)}
                for index, second in enumerate(seconds)
            ],
        }
        active = ranker or CodexThumbnailFrameRanker(
            storage_root=storage_root,
            job_id=job_id,
            clip_id=f"thumb_frame_{export_id}",
        )
        ranking = ThumbnailFrameRanking.model_validate(active.generate(payload, sheets))
    order = ranking.ranked_frame_ids
    start = max(0, int(variant_index)) % len(order)
    for offset in range(len(order)):
        selected = seconds[order[(start + offset) % len(order)]]
        if abs(selected - current_frame_seconds) > max(0.25, duration * 0.02):
            return selected
    return seconds[order[start]]
