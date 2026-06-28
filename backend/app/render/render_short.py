from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.ids import make_id
from app.models import ExportItem, Job
from app.render.crop_strategy import (
    CropLayout,
    CropStrategy,
    build_center_crop_filter as _build_center_crop_filter,
    build_crop_filter,
    strategy_order,
)
from app.render.filters import loudnorm_filter
from app.render.subtitles_ass import SubtitleLayout, write_ass_for_candidate
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.face_detect import FaceDetection, best_face_center, detect_faces_for_clip
from app.video.probe import VideoMetadata, probe_metadata


@dataclass(frozen=True)
class ShortRenderResult:
    path: Path
    strategy: CropStrategy


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
    subprocess.run(command, check=True, capture_output=True, text=True)


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
    face_center = best_face_center(detections)
    last_error: Exception | None = None

    for strategy in strategy_order(layout, detections=detections, source_width=width, source_height=height):
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
            return ShortRenderResult(path=Path(output_path), strategy=strategy)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"short render failed: {last_error}") from last_error


def shorts_output_dir(paths: StoragePaths, job_id: str) -> Path:
    output_dir = paths.job_outputs(job_id) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _candidate_score(candidate: Candidate) -> float:
    for score in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if score is not None:
            return float(score)
    return 0.0


def _candidate_title(candidate: Candidate, index: int) -> str:
    return candidate.title or f"Short {index}"


def _write_export_metadata(
    path: Path,
    export_id: str,
    candidate: Candidate,
    title: str,
    video_path: Path,
    subtitle_path: Path | None,
    strategy: str | None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": export_id,
                "type": "short",
                "candidate_id": candidate.id,
                "title": title,
                "overlay_title": candidate.overlay_title,
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "score": _candidate_score(candidate),
                "strategy": strategy,
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
) -> ShortRenderBatchResult:
    storage_paths = paths or get_storage_paths()
    output_dir = shorts_output_dir(storage_paths, job.id)
    exports: list[ExportItem] = []
    failures: list[ShortRenderFailure] = []

    short_candidates = [candidate for candidate in selected_candidates if candidate.type == "short"]
    for index, candidate in enumerate(short_candidates, start=1):
        export_id = make_id("exp")
        output_path = output_dir / f"short_{index:02d}.mp4"
        metadata_path = output_dir / f"short_{index:02d}.json"
        subtitle_path: Path | None = None

        try:
            title = _candidate_title(candidate, index)
            if burn_subtitles:
                subtitle_path = output_dir / f"short_{index:02d}.ass"
                write_ass_for_candidate(
                    candidate,
                    _subtitle_segments_for_candidate(candidate, transcript_segments),
                    subtitle_path,
                    layout=SubtitleLayout.short(),
                    top_title=candidate.overlay_title,
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
            _write_export_metadata(
                metadata_path,
                export_id=export_id,
                candidate=candidate,
                title=title,
                video_path=rendered_path,
                subtitle_path=subtitle_path,
                strategy=render_result.strategy if isinstance(render_result, ShortRenderResult) else None,
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
