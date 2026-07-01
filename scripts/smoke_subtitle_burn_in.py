from __future__ import annotations

import argparse
import json
import os
import re
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
TASK35C_DEFAULT_OVERLAY_TITLE = "日本語タイトル確認"


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    duration: float


@dataclass(frozen=True)
class AssLayoutInspection:
    title_style_exists: bool
    subtitle_style_exists: bool
    title_dialogue_count: int
    subtitle_dialogue_count: int
    title_margin_v: int | None
    subtitle_margin_v: int | None
    title_subtitle_vertical_gap: int | None
    title_subtitle_overlap: bool
    safe_vertical_positions: bool


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def container_output_path(job_id: str, *parts: str) -> str:
    suffix = "/".join(parts)
    return f"/app/storage/outputs/{job_id}/{suffix}"


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


def extract_frame(
    input_video: Path,
    output_path: Path,
    *,
    timestamp_seconds: float,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{max(0.0, timestamp_seconds):.3f}",
        "-i",
        str(input_video),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return output_path


def _parse_style_fields(ass_text: str, style_name: str) -> dict[str, Any]:
    prefix = f"Style: {style_name},"
    for line in ass_text.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line.removeprefix("Style: ").split(",")
        if len(parts) < 23:
            return {}
        return {
            "name": parts[0],
            "font_name": parts[1],
            "font_size": int(float(parts[2])),
            "outline": int(float(parts[16])),
            "alignment": int(parts[18]),
            "margin_v": int(parts[21]),
        }
    return {}


def inspect_ass_layout(path: Path, layout: SubtitleLayout) -> AssLayoutInspection:
    ass_text = path.read_text(encoding="utf-8", errors="replace")
    title_style = _parse_style_fields(ass_text, "Title")
    subtitle_style = _parse_style_fields(ass_text, "Subtitle")
    title_count = sum(1 for line in ass_text.splitlines() if line.startswith("Dialogue:") and ",Title,," in line)
    subtitle_count = sum(1 for line in ass_text.splitlines() if line.startswith("Dialogue:") and ",Subtitle,," in line)
    title_margin = title_style.get("margin_v")
    subtitle_margin = subtitle_style.get("margin_v")
    title_bottom = None
    subtitle_top = None
    gap = None
    overlap = False
    if title_style and subtitle_style:
        title_bottom = (
            int(title_margin)
            + int(title_style["font_size"]) * layout.max_lines
            + int(title_style.get("outline") or 0) * 2
        )
        subtitle_top = (
            layout.height
            - int(subtitle_margin)
            - int(subtitle_style["font_size"]) * layout.max_lines
            - int(subtitle_style.get("outline") or 0) * 2
        )
        gap = subtitle_top - title_bottom
        overlap = gap <= 0
    return AssLayoutInspection(
        title_style_exists=bool(title_style),
        subtitle_style_exists=bool(subtitle_style),
        title_dialogue_count=title_count,
        subtitle_dialogue_count=subtitle_count,
        title_margin_v=title_margin,
        subtitle_margin_v=subtitle_margin,
        title_subtitle_vertical_gap=gap,
        title_subtitle_overlap=overlap,
        safe_vertical_positions=bool(title_style and subtitle_style and title_count > 0 and subtitle_count > 0 and not overlap),
    )


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


def apply_overlay_title_policy(
    subset: dict[str, list[dict[str, Any]]],
    *,
    require_overlay_title: bool,
    force_overlay_title: str | None,
) -> dict[str, list[dict[str, Any]]]:
    updated = {"normalClips": [dict(clip) for clip in subset["normalClips"]], "shorts": []}
    for index, clip in enumerate(subset["shorts"], start=1):
        short = dict(clip)
        original_overlay_title = short.get("overlay_title")
        if force_overlay_title:
            short["source_overlay_title"] = original_overlay_title
            short["overlay_title"] = force_overlay_title.format(index=index, number=f"{index:02d}")
        if require_overlay_title and not str(short.get("overlay_title") or "").strip():
            raise RuntimeError(f"short candidate lacks overlay_title: {short.get('id')}")
        updated["shorts"].append(short)
    return updated


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
    parser.add_argument("--job-id", dest="source_job_id", help="Alias for --source-job-id.")
    parser.add_argument("--video", type=Path, default=None, help="Optional input video for a high_quality E2E before smoke rendering.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--mode", default=None, choices=["low_cost", "fast", "high_quality"])
    parser.add_argument("--openai-candidate-limit", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output-job-id", default=None)
    parser.add_argument("--input-video", type=Path, default=None)
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--normal-count", type=int, default=1)
    parser.add_argument("--short-count", type=int, default=2)
    parser.add_argument("--normal-duration-limit", type=float, default=120.0)
    parser.add_argument("--short-layout", choices=["center_crop", "blur_background"], default="center_crop")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--ffprobe-bin", default="ffprobe")
    parser.add_argument("--require-overlay-title", action="store_true")
    parser.add_argument("--force-overlay-title", default=None)
    parser.add_argument("--extract-short-frames", dest="extract_short_frames", action="store_true", default=True)
    parser.add_argument("--no-extract-short-frames", dest="extract_short_frames", action="store_false")
    parser.add_argument("--run-audit", dest="run_audit", action="store_true", default=True)
    parser.add_argument("--no-run-audit", dest="run_audit", action="store_false")
    parser.add_argument(
        "--docker-service",
        default=None,
        help="Run the smoke inside a compose service, usually 'worker', so container ffmpeg/ffprobe are used.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run_video_e2e(args: argparse.Namespace) -> str:
    if args.video is None:
        raise RuntimeError("--video is required for video E2E")
    mode = args.mode or "high_quality"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "e2e_real_video.py"),
        "--video",
        str(args.video),
        "--backend-url",
        str(args.backend_url),
        "--mode",
        mode,
        "--normal-count",
        str(args.normal_count),
        "--short-count",
        str(args.short_count),
        "--timeout",
        str(args.timeout),
        "--burn-subtitles",
        "true",
        "--openai-candidate-limit",
        str(args.openai_candidate_limit),
    ]
    if mode == "high_quality":
        command.extend(
            [
                "--use-openai-scoring",
                "true",
                "--ensure-selected-openai-scored",
                "true",
                "--openai-fallback-to-rule-score",
                "true",
            ]
        )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"real video E2E failed with exit code {completed.returncode}")
    match = re.search(r"created job:\s*(job_[A-Za-z0-9]+)", completed.stdout)
    if match is None:
        raise RuntimeError("could not find created job id in E2E output")
    return match.group(1)


