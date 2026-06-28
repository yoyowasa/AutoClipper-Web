from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from smoke_runtime import ROOT, compose_exec, docker_env


DEFAULT_OUTPUT = ROOT / "storage" / "temp" / "e2e_sample.mp4"


def _container_storage_path(host_path: Path) -> str:
    storage_root = (ROOT / "storage").resolve()
    resolved = host_path.resolve()
    try:
        relative = resolved.relative_to(storage_root)
    except ValueError as exc:
        raise RuntimeError(f"output must be under {storage_root}") from exc
    return f"/app/storage/{relative.as_posix()}"


def generate_sample_video(output: Path = DEFAULT_OUTPUT, duration: float = 25.0) -> Path:
    if duration < 15 or duration > 30:
        raise RuntimeError("duration must be between 15 and 30 seconds")

    host_output = output if output.is_absolute() else ROOT / output
    container_output = _container_storage_path(host_output)
    container_dir = str(Path(container_output).parent).replace("\\", "/")
    env = docker_env()
    quoted_output = shlex.quote(container_output)
    quoted_dir = shlex.quote(container_dir)
    command = (
        "set -eu; "
        f"mkdir -p {quoted_dir}; "
        "ffmpeg -hide_banner -loglevel error -y "
        "-f lavfi -i testsrc=size=320x180:rate=10 "
        "-f lavfi -i sine=frequency=1000:sample_rate=16000 "
        f"-t {duration:.3f} -shortest -pix_fmt yuv420p -c:v libx264 -c:a aac "
        f"{quoted_output}; "
        f"test -s {quoted_output}; "
        "ffprobe -v error "
        "-select_streams v:0 "
        "-show_entries stream=width,height,r_frame_rate "
        f"-of csv=p=0 {quoted_output}; "
        "ffprobe -v error "
        "-show_entries format=duration "
        f"-of default=nw=1:nk=1 {quoted_output}"
    )
    compose_exec("backend", ["sh", "-lc", command], env=env)
    if not host_output.is_file():
        raise RuntimeError(f"sample video was not created: {host_output}")
    print(f"sample video: {host_output}")
    return host_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a tiny synthetic MP4 via docker compose ffmpeg.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--duration", type=float, default=25.0)
    args = parser.parse_args()

    try:
        generate_sample_video(output=args.output, duration=args.duration)
    except Exception as exc:
        print(f"SAMPLE VIDEO GENERATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
