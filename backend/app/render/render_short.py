from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.title_fallback import candidate_with_title, resolve_candidate_title
from app.ids import make_id
from app.models import ExportItem, Job
from app.render.crop_strategy import (
    CropLayout,
    CropStrategy,
    build_center_crop_filter as _build_center_crop_filter,
    build_crop_filter,
    plan_short_crop,
)
from app.render.filters import loudnorm_filter
from app.render.subtitles_ass import SubtitleLayout, SubtitleRenderSettings, write_ass_for_candidate
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.face_detect import FaceDetection, best_face_center, detect_faces_for_clip
from app.video.probe import VideoMetadata, probe_metadata

SHORT_OVERLAY_TITLE_MODES = {"auto", "always", "high_quality_only", "never"}


@dataclass(frozen=True)
class ShortRenderResult:
    path: Path
    strategy: CropStrategy
    crop_signal_source: str | None = None
    crop_confidence: float | None = None
    crop_fallback_reason: str | None = None
    crop_x: int | None = None
    crop_y: int | None = None
    crop_detection_count: int | None = None
    crop_attempted_strategies: tuple[CropStrategy, ...] = ()


@dataclass(frozen=True)
class ShortRenderFailure:
    candidate_id: str
    error: str


@dataclass(frozen=True)
class ShortRenderBatchResult:
    exports: list[ExportItem]
    failures: list[ShortRenderFailure]


def build_center_crop_filter(subtitle_path: str | Path | None = None) -> str:
    return _build_center_crop_filter(subtitle_path)


ShortCommandRunner = Callable[[list[str]], None]
ShortClipRenderer = Callable[..., Path | ShortRenderResult]
FaceDetector = Callable[[str | Path, float, float], list[FaceDetection]]
MetadataProbe = Callable[[str | Path], VideoMetadata]


def _duration(start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        raise ValueError("end must be greater than start")
    return duration


def _run_ffmpeg_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def build_render_short_command(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
    layout: CropStrategy = "center_crop",
    source_width: int | None = None,
    source_height: int | None = None,
    face_center: tuple[float, float] | None = None,
) -> list[str]:
    command = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(input_path),
        "-t",
        f"{_duration(start, end):.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        build_crop_filter(
            layout,
            subtitle_path=subtitle_path,
            source_width=source_width,
            source_height=source_height,
            face_center=face_center,
        ),
    ]

    if normalize_audio:
        command.extend(["-af", loudnorm_filter()])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def render_short_center_crop(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    command = build_render_short_command(
        input_path,
        output_path,
        start,
        end,
        subtitle_path=subtitle_path,
        normalize_audio=normalize_audio,
        ffmpeg_bin=ffmpeg_bin,
    )
    _run_ffmpeg_command(command)
    return Path(output_path)


def _source_dimensions(
    input_path: str | Path,
    source_width: int | None,
    source_height: int | None,
    metadata_probe: MetadataProbe,
) -> tuple[int | None, int | None]:
    if source_width is not None and source_height is not None:
        return source_width, source_height
    try:
        metadata = metadata_probe(input_path)
    except Exception:
        return source_width, source_height
    return source_width or metadata.width, source_height or metadata.height


def _detect_faces_for_layout(
    layout: CropLayout,
    input_path: str | Path,
    start: float,
    end: float,
    face_detector: FaceDetector,
) -> list[FaceDetection]:
    if layout not in ("auto", "face_tracking_crop"):
        return []
    try:
        return face_detector(input_path, start, end)
    except Exception:
        return []


def render_short_clip(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
    layout: CropLayout = "auto",
    source_width: int | None = None,
    source_height: int | None = None,
    face_detector: FaceDetector = detect_faces_for_clip,
    metadata_probe: MetadataProbe = probe_metadata,
    command_runner: ShortCommandRunner = _run_ffmpeg_command,
) -> ShortRenderResult:
    width, height = _source_dimensions(
        input_path,
        source_width=source_width,
        source_height=source_height,
        metadata_probe=metadata_probe,
    )
    detections = _detect_faces_for_layout(
        layout,
        input_path=input_path,
        start=start,
        end=end,
        face_detector=face_detector,
    )
    crop_plan = plan_short_crop(layout, detections=detections, source_width=width, source_height=height)
    face_center = crop_plan.face_center or best_face_center(detections)
    last_error: Exception | None = None
    attempted: list[CropStrategy] = []

    for strategy in crop_plan.strategy_order:
        attempted.append(strategy)
        try:
            command = build_render_short_command(
                input_path,
                output_path,
                start=start,
                end=end,
                subtitle_path=subtitle_path,
                normalize_audio=normalize_audio,
                ffmpeg_bin=ffmpeg_bin,
                layout=strategy,
                source_width=width,
                source_height=height,
                face_center=face_center if strategy == "face_tracking_crop" else None,
            )
            command_runner(command)
            fallback_reason = crop_plan.fallback_reason
            if len(attempted) > 1 and fallback_reason is None:
                fallback_reason = f"render_strategy_failed:{attempted[0]}"
            return ShortRenderResult(
                path=Path(output_path),
                strategy=strategy,
                crop_signal_source=crop_plan.signal_source,
                crop_confidence=crop_plan.confidence,
                crop_fallback_reason=fallback_reason,
                crop_x=crop_plan.crop_x,
                crop_y=crop_plan.crop_y,
                crop_detection_count=crop_plan.detection_count,
                crop_attempted_strategies=tuple(attempted),
            )
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"short render failed: {last_error}") from last_error


