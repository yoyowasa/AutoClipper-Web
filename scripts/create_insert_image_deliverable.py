from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


"""Create an optional insert-image preview MP4 from completed job artifacts.

This helper is separate from the production AutoClipper pipeline. It copies
local image assets into a job output subfolder, overlays them on an existing
rendered clip using a base filter graph, and optionally renders a preview MP4.
"""


ROOT = Path(__file__).resolve().parents[1]
APP_PREFIX = "/app"


@dataclass(frozen=True)
class InsertImage:
    source: Path
    asset_name: str
    start: float
    end: float
    label: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a preview MP4 with full-screen insert images before ASS burn-in.",
    )
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--source-container-path",
        default=None,
        help=(
            "Input MP4 path inside the Docker worker container, for example "
            "/app/storage/outputs/job_x/shorts/short_01.mp4. Required unless --dry-run is used."
        ),
    )
    parser.add_argument("--base-filter", type=Path, required=True)
    parser.add_argument("--subtitle", type=Path, required=True)
    parser.add_argument("--output-name", default="short_01_insert_p0.mp4")
    parser.add_argument("--output-subdir", default="inserts_p0")
    parser.add_argument("--font-dir-container-path", default="/app/storage/fonts")
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional output duration. If omitted, the source video duration is probed before rendering.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Copy assets and write filter/manifest, but skip ffmpeg rendering and frame extraction.",
    )
    parser.add_argument("--docker-service", default="worker", help="docker compose service used for ffmpeg/ffprobe.")
    parser.add_argument(
        "--image",
        action="append",
        nargs=5,
        metavar=("PATH", "ASSET_NAME", "START", "END", "LABEL"),
        required=True,
        help="Insert image tuple. Example: --image .\\local.png insert_01.png 0.95 3.02 label",
    )
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def validate_args(args: argparse.Namespace) -> None:
    if not args.dry_run and not args.source_container_path:
        raise ValueError("--source-container-path is required unless --dry-run is used.")
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration must be greater than 0.")
    if args.output_name.endswith((".ass", ".json", ".txt")):
        raise ValueError("--output-name must be a rendered media filename, usually .mp4.")


def local_to_container(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"path must be inside workspace: {resolved}") from exc
    return f"{APP_PREFIX}/{relative.as_posix()}"


