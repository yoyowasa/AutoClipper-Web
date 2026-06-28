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
from app.render.filters import ass_filter, loudnorm_filter
from app.render.subtitles_ass import SubtitleLayout, write_ass_for_candidate
from app.storage.paths import StoragePaths, get_storage_paths


NormalClipRenderer = Callable[..., Path]


@dataclass(frozen=True)
class NormalRenderFailure:
    candidate_id: str
    error: str


@dataclass(frozen=True)
class NormalRenderBatchResult:
    exports: list[ExportItem]
    failures: list[NormalRenderFailure]


def _duration(start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        raise ValueError("end must be greater than start")
    return duration


def build_render_normal_command(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
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
    ]

    if subtitle_path is not None:
        command.extend(["-vf", ass_filter(subtitle_path)])

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


def render_normal_clip(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    command = build_render_normal_command(
        input_path,
        output_path,
        start,
        end,
        subtitle_path=subtitle_path,
        normalize_audio=normalize_audio,
        ffmpeg_bin=ffmpeg_bin,
    )
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Path(output_path)


def normal_output_dir(paths: StoragePaths, job_id: str) -> Path:
    output_dir = paths.job_outputs(job_id) / "normal"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _candidate_score(candidate: Candidate) -> float:
    for score in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if score is not None:
            return float(score)
    return 0.0


def _candidate_title(candidate: Candidate, index: int) -> str:
    return candidate.title or f"Normal clip {index}"


def _write_export_metadata(
    path: Path,
    export_id: str,
    candidate: Candidate,
    title: str,
    video_path: Path,
    subtitle_path: Path | None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": export_id,
                "type": "normal",
                "candidate_id": candidate.id,
                "title": title,
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "score": _candidate_score(candidate),
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


def render_selected_normal_candidates(
    db: Session,
    job: Job,
    input_path: str | Path,
    selected_candidates: Sequence[Candidate],
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    burn_subtitles: bool = True,
    normalize_audio: bool = False,
    paths: StoragePaths | None = None,
    renderer: NormalClipRenderer = render_normal_clip,
    ffmpeg_bin: str = "ffmpeg",
    normal_width: int = 1920,
    normal_height: int = 1080,
) -> NormalRenderBatchResult:
    storage_paths = paths or get_storage_paths()
    output_dir = normal_output_dir(storage_paths, job.id)
    exports: list[ExportItem] = []
    failures: list[NormalRenderFailure] = []

    normal_candidates = [candidate for candidate in selected_candidates if candidate.type == "normal"]
    for index, candidate in enumerate(normal_candidates, start=1):
        export_id = make_id("exp")
        output_path = output_dir / f"normal_{index:02d}.mp4"
        metadata_path = output_dir / f"normal_{index:02d}.json"
        subtitle_path: Path | None = None

        try:
            title = _candidate_title(candidate, index)
            if burn_subtitles:
                subtitle_path = output_dir / f"normal_{index:02d}.ass"
                write_ass_for_candidate(
                    candidate,
                    _subtitle_segments_for_candidate(candidate, transcript_segments),
                    subtitle_path,
                    layout=SubtitleLayout.normal(width=normal_width, height=normal_height),
                )

            renderer(
                input_path,
                output_path,
                start=candidate.start,
                end=candidate.end,
                subtitle_path=subtitle_path,
                normalize_audio=normalize_audio,
                ffmpeg_bin=ffmpeg_bin,
            )
            _write_export_metadata(
                metadata_path,
                export_id=export_id,
                candidate=candidate,
                title=title,
                video_path=output_path,
                subtitle_path=subtitle_path,
            )

            export = ExportItem(
                id=export_id,
                job_id=job.id,
                video_id=job.video_id,
                candidate_id=candidate.id,
                type="normal",
                title=title,
                duration=candidate.duration,
                score=_candidate_score(candidate),
                video_path=str(output_path),
                subtitle_path=str(subtitle_path) if subtitle_path is not None else None,
                metadata_path=str(metadata_path),
            )
            db.add(export)
            db.commit()
            db.refresh(export)
            exports.append(export)
        except Exception as exc:
            db.rollback()
            failures.append(NormalRenderFailure(candidate_id=candidate.id, error=str(exc)))

    return NormalRenderBatchResult(exports=exports, failures=failures)
