from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKER_BIN_DIR = Path(r"C:\Program Files\Docker\Docker\resources\bin")
REQUIRED_SERVICES = {"backend", "frontend", "worker", "redis"}


def docker_env() -> dict[str, str]:
    env = os.environ.copy()
    current_path = env.get("PATH") or env.get("Path") or ""
    docker = shutil.which("docker", path=current_path)
    if shutil.which("docker", path=current_path) is None and DOCKER_BIN_DIR.is_dir():
        current_path = f"{DOCKER_BIN_DIR}{os.pathsep}{current_path}"
        env["PATH"] = current_path
        env["Path"] = current_path
        docker = shutil.which("docker", path=current_path)
    if docker is None:
        raise RuntimeError("docker executable not found")
    env["AUTOCLIPPER_DOCKER_EXE"] = docker
    return env


def run(args: list[str], *, env: dict[str, str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(args)}")
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def compose(args: list[str], *, env: dict[str, str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return run([env["AUTOCLIPPER_DOCKER_EXE"], "compose", *args], env=env, capture=capture)


def compose_exec(service: str, args: list[str], *, env: dict[str, str]) -> str:
    completed = compose(["exec", "-T", service, *args], env=env)
    output = completed.stdout.strip()
    if output:
        print(output)
    return output


def check_http(url: str, expected_text: str | None = None) -> None:
    print(f"$ GET {url}")
    with urllib.request.urlopen(url, timeout=15) as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        if expected_text is not None and expected_text not in body:
            raise RuntimeError(f"{url} did not contain expected text: {expected_text}")
        print(f"HTTP {response.status}, {len(body)} bytes")


def parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            raise RuntimeError(f"Unexpected runtime settings line: {line}")
        values[key] = value
    return values


def check_services(env: dict[str, str]) -> None:
    output = compose(["ps", "--services", "--status", "running"], env=env).stdout
    running = {line.strip() for line in output.splitlines() if line.strip()}
    missing = sorted(REQUIRED_SERVICES - running)
    if missing:
        raise RuntimeError(f"Missing running services: {', '.join(missing)}")
    print(f"running services: {', '.join(sorted(running))}")


def check_runtime_paths(env: dict[str, str]) -> None:
    code = (
        "from app.config import get_settings; "
        "from app.storage.paths import get_storage_paths; "
        "s=get_settings(); p=get_storage_paths(); "
        "print('DATABASE_URL='+s.database_url); "
        "print('STORAGE_ROOT='+str(p.root)); "
        "print('UPLOADS='+str(p.uploads)); "
        "print('TEMP='+str(p.temp)); "
        "print('OUTPUTS='+str(p.outputs))"
    )
    backend = parse_key_values(compose_exec("backend", ["python", "-c", code], env=env))
    worker = parse_key_values(compose_exec("worker", ["python", "-c", code], env=env))
    if backend != worker:
        raise RuntimeError(f"backend/worker runtime paths differ:\nbackend={backend}\nworker={worker}")
    expected = {
        "DATABASE_URL": "sqlite:////app/storage/autoclipper.db",
        "STORAGE_ROOT": "/app/storage",
        "UPLOADS": "/app/storage/uploads",
        "TEMP": "/app/storage/temp",
        "OUTPUTS": "/app/storage/outputs",
    }
    for key, value in expected.items():
        if backend.get(key) != value:
            raise RuntimeError(f"{key} expected {value}, got {backend.get(key)}")
    print("backend/worker runtime paths match")


def check_shared_storage(env: dict[str, str]) -> None:
    write_markers = (
        "set -eu; "
        "for d in uploads temp outputs; do "
        "mkdir -p /app/storage/$d; "
        "printf smoke-runtime > /app/storage/$d/smoke_runtime_marker.txt; "
        "done"
    )
    read_markers = (
        "set -eu; "
        "for d in uploads temp outputs; do "
        "test \"$(cat /app/storage/$d/smoke_runtime_marker.txt)\" = smoke-runtime; "
        "done; "
        "test -f /app/storage/autoclipper.db"
    )
    cleanup_markers = (
        "rm -f "
        "/app/storage/uploads/smoke_runtime_marker.txt "
        "/app/storage/temp/smoke_runtime_marker.txt "
        "/app/storage/outputs/smoke_runtime_marker.txt"
    )
    compose_exec("backend", ["sh", "-lc", write_markers], env=env)
    compose_exec("worker", ["sh", "-lc", read_markers], env=env)
    compose_exec("backend", ["sh", "-lc", cleanup_markers], env=env)
    print("backend/worker share database and storage mounts")


def check_ffmpeg(env: dict[str, str]) -> None:
    for service in ("backend", "worker"):
        for binary in ("ffmpeg", "ffprobe"):
            output = compose_exec(service, [binary, "-version"], env=env)
            first_line = output.splitlines()[0] if output else ""
            if binary not in first_line:
                raise RuntimeError(f"{binary} check failed in {service}: {first_line}")
            print(f"{service}: {first_line}")


def check_generated_video(env: dict[str, str], *, keep_test_video: bool) -> None:
    video_path = "/app/storage/temp/smoke_runtime/smoke.mp4"
    generate = (
        "set -eu; "
        "mkdir -p /app/storage/temp/smoke_runtime; "
        "ffmpeg -hide_banner -loglevel error -y "
        "-f lavfi -i testsrc=size=128x72:rate=10 "
        "-f lavfi -i sine=frequency=1000:sample_rate=16000 "
        "-t 1 -shortest -pix_fmt yuv420p -c:v libx264 -c:a aac "
        f"{video_path}; "
        f"test -s {video_path}; "
        f"ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 {video_path}"
    )
    probe_from_worker = (
        "set -eu; "
        f"test -s {video_path}; "
        f"ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 {video_path}"
    )
    compose_exec("backend", ["sh", "-lc", generate], env=env)
    compose_exec("worker", ["sh", "-lc", probe_from_worker], env=env)
    if keep_test_video:
        print(f"kept generated video at storage/temp/smoke_runtime/smoke.mp4")
    else:
        compose_exec("backend", ["sh", "-lc", "rm -rf /app/storage/temp/smoke_runtime"], env=env)
        print("removed generated smoke video")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AutoClipper docker compose runtime.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--skip-video", action="store_true", help="Skip generated MP4 probe smoke.")
    parser.add_argument("--keep-test-video", action="store_true", help="Keep generated MP4 under storage/temp/smoke_runtime.")
    args = parser.parse_args()

    env = docker_env()
    try:
        run([env["AUTOCLIPPER_DOCKER_EXE"], "--version"], env=env)
        run([env["AUTOCLIPPER_DOCKER_EXE"], "compose", "version"], env=env)
        check_services(env)
        check_http(f"{args.backend_url}/health", '"status":"ok"')
        check_http(args.frontend_url, "AutoClipper")
        check_runtime_paths(env)
        check_shared_storage(env)
        check_ffmpeg(env)
        if not args.skip_video:
            check_generated_video(env, keep_test_video=args.keep_test_video)
    except Exception as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 1

    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