def run_audit_report(job_id: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "audit_outputs.py"),
        "--job-id",
        job_id,
        "--format",
        "both",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"audit_outputs.py failed with exit code {completed.returncode}")


def run_in_docker(args: argparse.Namespace) -> int:
    service = str(args.docker_service)
    if not args.output_job_id:
        args.output_job_id = f"{args.source_job_id}_task35c_overlay_burnin_{int(time.time())}"
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
        "--no-run-audit",
    ]
    if args.mode:
        forwarded.extend(["--mode", str(args.mode)])
    if args.output_job_id:
        forwarded.extend(["--output-job-id", str(args.output_job_id)])
    if args.input_video:
        forwarded.extend(["--input-video", container_path_from_host_storage(Path(args.input_video))])
    if args.require_overlay_title:
        forwarded.append("--require-overlay-title")
    if args.force_overlay_title:
        forwarded.extend(["--force-overlay-title", str(args.force_overlay_title)])
    if not args.extract_short_frames:
        forwarded.append("--no-extract-short-frames")

    script = "/app/storage/temp/smoke_subtitle_burn_in.py"
    command = "AUTOCLIPPER_ROOT=/app python " + shlex.quote(script)
    command += " " + " ".join(shlex.quote(value) for value in forwarded)
    completed = subprocess.run(["docker", "compose", "exec", "-T", service, "sh", "-lc", command], cwd=ROOT)
    if completed.returncode == 0 and args.run_audit:
        run_audit_report(str(args.output_job_id))
    return int(completed.returncode)


