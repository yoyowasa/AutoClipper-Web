from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(os.environ.get("AUTOCLIPPER_ROOT", Path(__file__).resolve().parents[1]))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.audio.transcribe_faster_whisper import TranscriptSegment  # noqa: E402
from app.candidates.merge_boundaries import Candidate  # noqa: E402
from app.render.render_normal import render_normal_clip  # noqa: E402
from app.render.render_short import render_short_clip  # noqa: E402
from app.render.subtitles_ass import SubtitleLayout, write_ass_for_candidate  # noqa: E402


DEFAULT_SOURCE_JOB_ID = "job_6e0b6c7539644c679e853eccfcb77039"
DEFAULT_DATABASE_PATH = ROOT / "storage" / "autoclipper.db"


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    duration: float


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def container_output_path(job_id: str, folder: str, filename: str) -> str:
    return f"/app/storage/outputs/{job_id}/{folder}/{filename}"


def host_path_from_artifact(path_value: str | None, *, root: Path = ROOT) -> Path | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    prefix = "/app/storage/"
    if normalized.startswith(prefix):
        return root / "storage" / normalized.removeprefix(prefix)
    return Path(path_value)


def container_path_from_host_storage(path: Path, *, root: Path = ROOT) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to((root / "storage").resolve())
    except ValueError as exc:
        raise RuntimeError(f"--input-video with --docker-service must be under {root / 'storage'}: {path}") from exc
    return "/app/storage/" + relative.as_posix()


