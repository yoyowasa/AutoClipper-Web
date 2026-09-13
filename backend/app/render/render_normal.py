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
from app.render.filters import ass_filter, loudnorm_filter
from app.render.subtitles_ass import SubtitleLayout, SubtitleRenderSettings, write_ass_for_candidate
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


def _hook_scene_range(
    start: float,
    end: float,
    hook_scene_start: float | None,
    hook_scene_end: float | None,
) -> tuple[float, float, float] | None:
    if (hook_scene_start is None) != (hook_scene_end is None):
        raise ValueError("hook scene requires both start and end")
    if hook_scene_start is None or hook_scene_end is None:
        return None
    hook_duration = hook_scene_end - hook_scene_start
    if not 0.5 <= hook_duration <= 3.0:
        raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
    if hook_scene_start < start - 0.001 or hook_scene_end > end + 0.001:
        raise ValueError("hook scene must stay within the selected clip")
    return hook_scene_start, hook_scene_end, hook_duration


def build_render_normal_command(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
    hook_scene_start: float | None = None,
    hook_scene_end: float | None = None,
) -> list[str]:
    hook_scene = _hook_scene_range(
        start,
        end,
        hook_scene_start,
        hook_scene_end,
    )
    if hook_scene is not None:
        hook_start, _hook_end, hook_duration = hook_scene
        filters = [
            "[0:v:0]setpts=PTS-STARTPTS[hook_v]",
            "[1:v:0]setpts=PTS-STARTPTS[main_v]",
            "[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[hook_a]",
            "[1:a:0]aresample=48000,asetpts=PTS-STARTPTS[main_a]",
            (
                "[hook_v][hook_a][main_v][main_a]"
                "concat=n=2:v=1:a=1[concat_v][concat_a]"
            ),
        ]
        video_label = "concat_v"
        if subtitle_path is not None:
            filters.append(f"[concat_v]{ass_filter(subtitle_path)}[video_out]")
            video_label = "video_out"
        audio_label = "concat_a"
        if normalize_audio:
            filters.append(f"[concat_a]{loudnorm_filter()}[audio_out]")
            audio_label = "audio_out"
        return [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{hook_start:.3f}",
            "-t",
            f"{hook_duration:.3f}",
            "-i",
            str(input_path),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{_duration(start, end):.3f}",
            "-i",
            str(input_path),
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{video_label}]",
            "-map",
            f"[{audio_label}]",
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
    hook_scene_start: float | None = None,
    hook_scene_end: float | None = None,
) -> Path:
    command = build_render_normal_command(
        input_path,
        output_path,
        start,
        end,
        subtitle_path=subtitle_path,
        normalize_audio=normalize_audio,
        ffmpeg_bin=ffmpeg_bin,
        hook_scene_start=hook_scene_start,
        hook_scene_end=hook_scene_end,
    )
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Path(output_path)


def normal_output_dir(paths: StoragePaths, job_id: str) -> Path:
    output_dir = paths.job_outputs(job_id) / "normal"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def normal_subtitle_dir(paths: StoragePaths, job_id: str) -> Path:
    return paths.job_subtitles(job_id, "normal")


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


def _candidate_hook_scene_duration(candidate: Candidate) -> float:
    if candidate.hook_scene_start is None or candidate.hook_scene_end is None:
        return 0.0
    return candidate.hook_scene_end - candidate.hook_scene_start