def run(args: argparse.Namespace) -> int:
    if args.video is not None:
        if os.environ.get("AUTOCLIPPER_ROOT") == "/app":
            raise RuntimeError("--video mode must be started from the host, not inside the worker container")
        args.source_job_id = run_video_e2e(args)
        args.video = None
        if not args.output_job_id:
            args.output_job_id = f"{args.source_job_id}_task35c_overlay_burnin"
        if args.mode == "high_quality":
            args.require_overlay_title = True

    if args.docker_service:
        return run_in_docker(args)

    source_job_id = str(args.source_job_id)
    output_job_id = args.output_job_id or f"{source_job_id}_task35c_overlay_burnin_{int(time.time())}"
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
    subset = apply_overlay_title_policy(
        subset,
        require_overlay_title=bool(args.require_overlay_title or args.mode == "high_quality"),
        force_overlay_title=args.force_overlay_title,
    )
    source_overlay_titles = {
        str(clip.get("id")): clip.get("source_overlay_title")
        for clip in subset["shorts"]
        if clip.get("source_overlay_title") is not None
    }
    normal_candidates, short_candidates = candidates_from_subset(subset)
    if not normal_candidates or not short_candidates:
        raise RuntimeError("smoke requires at least one normal and one short candidate")

    transcript_segments = [TranscriptSegment(**segment) for segment in transcript_payload]
    normal_dir = output_dir / "normal"
    shorts_dir = output_dir / "shorts"
    normal_subtitle_dir = output_dir / "subtitles" / "normal"
    short_subtitle_dir = output_dir / "subtitles" / "shorts"
    frames_dir = output_dir / "audit_frames"
    normal_dir.mkdir(parents=True, exist_ok=True)
    shorts_dir.mkdir(parents=True, exist_ok=True)
    normal_subtitle_dir.mkdir(parents=True, exist_ok=True)
    short_subtitle_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    write_json(output_dir / "selected_clips.json", subset)
    write_json(output_dir / "transcript_segments.json", transcript_payload)
    for filename in [
        "openai_scoring_summary.json",
        "transcript_summary.json",
        "candidate_summary.json",
        "selected_clips_summary.json",
    ]:
        source_file = source_dir / filename
        if source_file.is_file():
            shutil.copy2(source_file, output_dir / filename)
    write_json(
        output_dir / "selected_clips_summary.json",
        {
            "selected_normal_count": len(normal_candidates),
            "selected_short_count": len(short_candidates),
            "requested_normal_count": args.normal_count,
            "requested_short_count": args.short_count,
            "shorts_with_overlay_title": sum(1 for candidate in short_candidates if candidate.overlay_title),
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
    ass_inspections: list[dict[str, Any]] = []
    extracted_frames: list[dict[str, str]] = []

    for index, candidate in enumerate(normal_candidates, start=1):
        try:
            subtitle_path = normal_subtitle_dir / f"normal_{index:02d}.ass"
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
                "subtitle_path": container_output_path(
                    output_job_id,
                    "subtitles",
                    "normal",
                    subtitle_path.name,
                ),
            }
            write_json(normal_dir / f"normal_{index:02d}.json", metadata)
            rendered.append({"candidate_id": candidate.id, "type": "normal", **metadata})
        except Exception as exc:
            failures.append({"candidate_id": candidate.id, "type": "normal", "error": str(exc)})

    for index, candidate in enumerate(short_candidates, start=1):
        try:
            layout = SubtitleLayout.short()
            subtitle_path = short_subtitle_dir / f"short_{index:02d}.ass"
            output_path = shorts_dir / f"short_{index:02d}.mp4"
            write_ass_for_candidate(
                candidate,
                transcript_segments,
                subtitle_path,
                layout=layout,
                top_title=candidate.overlay_title,
            )
            ass_inspection = inspect_ass_layout(subtitle_path, layout)
            if not ass_inspection.safe_vertical_positions:
                raise RuntimeError(f"unsafe title/subtitle ASS layout: {ass_inspection}")
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
            frame_path = None
            if args.extract_short_frames:
                timestamp = min(max(1.0, candidate.duration / 2), max(0.1, candidate.duration - 0.5))
                frame_path = extract_frame(
                    rendered_path,
                    frames_dir / f"short_{index:02d}.png",
                    timestamp_seconds=timestamp,
                    ffmpeg_bin=args.ffmpeg_bin,
                )
                extracted_frames.append(
                    {
                        "candidate_id": candidate.id,
                        "frame_path": container_output_path(output_job_id, "audit_frames", frame_path.name),
                    }
                )
            inspection_payload = {
                "candidate_id": candidate.id,
                "subtitle_path": container_output_path(
                    output_job_id,
                    "subtitles",
                    "shorts",
                    subtitle_path.name,
                ),
                **ass_inspection.__dict__,
            }
            ass_inspections.append(inspection_payload)
            metadata = {
                "id": f"smoke_short_{index:02d}",
                "type": "short",
                "candidate_id": candidate.id,
                "title": candidate.title or f"Short Burn-in {index:02d}",
                "overlay_title": candidate.overlay_title,
                "source_overlay_title": source_overlay_titles.get(candidate.id),
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "score": candidate.final_score or candidate.rule_score or 0.0,
                "strategy": render_result.strategy,
                "width": probe.width,
                "height": probe.height,
                "video_path": container_output_path(output_job_id, "shorts", rendered_path.name),
                "subtitle_path": container_output_path(
                    output_job_id,
                    "subtitles",
                    "shorts",
                    subtitle_path.name,
                ),
                "frame_path": container_output_path(output_job_id, "audit_frames", frame_path.name)
                if frame_path is not None
                else None,
                "ass_layout": inspection_payload,
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
        "ass_layout_inspections": ass_inspections,
        "extracted_frames": extracted_frames,
        "shorts_with_overlay_title": sum(
            1 for item in rendered if item.get("type") == "short" and item.get("overlay_title")
        ),
    }
    write_json(output_dir / "subtitle_burn_in_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.run_audit:
        run_audit_report(output_job_id)
    return 0 if not failures else 1


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