def parse_insert_images(raw_images: list[list[str]]) -> list[InsertImage]:
    inserts: list[InsertImage] = []
    for raw_path, asset_name, start, end, label in raw_images:
        source = Path(raw_path)
        if not source.exists():
            raise FileNotFoundError(source)
        if Path(asset_name).name != asset_name:
            raise ValueError(f"asset name must not include directories: {asset_name}")
        if Path(asset_name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(f"unsupported image asset extension: {asset_name}")
        start_seconds = float(start)
        end_seconds = float(end)
        if end_seconds <= start_seconds:
            raise ValueError(f"end must be greater than start for {label}")
        inserts.append(
            InsertImage(
                source=source,
                asset_name=asset_name,
                start=start_seconds,
                end=end_seconds,
                label=label,
            )
        )
    return inserts


def read_base_filter(base_filter: Path) -> list[str]:
    lines = [line.strip() for line in base_filter.read_text(encoding="utf-8").splitlines() if line.strip()]
    kept: list[str] = []
    removed_ass = False
    for line in lines:
        if line.startswith("[vcat]ass="):
            removed_ass = True
            continue
        kept.append(line)
    if not removed_ass:
        raise ValueError("base filter did not contain the final [vcat]ass line")
    return kept


def build_filter(
    base_lines: list[str],
    inserts: list[InsertImage],
    asset_paths: list[Path],
    subtitle_container_path: str,
    font_dir_container_path: str,
) -> str:
    lines = [line if line.endswith(";") else f"{line};" for line in base_lines]
    previous = "vcat"
    for index, (insert, _asset_path) in enumerate(zip(inserts, asset_paths, strict=True), start=1):
        fade_duration = min(0.15, max(0.04, (insert.end - insert.start) / 5))
        fade_out_start = max(insert.start, insert.end - fade_duration)
        lines.append(
            f"[{index}:v]"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=white,"
            "format=rgba,"
            f"fade=t=in:st={insert.start:.3f}:d={fade_duration:.3f}:alpha=1,"
            f"fade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f}:alpha=1"
            f"[ins{index}];"
        )
        current = f"vins{index}"
        lines.append(
            f"[{previous}][ins{index}]"
            f"overlay=x=0:y=0:enable='between(t,{insert.start:.3f},{insert.end:.3f})'"
            f"[{current}];"
        )
        previous = current
    ass_filter = f"ass='{subtitle_container_path}'"
    if font_dir_container_path:
        ass_filter += f":fontsdir='{font_dir_container_path}'"
    lines.append(f"[{previous}]{ass_filter}[vout]")
    return "\n".join(lines) + "\n"


def build_ffmpeg_command(
    source_container_path: str,
    asset_container_paths: list[str],
    filter_container_path: str,
    output_container_path: str,
    duration: float,
    *,
    docker_service: str,
) -> list[str]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        docker_service,
        "ffmpeg",
        "-y",
        "-i",
        source_container_path,
    ]
    for asset_path in asset_container_paths:
        command.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", asset_path])
    command.extend(
        [
            "-filter_complex_script",
            filter_container_path,
            "-map",
            "[vout]",
            "-map",
            "[acat]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-r",
            "25",
            "-t",
            f"{duration:.3f}",
            output_container_path,
        ]
    )
    return command


def run_ffmpeg(
    source_container_path: str,
    asset_container_paths: list[str],
    filter_container_path: str,
    output_container_path: str,
    duration: float,
    *,
    docker_service: str,
) -> None:
    command = [
        *build_ffmpeg_command(
            source_container_path,
            asset_container_paths,
            filter_container_path,
            output_container_path,
            duration,
            docker_service=docker_service,
        )
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def build_ffprobe_command(video_container_path: str, *, docker_service: str) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        docker_service,
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        video_container_path,
    ]