def _write_export_metadata(
    path: Path,
    export_id: str,
    candidate: Candidate,
    title: str,
    overlay_title: str,
    video_path: Path,
    subtitle_path: Path | None,
    hook_rendered: bool,
) -> Path:
    hook_scene_duration = _candidate_hook_scene_duration(candidate)
    output_duration = candidate.duration + hook_scene_duration
    path.write_text(
        json.dumps(
            {
                "id": export_id,
                "type": "normal",
                "candidate_id": candidate.id,
                "title": title,
                "overlay_title": overlay_title,
                "title_source": candidate.title_source,
                "title_candidates": [
                    item.model_dump(by_alias=True, mode="json")
                    for item in candidate.title_candidates
                ],
                "recommended_title_id": candidate.recommended_title_id,
                "selected_title_id": candidate.selected_title_id,
                "youtube_description": candidate.youtube_description,
                "youtube_hashtags": candidate.youtube_hashtags,
                "youtube_tags": candidate.youtube_tags,
                "description_evidence_segment_ids": candidate.description_evidence_segment_ids,
                "post_metadata_source": candidate.post_metadata_source,
                "post_metadata_revision_hash": candidate.post_metadata_revision_hash,
                "title_rendered": True,
                "overlay_title_expected": bool(overlay_title),
                "overlay_title_rendered": bool(overlay_title),
                "title_style": (
                    candidate.title_style.model_dump(by_alias=True)
                    if candidate.title_style
                    else None
                ),
                "start": candidate.start,
                "end": candidate.end,
                "duration": output_duration,
                "body_duration": candidate.duration,
                "hook_text": candidate.hook_text,
                "hook_rendered": hook_rendered,
                "hook_duration_seconds": candidate.hook_duration_seconds,
                "hook_scene_start": candidate.hook_scene_start,
                "hook_scene_end": candidate.hook_scene_end,
                "thumbnail_kicker": candidate.thumbnail_kicker,
                "thumbnail_line1": candidate.thumbnail_line1,
                "thumbnail_line2": candidate.thumbnail_line2,
                "thumbnail_frame_seconds": candidate.thumbnail_frame_seconds,
                "hook_scene_duration": hook_scene_duration,
                "hook_scene_rendered": hook_scene_duration > 0,
                "original_start": candidate.original_start,
                "original_end": candidate.original_end,
                "refined_start": candidate.refined_start,
                "refined_end": candidate.refined_end,
                "boundary_refined": candidate.boundary_refined,
                "boundary_refinement_reason": candidate.boundary_refinement_reason,
                "boundary_expansion_seconds": candidate.boundary_expansion_seconds,
                "subtitle_style": (
                    candidate.subtitle_style.model_dump(by_alias=True)
                    if candidate.subtitle_style
                    else None
                ),
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
    subtitle_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
) -> NormalRenderBatchResult:
    storage_paths = paths or get_storage_paths()
    output_dir = normal_output_dir(storage_paths, job.id)
    subtitle_dir = normal_subtitle_dir(storage_paths, job.id)
    exports: list[ExportItem] = []
    failures: list[NormalRenderFailure] = []

    normal_candidates = [candidate for candidate in selected_candidates if candidate.type == "normal"]
    for index, candidate in enumerate(normal_candidates, start=1):
        candidate = candidate_with_title(candidate, index=index, transcript_segments=transcript_segments)
        hook_scene_duration = _candidate_hook_scene_duration(candidate)
        output_duration = candidate.duration + hook_scene_duration
        export_id = make_id("exp")
        output_path = output_dir / f"normal_{index:02d}.mp4"
        metadata_path = output_dir / f"normal_{index:02d}.json"
        subtitle_path: Path | None = None

        try:
            title = _candidate_title(candidate, index)
            overlay_title = (
                candidate.overlay_title
                if candidate.overlay_title is not None
                else title
            ).strip()
            use_ass = burn_subtitles or bool(overlay_title)
            if use_ass:
                subtitle_path = subtitle_dir / f"normal_{index:02d}.ass"
                ass_candidate = (
                    candidate
                    if burn_subtitles
                    else candidate.model_copy(update={"hook_text": None})
                )
                write_ass_for_candidate(
                    ass_candidate,
                    (
                        _subtitle_segments_for_candidate(candidate, transcript_segments)
                        if burn_subtitles
                        else []
                    ),
                    subtitle_path,
                    layout=SubtitleLayout.normal(
                        width=normal_width,
                        height=normal_height,
                        settings=subtitle_settings,
                    ),
                    subtitle_settings=subtitle_settings,
                    top_title=overlay_title,
                )

            render_kwargs: dict[str, Any] = {
                "start": candidate.start,
                "end": candidate.end,
                "subtitle_path": subtitle_path,
                "normalize_audio": normalize_audio,
                "ffmpeg_bin": ffmpeg_bin,
            }
            if hook_scene_duration > 0:
                render_kwargs["hook_scene_start"] = candidate.hook_scene_start
                render_kwargs["hook_scene_end"] = candidate.hook_scene_end
            renderer(input_path, output_path, **render_kwargs)
            _remove_autoload_sidecar(output_path, subtitle_path)
            _write_export_metadata(
                metadata_path,
                export_id=export_id,
                candidate=candidate,
                title=title,
                overlay_title=overlay_title,
                video_path=output_path,
                subtitle_path=subtitle_path,
                hook_rendered=bool(burn_subtitles and candidate.hook_text),
            )

            export = ExportItem(
                id=export_id,
                job_id=job.id,
                video_id=job.video_id,
                candidate_id=candidate.id,
                type="normal",
                title=title,
                duration=output_duration,
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