def resolve_input_video(source_job_id: str, database_path: Path, explicit_input: Path | None) -> Path:
    if explicit_input is not None:
        return explicit_input.resolve()
    if not database_path.is_file():
        raise RuntimeError(f"database not found: {database_path}")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            select videos.stored_path
            from jobs
            join videos on videos.id = jobs.video_id
            where jobs.id = ?
            """,
            (source_job_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError(f"source job not found in database: {source_job_id}")
    resolved = host_path_from_artifact(str(row["stored_path"]))
    if resolved is None:
        raise RuntimeError(f"could not resolve stored video path: {row['stored_path']}")
    return resolved.resolve()


def probe_media(path: Path, ffprobe_bin: str = "ffprobe") -> ProbeResult:
    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    payload = json.loads(completed.stdout)
    stream = payload["streams"][0]
    duration = float(payload.get("format", {}).get("duration") or 0.0)
    return ProbeResult(width=int(stream["width"]), height=int(stream["height"]), duration=duration)


def clip_with_duration_limit(clip: dict[str, Any], limit_seconds: float | None) -> dict[str, Any]:
    if not limit_seconds or limit_seconds <= 0:
        return dict(clip)
    adjusted = dict(clip)
    start = float(adjusted["start"])
    end = float(adjusted["end"])
    adjusted_end = min(end, start + limit_seconds)
    adjusted["end"] = round(adjusted_end, 3)
    adjusted["duration"] = round(adjusted_end - start, 3)
    adjusted["id"] = f"{adjusted['id']}_burnin"
    return adjusted


def selected_subset(
    selected: dict[str, Any],
    *,
    normal_count: int,
    short_count: int,
    normal_duration_limit: float | None,
) -> dict[str, list[dict[str, Any]]]:
    normal_clips = [
        clip_with_duration_limit(clip, normal_duration_limit)
        for clip in selected.get("normalClips", [])[:normal_count]
    ]
    shorts = [dict(clip) for clip in selected.get("shorts", [])[:short_count]]
    return {"normalClips": normal_clips, "shorts": shorts}


def candidates_from_subset(subset: dict[str, list[dict[str, Any]]]) -> tuple[list[Candidate], list[Candidate]]:
    normal_candidates = [Candidate(**{**clip, "type": "normal"}) for clip in subset["normalClips"]]
    short_candidates = [Candidate(**{**clip, "type": "short"}) for clip in subset["shorts"]]
    return normal_candidates, short_candidates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a small ASS subtitle burn-in smoke from existing job artifacts.")
    parser.add_argument("--source-job-id", default=DEFAULT_SOURCE_JOB_ID)
    parser.add_argument("--output-job-id", default=None)
    parser.add_argument("--input-video", type=Path, default=None)
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--normal-count", type=int, default=1)
    parser.add_argument("--short-count", type=int, default=2)
    parser.add_argument("--normal-duration-limit", type=float, default=120.0)
    parser.add_argument("--short-layout", choices=["center_crop", "blur_background"], default="center_crop")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--ffprobe-bin", default="ffprobe")
    parser.add_argument(
        "--docker-service",
        default=None,
        help="Run the smoke inside a compose service, usually 'worker', so container ffmpeg/ffprobe are used.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run_in_docker(args: argparse.Namespace) -> int:
    service = str(args.docker_service)
    temp_script = ROOT / "storage" / "temp" / "smoke_subtitle_burn_in.py"
    temp_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), temp_script)

    forwarded = [
        "--source-job-id",
        str(args.source_job_id),
        "--database-path",
        "/app/storage/autoclipper.db",
        "--normal-count",
        str(args.normal_count),
        "--short-count",
        str(args.short_count),
        "--normal-duration-limit",
        str(args.normal_duration_limit),
        "--short-layout",
        str(args.short_layout),
        "--ffmpeg-bin",
        str(args.ffmpeg_bin),
        "--ffprobe-bin",
        str(args.ffprobe_bin),
    ]
    if args.output_job_id:
        forwarded.extend(["--output-job-id", str(args.output_job_id)])
    if args.input_video:
        forwarded.extend(["--input-video", container_path_from_host_storage(Path(args.input_video))])

    script = "/app/storage/temp/smoke_subtitle_burn_in.py"
    command = "AUTOCLIPPER_ROOT=/app python " + shlex.quote(script)
    command += " " + " ".join(shlex.quote(value) for value in forwarded)
    completed = subprocess.run(["docker", "compose", "exec", "-T", service, "sh", "-lc", command], cwd=ROOT)
    return int(completed.returncode)


def run(args: argparse.Namespace) -> int:
    if args.docker_service:
        return run_in_docker(args)

    source_job_id = str(args.source_job_id)
    output_job_id = args.output_job_id or f"{source_job_id}_task35b_burnin_{int(time.time())}"
    source_dir = ROOT / "storage" / "outputs" / source_job_id
    output_dir = ROOT / "storage" / "outputs" / output_job_id
    if not source_dir.is_dir():
        raise RuntimeError(f"source output directory not found: {source_dir}")

    input_video = resolve_input_video(source_job_id, Path(args.database_path), args.input_video)
    if not input_video.is_file():
        raise RuntimeError(f"input video not found: {input_video}")
    input_probe = probe_media(input_video, ffprobe_bin=args.ffprobe_bin)

    selected = read_json(source_dir / "selected_clips.json")
    transcript_payload = read_json(source_dir / "transcript_segments.json")
    subset = selected_subset(
        selected,
        normal_count=max(0, args.normal_count),
        short_count=max(0, args.short_count),
        normal_duration_limit=args.normal_duration_limit,
    )
    normal_candidates, short_candidates = candidates_from_subset(subset)
    if not normal_candidates or not short_candidates:
        raise RuntimeError("smoke requires at least one normal and one short candidate")

    transcript_segments = [TranscriptSegment(**segment) for segment in transcript_payload]
    normal_dir = output_dir / "normal"
    shorts_dir = output_dir / "shorts"
    normal_dir.mkdir(parents=True, exist_ok=True)
    shorts_dir.mkdir(parents=True, exist_ok=True)

    write_json(output_dir / "selected_clips.json", subset)
    write_json(output_dir / "transcript_segments.json", transcript_payload)
    write_json(
        output_dir / "selected_clips_summary.json",
        {
            "selected_normal_count": len(normal_candidates),
            "selected_short_count": len(short_candidates),
            "requested_normal_count": args.normal_count,
            "requested_short_count": args.short_count,
        },
    )
    write_json(
        output_dir / "candidate_summary.json",
        {
            "total_candidates": len(normal_candidates) + len(short_candidates),
            "normal_candidates": len(normal_candidates),
            "short_candidates": len(short_candidates),
        },
    )

    failures: list[dict[str, str]] = []
    rendered: list[dict[str, Any]] = []

    for index, candidate in enumerate(normal_candidates, start=1):
        try:
            subtitle_path = normal_dir / f"normal_{index:02d}.ass"
            output_path = normal_dir / f"normal_{index:02d}.mp4"
            write_ass_for_candidate(
                candidate,
                transcript_segments,
                subtitle_path,
                layout=SubtitleLayout.normal(width=input_probe.width, height=input_probe.height),
            )
            render_normal_clip(
                input_video,
                output_path,
                start=candidate.start,
                end=candidate.end,
                subtitle_path=subtitle_path,
                normalize_audio=False,
                ffmpeg_bin=args.ffmpeg_bin,
            )
            probe = probe_media(output_path, ffprobe_bin=args.ffprobe_bin)
            metadata = {
                "id": f"smoke_normal_{index:02d}",
                "type": "normal",
                "candidate_id": candidate.id,
                "title": candidate.title or f"Normal Burn-in {index:02d}",
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "score": candidate.final_score or candidate.rule_score or 0.0,
                "width": probe.width,
                "height": probe.height,
                "video_path": container_output_path(output_job_id, "normal", output_path.name),
                "subtitle_path": container_output_path(output_job_id, "normal", subtitle_path.name),
            }
            write_json(normal_dir / f"normal_{index:02d}.json", metadata)
            rendered.append({"candidate_id": candidate.id, "type": "normal", **metadata})
        except Exception as exc:
            failures.append({"candidate_id": candidate.id, "type": "normal", "error": str(exc)})

    for index, candidate in enumerate(short_candidates, start=1):
        try:
            subtitle_path = shorts_dir / f"short_{index:02d}.ass"
            output_path = shorts_dir / f"short_{index:02d}.mp4"
            write_ass_for_candidate(
                candidate,
                transcript_segments,
                subtitle_path,
                layout=SubtitleLayout.short(),
                top_title=candidate.overlay_title,
            )
            render_result = render_short_clip(
                input_video,
                output_path,
                start=candidate.start,
                end=candidate.end,
                subtitle_path=subtitle_path,
                normalize_audio=False,
                ffmpeg_bin=args.ffmpeg_bin,
                layout=args.short_layout,
                source_width=input_probe.width,
                source_height=input_probe.height,
            )
            rendered_path = render_result.path
            probe = probe_media(rendered_path, ffprobe_bin=args.ffprobe_bin)
            if (probe.width, probe.height) != (1080, 1920):
                raise RuntimeError(f"short output is not 1080x1920: {probe.width}x{probe.height}")
            metadata = {
                "id": f"smoke_short_{index:02d}",
                "type": "short",
                "candidate_id": candidate.id,
                "title": candidate.title or f"Short Burn-in {index:02d}",
                "overlay_title": candidate.overlay_title,
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "score": candidate.final_score or candidate.rule_score or 0.0,
                "strategy": render_result.strategy,
                "width": probe.width,
                "height": probe.height,
                "video_path": container_output_path(output_job_id, "shorts", rendered_path.name),
                "subtitle_path": container_output_path(output_job_id, "shorts", subtitle_path.name),
            }
            write_json(shorts_dir / f"short_{index:02d}.json", metadata)
            rendered.append({"candidate_id": candidate.id, "type": "short", **metadata})
        except Exception as exc:
            failures.append({"candidate_id": candidate.id, "type": "short", "error": str(exc)})

    write_json(output_dir / "render_failures.json", failures)
    summary = {
        "source_job_id": source_job_id,
        "output_job_id": output_job_id,
        "input_video": str(input_video),
        "normal_count": len([item for item in rendered if item["type"] == "normal"]),
        "short_count": len([item for item in rendered if item["type"] == "short"]),
        "render_failure_count": len(failures),
        "rendered": rendered,
        "failures": failures,
    }
    write_json(output_dir / "subtitle_burn_in_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