def shorts_output_dir(paths: StoragePaths, job_id: str) -> Path:
    output_dir = paths.job_outputs(job_id) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def shorts_subtitle_dir(paths: StoragePaths, job_id: str) -> Path:
    return paths.job_subtitles(job_id, "short")


def _remove_autoload_sidecar(output_path: Path, subtitle_path: Path | None) -> None:
    sidecar_path = output_path.with_suffix(".ass")
    if subtitle_path is not None and sidecar_path.resolve() == subtitle_path.resolve():
        return
    if sidecar_path.is_file():
        sidecar_path.unlink()


def _candidate_score(candidate: Candidate) -> float:
    for score in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if score is not None:
            return float(score)
    return 0.0


def _candidate_title(candidate: Candidate, index: int) -> str:
    return resolve_candidate_title(candidate, index=index).title


def _setting_text(settings: SubtitleRenderSettings | dict[str, Any] | None, key: str) -> str | None:
    if isinstance(settings, dict):
        value = settings.get(key)
        if value is not None:
            return str(value)
    return None


def _normalize_overlay_title_mode(value: str | None) -> str:
    mode = (value or "auto").strip()
    return mode if mode in SHORT_OVERLAY_TITLE_MODES else "auto"


def _render_mode(settings: SubtitleRenderSettings | dict[str, Any] | None, explicit_mode: str | None) -> str:
    return (explicit_mode or _setting_text(settings, "mode") or "high_quality").strip()


def _overlay_title_expected(*, mode: str, overlay_title_mode: str) -> bool:
    if overlay_title_mode == "always":
        return True
    if overlay_title_mode == "never":
        return False
    if overlay_title_mode in {"auto", "high_quality_only"}:
        return mode == "high_quality"
    return mode == "high_quality"


def _overlay_title_for_burn(candidate: Candidate, *, expected: bool, fallback_title: str) -> str:
    if not expected:
        return ""
    return (candidate.overlay_title or fallback_title).strip()


