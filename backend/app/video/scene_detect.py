import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field, model_validator


SCENE_SEGMENTS_FILENAME = "scene_segments.json"


class SceneSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "SceneSegment":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


def scene_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / SCENE_SEGMENTS_FILENAME


def _positive_duration(duration: float | None) -> float | None:
    if duration is None or duration <= 0:
        return None
    return float(duration)


def _clean_boundaries(boundaries: Sequence[float], duration: float) -> list[float]:
    cleaned = {
        round(float(boundary), 6)
        for boundary in boundaries
        if 0 < float(boundary) < duration
    }
    return sorted(cleaned)


def scene_segments_from_boundaries(
    boundaries: Sequence[float],
    duration: float | None,
) -> list[SceneSegment]:
    clean_duration = _positive_duration(duration)
    if clean_duration is None:
        return []

    points = [0.0, *_clean_boundaries(boundaries, clean_duration), clean_duration]
    segments: list[SceneSegment] = []
    for start, end in zip(points, points[1:]):
        if end > start:
            segments.append(SceneSegment(start=start, end=end))
    return segments


def segments_to_jsonable(segments: Sequence[SceneSegment]) -> list[dict[str, Any]]:
    return [segment.model_dump() for segment in segments]


def write_scene_segments(segments: Sequence[SceneSegment], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(segments_to_jsonable(segments), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def detect_scenes(input_path: str | Path, threshold: float = 27.0) -> list[SceneSegment]:
    try:
        from scenedetect import ContentDetector, detect
    except ImportError as exc:
        raise RuntimeError("PySceneDetect is not installed") from exc

    scenes = detect(str(input_path), ContentDetector(threshold=threshold))
    segments: list[SceneSegment] = []
    for start_time, end_time in scenes:
        segments.append(
            SceneSegment(
                start=float(start_time.get_seconds()),
                end=float(end_time.get_seconds()),
            )
        )
    return segments


def detect_scenes_to_json(
    input_path: str | Path,
    output_dir: str | Path,
    threshold: float = 27.0,
) -> Path:
    segments = detect_scenes(input_path, threshold=threshold)
    return write_scene_segments(segments, scene_output_path(output_dir))
