from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from app.thumbnail_style import resolve_thumbnail_text_styles
from typing import Any

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.models import ExportItem
from app.render.render_thumbnail import (
    ThumbnailRenderResult,
    render_normal_thumbnail,
    render_short_thumbnail,
)


NormalThumbnailRenderer = Callable[..., ThumbnailRenderResult]
ShortThumbnailRenderer = Callable[..., ThumbnailRenderResult]


@dataclass(frozen=True)
class ThumbnailGenerationFailure:
    export_id: str
    candidate_id: str | None
    error_code: str


@dataclass(frozen=True)
class ThumbnailGenerationBatchResult:
    generated_paths: list[Path]
    failures: list[ThumbnailGenerationFailure]


def read_export_metadata(export: ExportItem) -> dict[str, Any]:
    metadata_value = getattr(export, "metadata_path", None)
    if not metadata_value:
        return {}
    path = Path(metadata_value)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def thumbnail_path_from_export(export: ExportItem) -> Path | None:
    metadata = read_export_metadata(export)
    if metadata.get("thumbnail_status") != "ready":
        return None
    value = metadata.get("thumbnail_path")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def _write_metadata(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_export_metadata(path: str | Path, payload: dict[str, Any]) -> None:
    """Atomically update published export metadata."""
    _write_metadata(Path(path), payload)


def _candidate_map(selection: CandidateSelection) -> dict[str, Candidate]:
    return {
        candidate.id: candidate
        for candidate in (*selection.normal_clips, *selection.shorts)
    }


def _thumbnail_output_path(job_output_dir: Path, export: ExportItem) -> Path:
    type_dir = "shorts" if export.type == "short" else "normal"
    stem = Path(str(export.video_path)).stem
    return job_output_dir / "thumbnails" / type_dir / f"{stem}.jpg"


def thumbnail_output_path(job_output_dir: str | Path, export: ExportItem) -> Path:
    return _thumbnail_output_path(Path(job_output_dir), export)


def _normal_frame_seconds(candidate: Candidate) -> float:
    relative = candidate.thumbnail_frame_seconds
    if relative is None:
        relative = candidate.duration * 0.38
    return candidate.start + min(max(0.0, relative), candidate.duration)


def _short_hook_range(candidate: Candidate, export: ExportItem) -> tuple[float, float]:
    available = max(0.5, float(getattr(export, "duration", candidate.duration)))
    hook_duration = candidate.hook_duration_seconds or 2.0
    hook_scene_duration = (
        candidate.hook_scene_end - candidate.hook_scene_start
        if candidate.hook_scene_start is not None and candidate.hook_scene_end is not None
        else 0.0
    )
    metadata = read_export_metadata(export)
    hook_rendered = metadata.get("hook_rendered")
    if hook_rendered is None:
        hook_rendered = bool((candidate.hook_text or "").strip())
    if hook_rendered:
        visible_duration = hook_duration
        if hook_scene_duration > 0:
            visible_duration = min(visible_duration, hook_scene_duration)
    else:
        visible_duration = hook_scene_duration or min(3.0, available)
    return 0.0, min(available, max(0.5, min(3.0, visible_duration)))


def _ready_metadata(
    payload: dict[str, Any],
    *,
    result: ThumbnailRenderResult,
    output_path: Path,
    source_basis: str,
    character_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **payload,
        "thumbnail_path": str(output_path),
        "thumbnail_filename": output_path.name,
        "thumbnail_status": "ready",
        "thumbnail_source_time": round(result.source_timestamp, 3),
        "thumbnail_source_time_basis": source_basis,
        "thumbnail_width": result.width,
        "thumbnail_height": result.height,
        "thumbnail_template_version": (
            ("character_normal_v1" if character_style is not None else "raden_normal_v4")
            if result.kind == "normal" else "short_hook_frame_v1"
        ),
        "thumbnail_error_code": None,
        **({"thumbnail_text_styles": resolve_thumbnail_text_styles(character_style).model_dump(mode="json", by_alias=True)}
           if result.kind == "normal" else {}),
    }


def _failed_metadata(
    payload: dict[str, Any],
    *,
    output_path: Path,
    error_code: str,
) -> dict[str, Any]:
    return {
        **payload,
        "thumbnail_path": None,
        "thumbnail_filename": output_path.name,
        "thumbnail_status": "failed",
        "thumbnail_error_code": error_code,
    }


def generate_export_thumbnails(
    *,
    exports: Sequence[ExportItem],
    selection: CandidateSelection,
    input_path: str | Path,
    job_output_dir: str | Path,
    normal_renderer: NormalThumbnailRenderer = render_normal_thumbnail,
    short_renderer: ShortThumbnailRenderer = render_short_thumbnail,
    character_style: dict[str, Any] | None = None,
) -> ThumbnailGenerationBatchResult:
    output_dir = Path(job_output_dir)
    resolved_output_dir = output_dir.resolve(strict=False)
    candidates = _candidate_map(selection)
    generated_paths: list[Path] = []
    failures: list[ThumbnailGenerationFailure] = []

    for export in exports:
        candidate_id = getattr(export, "candidate_id", None)
        candidate = candidates.get(candidate_id or "")
        metadata_value = getattr(export, "metadata_path", None)
        metadata_path = Path(metadata_value) if metadata_value else None
        output_path = _thumbnail_output_path(output_dir, export)
        try:
            if candidate is None:
                raise ValueError("thumbnail candidate is unavailable")
            if metadata_path is None or not metadata_path.is_file():
                raise FileNotFoundError("thumbnail export metadata is unavailable")
            metadata_path.resolve().relative_to(resolved_output_dir)
            output_path.resolve(strict=False).relative_to(resolved_output_dir)
            payload = read_export_metadata(export)
            if export.type == "normal":
                result = normal_renderer(
                    input_path,
                    output_path,
                    **({"character_style": character_style} if character_style is not None else {}),
                    frame_time=_normal_frame_seconds(candidate),
                    eyebrow=candidate.thumbnail_kicker.strip(),
                    title_first_line=candidate.thumbnail_line1.strip(),
                    title_second_line=candidate.thumbnail_line2.strip(),
                )
                source_basis = "source_video_absolute"
            elif export.type == "short":
                hook_start, hook_end = _short_hook_range(candidate, export)
                result = short_renderer(
                    export.video_path,
                    output_path,
                    hook_start=hook_start,
                    hook_end=hook_end,
                )
                source_basis = "rendered_video_relative"
            else:
                raise ValueError("unsupported thumbnail export type")
            if result.path.resolve() != output_path.resolve() or not output_path.is_file():
                raise RuntimeError("thumbnail renderer returned an unpublished path")
            _write_metadata(
                metadata_path,
                _ready_metadata(
                    payload,
                    result=result,
                    output_path=output_path,
                    source_basis=source_basis,
                    character_style=character_style,
                ),
            )
            generated_paths.append(output_path)
        except Exception as exc:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            error_code = exc.__class__.__name__
            failures.append(
                ThumbnailGenerationFailure(
                    export_id=export.id,
                    candidate_id=candidate_id,
                    error_code=error_code,
                )
            )
            if metadata_path is not None and metadata_path.is_file():
                try:
                    metadata_path.resolve().relative_to(resolved_output_dir)
                    _write_metadata(
                        metadata_path,
                        _failed_metadata(
                            read_export_metadata(export),
                            output_path=output_path,
                            error_code=error_code,
                        ),
                    )
                except (OSError, ValueError):
                    pass

    return ThumbnailGenerationBatchResult(
        generated_paths=generated_paths,
        failures=failures,
    )