def run_ffprobe(video_container_path: str, *, docker_service: str) -> dict[str, object]:
    command = build_ffprobe_command(video_container_path, docker_service=docker_service)
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def duration_from_probe(probe: dict[str, object]) -> float:
    try:
        duration = float(probe["format"]["duration"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ffprobe output did not include format.duration") from exc
    if duration <= 0:
        raise ValueError("source video duration must be greater than 0")
    return duration


def build_extract_frame_command(
    output_container_path: str,
    frame_container_path: str,
    seconds: float,
    *,
    docker_service: str,
) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        docker_service,
        "ffmpeg",
        "-y",
        "-ss",
        f"{seconds:.3f}",
        "-i",
        output_container_path,
        "-frames:v",
        "1",
        "-update",
        "1",
        frame_container_path,
    ]


def build_contact_sheet_command(frame_paths: list[str], contact_container_path: str, *, docker_service: str) -> list[str]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        docker_service,
        "ffmpeg",
        "-y",
    ]
    if len(frame_paths) == 1:
        command.extend(
            [
                "-i",
                frame_paths[0],
                "-vf",
                "scale=360:640",
                "-frames:v",
                "1",
                "-update",
                "1",
                contact_container_path,
            ]
        )
        return command

    for frame_path in frame_paths:
        command.extend(["-i", frame_path])
    cols = 2
    scaled = []
    layout = []
    for index in range(len(frame_paths)):
        scaled.append(f"[{index}:v]scale=360:640[f{index}]")
        x = (index % cols) * 360
        y = (index // cols) * 640
        layout.append(f"{x}_{y}")
    stack_inputs = "".join(f"[f{index}]" for index in range(len(frame_paths)))
    command.extend(
        [
            "-filter_complex",
            ";".join(scaled) + f";{stack_inputs}xstack=inputs={len(frame_paths)}:layout={'|'.join(layout)}[v]",
            "-map",
            "[v]",
            "-frames:v",
            "1",
            "-update",
            "1",
            contact_container_path,
        ]
    )
    return command


def extract_contact_sheet(
    output_dir: Path,
    output_container_path: str,
    output_subdir_container: str,
    inserts: list[InsertImage],
    *,
    docker_service: str,
) -> Path:
    frame_times = [(insert.start + insert.end) / 2 for insert in inserts]
    frame_paths = []
    for index, seconds in enumerate(frame_times, start=1):
        frame_path = output_dir / f"insert_frame_{index:02d}.jpg"
        frame_container_path = f"{output_subdir_container}/{frame_path.name}"
        command = build_extract_frame_command(
            output_container_path,
            frame_container_path,
            seconds,
            docker_service=docker_service,
        )
        subprocess.run(command, cwd=ROOT, check=True)
        frame_paths.append(frame_container_path)

    contact_path = output_dir / "insert_contact_sheet.jpg"
    contact_container_path = f"{output_subdir_container}/{contact_path.name}"
    command = build_contact_sheet_command(frame_paths, contact_container_path, docker_service=docker_service)
    subprocess.run(command, cwd=ROOT, check=True)
    return contact_path


def main() -> None:
    args = parse_args()
    inserts = parse_insert_images(args.image)

    job_dir = ROOT / "storage" / "outputs" / args.job_id
    output_dir = job_dir / args.output_subdir
    assets_dir = output_dir / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    asset_paths: list[Path] = []
    for insert in inserts:
        asset_path = assets_dir / insert.asset_name
        shutil.copy2(insert.source, asset_path)
        asset_paths.append(asset_path)

    subtitle_path = args.subtitle.resolve()
    filter_path = output_dir / "filter_complex_insert_p0.txt"
    output_path = output_dir / args.output_name

    filter_document = build_filter(
        read_base_filter(args.base_filter),
        inserts,
        asset_paths,
        local_to_container(subtitle_path),
        args.font_dir_container_path,
    )
    filter_path.write_text(filter_document, encoding="utf-8")

    asset_container_paths = [local_to_container(path) for path in asset_paths]
    output_container_path = local_to_container(output_path)
    output_subdir_container = local_to_container(output_dir)
    source_probe = None
    output_probe = None
    contact_path = None
    render_duration = args.duration
    if not args.dry_run:
        source_probe = run_ffprobe(args.source_container_path, docker_service=args.docker_service)
        if render_duration is None:
            render_duration = duration_from_probe(source_probe)
        run_ffmpeg(
            args.source_container_path,
            asset_container_paths,
            local_to_container(filter_path),
            output_container_path,
            render_duration,
            docker_service=args.docker_service,
        )
        output_probe = run_ffprobe(output_container_path, docker_service=args.docker_service)
        contact_path = extract_contact_sheet(
            output_dir,
            output_container_path,
            output_subdir_container,
            inserts,
            docker_service=args.docker_service,
        )

    manifest = {
        "output_path": str(output_path),
        "contact_sheet_path": str(contact_path) if contact_path is not None else None,
        "filter_path": str(filter_path),
        "dry_run": args.dry_run,
        "source_container_path": args.source_container_path,
        "subtitle_path": str(subtitle_path),
        "font_dir_container_path": args.font_dir_container_path,
        "duration": render_duration,
        "inserts": [
            {
                "label": insert.label,
                "start": insert.start,
                "end": insert.end,
                "asset_path": str(asset_path),
            }
            for insert, asset_path in zip(inserts, asset_paths, strict=True)
        ],
        "source_probe": source_probe,
        "output_probe": output_probe,
    }
    (output_dir / "insert_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.dry_run:
        print(output_dir / "insert_manifest.json")
        return
    print(output_path)


if __name__ == "__main__":
    main()