def _write_export_metadata(
    path: Path,
    export_id: str,
    candidate: Candidate,
    title: str,
    video_path: Path,
    subtitle_path: Path | None,
    strategy: str | None,
    crop_signal_source: str | None,
    crop_confidence: float | None,
    crop_fallback_reason: str | None,
    crop_x: int | None,
    crop_y: int | None,
    crop_detection_count: int | None,
    crop_attempted_strategies: Sequence[str],
    overlay_title_expected: bool,
    overlay_title_rendered: bool,
    overlay_title_mode: str,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": export_id,
                "type": "short",
                "candidate_id": candidate.id,
                "title": title,
                "overlay_title": candidate.overlay_title,
                "overlay_title_expected": overlay_title_expected,
                "overlay_title_rendered": overlay_title_rendered,
                "overlay_title_mode": overlay_title_mode,
                "title_source": candidate.title_source,
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "original_start": candidate.original_start,
                "original_end": candidate.original_end,
                "refined_start": candidate.refined_start,
                "refined_end": candidate.refined_end,
                "boundary_refined": candidate.boundary_refined,
                "boundary_refinement_reason": candidate.boundary_refinement_reason,
                "boundary_expansion_seconds": candidate.boundary_expansion_seconds,
                "score": _candidate_score(candidate),
                "strategy": strategy,
                "crop_strategy": strategy,
                "crop_signal_source": crop_signal_source,
                "crop_confidence": crop_confidence,
                "crop_fallback_reason": crop_fallback_reason,
                "crop_x": crop_x,
                "crop_y": crop_y,
                "crop_detection_count": crop_detection_count,
                "crop_attempted_strategies": list(crop_attempted_strategies),
                "video_path": str(video_path),
                "subtitle_path": str(subtitle_path) if subtitle_path is not None else None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _subtitle_segments_for_candidate(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> list[TranscriptSegment]:
    if transcript_segments is not None:
        return list(transcript_segments)
    if not candidate.transcript_text.strip():
        return []
    return [
        TranscriptSegment(
            start=candidate.start,
            end=candidate.end,
            text=candidate.transcript_text,
        )
    ]


def _rendered_path(result: Path | ShortRenderResult) -> Path:
    if isinstance(result, ShortRenderResult):
        return result.path
    return Path(result)


def render_selected_short_candidates(
    db: Session,
    job: Job,
    input_path: str | Path,
    selected_candidates: Sequence[Candidate],
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    burn_subtitles: bool = True,
    normalize_audio: bool = False,
    layout: CropLayout = "auto",
    paths: StoragePaths | None = None,
    renderer: ShortClipRenderer = render_short_clip,
    ffmpeg_bin: str = "ffmpeg",
    source_width: int | None = None,
    source_height: int | None = None,
    subtitle_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    mode: str | None = None,
    short_overlay_title_mode: str | None = None,
) -> ShortRenderBatchResult:
    storage_paths = paths or get_storage_paths()
    output_dir = shorts_output_dir(storage_paths, job.id)
    subtitle_dir = shorts_subtitle_dir(storage_paths, job.id)
    exports: list[ExportItem] = []
    failures: list[ShortRenderFailure] = []
    resolved_mode = _render_mode(subtitle_settings, mode)
    overlay_title_mode = _normalize_overlay_title_mode(
        short_overlay_title_mode or _setting_text(subtitle_settings, "shortOverlayTitleMode")
    )
    overlay_expected = _overlay_title_expected(mode=resolved_mode, overlay_title_mode=overlay_title_mode)

    short_candidates = [candidate for candidate in selected_candidates if candidate.type == "short"]
    for index, candidate in enumerate(short_candidates, start=1):
        candidate = candidate_with_title(candidate, index=index, transcript_segments=transcript_segments)
        export_id = make_id("exp")
        output_path = output_dir / f"short_{index:02d}.mp4"
        metadata_path = output_dir / f"short_{index:02d}.json"
        subtitle_path: Path | None = None

        try:
            title = _candidate_title(candidate, index)
            top_title = _overlay_title_for_burn(candidate, expected=overlay_expected, fallback_title=title)
            overlay_rendered = bool(burn_subtitles and top_title)
            if burn_subtitles:
                subtitle_path = subtitle_dir / f"short_{index:02d}.ass"
                write_ass_for_candidate(
                    candidate,
                    _subtitle_segments_for_candidate(candidate, transcript_segments),
                    subtitle_path,
                    layout=SubtitleLayout.short(settings=subtitle_settings),
                    top_title=top_title,
                    subtitle_settings=subtitle_settings,
                )

            render_result = renderer(
                input_path,
                output_path,
                start=candidate.start,
                end=candidate.end,
                subtitle_path=subtitle_path,
                normalize_audio=normalize_audio,
                ffmpeg_bin=ffmpeg_bin,
                layout=layout,
                source_width=source_width,
                source_height=source_height,
            )
            rendered_path = _rendered_path(render_result)
            _remove_autoload_sidecar(output_path, subtitle_path)
            _write_export_metadata(
                metadata_path,
                export_id=export_id,
                candidate=candidate,
                title=title,
                video_path=rendered_path,
                subtitle_path=subtitle_path,
                strategy=render_result.strategy if isinstance(render_result, ShortRenderResult) else None,
                crop_signal_source=render_result.crop_signal_source if isinstance(render_result, ShortRenderResult) else None,
                crop_confidence=render_result.crop_confidence if isinstance(render_result, ShortRenderResult) else None,
                crop_fallback_reason=render_result.crop_fallback_reason if isinstance(render_result, ShortRenderResult) else None,
                crop_x=render_result.crop_x if isinstance(render_result, ShortRenderResult) else None,
                crop_y=render_result.crop_y if isinstance(render_result, ShortRenderResult) else None,
                crop_detection_count=render_result.crop_detection_count if isinstance(render_result, ShortRenderResult) else None,
                crop_attempted_strategies=render_result.crop_attempted_strategies
                if isinstance(render_result, ShortRenderResult)
                else (),
                overlay_title_expected=overlay_expected,
                overlay_title_rendered=overlay_rendered,
                overlay_title_mode=overlay_title_mode,
            )

            export = ExportItem(
                id=export_id,
                job_id=job.id,
                video_id=job.video_id,
                candidate_id=candidate.id,
                type="short",
                title=title,
                duration=candidate.duration,
                score=_candidate_score(candidate),
                video_path=str(rendered_path),
                subtitle_path=str(subtitle_path) if subtitle_path is not None else None,
                metadata_path=str(metadata_path),
            )
            db.add(export)
            db.commit()
            db.refresh(export)
            exports.append(export)
        except Exception as exc:
            db.rollback()
            failures.append(ShortRenderFailure(candidate_id=candidate.id, error=str(exc)))

    return ShortRenderBatchResult(exports=exports, failures=failures)
