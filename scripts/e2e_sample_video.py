from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from e2e_summary import print_job_summaries
from generate_sample_video import DEFAULT_OUTPUT, _container_storage_path, generate_sample_video
from smoke_runtime import ROOT, check_http, check_services, compose, compose_exec, docker_env


DEFAULT_DOWNLOAD = ROOT / "storage" / "temp" / "e2e_download.mp4"
DEFAULT_ZIP_DOWNLOAD = ROOT / "storage" / "temp" / "e2e_download.zip"
CLEAR_FAILURE_CODES = {"no_candidates_found", "no_usable_output", "transcription_empty"}


def _request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc


def _upload_file(url: str, file_path: Path) -> dict[str, Any]:
    boundary = f"----autoclipper-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(file_path.name)[0] or "video/mp4"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8"),
            file_path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upload failed with HTTP {exc.code}: {body}") from exc


def _download(url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"download failed with HTTP {exc.code}: {body}") from exc
    if not data:
        raise RuntimeError(f"download was empty: {url}")
    output_path.write_bytes(data)
    return output_path


def _absolute_url(base_url: str, value: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", value)


def _poll_job(backend_url: str, job_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        payload = _request_json(f"{backend_url}/api/jobs/{job_id}")
        status = str(payload["status"])
        if status != last_status:
            print(f"job {job_id}: {status} {payload.get('progress')}%")
            last_status = status
        if status in {"completed", "failed"}:
            return payload
        time.sleep(2)
    raise RuntimeError(f"job did not finish within {timeout_seconds} seconds: {job_id}")


def _wait_http(url: str, expected_text: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check_http(url, expected_text)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"{url} was not ready within {timeout_seconds} seconds: {last_error}")


def run_e2e(
    *,
    backend_url: str,
    frontend_url: str,
    sample_path: Path,
    duration: float,
    timeout_seconds: int,
    start_compose: bool,
) -> int:
    env = docker_env()
    if start_compose:
        compose(["up", "-d", "--build"], env=env, capture=False)
    check_services(env)
    _wait_http(f"{backend_url}/health", '"status":"ok"')
    _wait_http(frontend_url, "AutoClipper")

    sample = generate_sample_video(output=sample_path, duration=duration)
    upload = _upload_file(f"{backend_url}/api/videos/upload", sample)
    video_id = upload["videoId"]
    print(f"uploaded video: {video_id}")

    job = _request_json(
        f"{backend_url}/api/jobs",
        method="POST",
        payload={
            "videoId": video_id,
            "settings": {
                "e2eFixtureTranscript": True,
                "normalClipCount": 0,
                "shortCount": 1,
                "shortMinDuration": 20,
                "shortMaxDuration": 25,
                "shortStepSeconds": 5,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": True,
                "normalizeAudio": False,
                "shortLayout": "center_crop",
            },
        },
    )
    job_id = job["jobId"]
    print(f"created job: {job_id}")

    final_status = _poll_job(backend_url, job_id, timeout_seconds)
    if final_status["status"] == "failed":
        print_job_summaries(job_id)
        error = final_status.get("error") or {}
        code = str(error.get("code", "unknown"))
        message = str(error.get("message", ""))
        if code in CLEAR_FAILURE_CODES:
            print(f"E2E CLEAR FAILURE: {code}: {message}")
            return 0
        raise RuntimeError(f"job failed: {code}: {message}")

    results = _request_json(f"{backend_url}/api/jobs/{job_id}/results")
    exports = [*results["normalClips"], *results["shorts"]]
    if not exports:
        print_job_summaries(job_id)
        raise RuntimeError("job completed but returned no output exports")

    print_job_summaries(job_id)
    first_export = exports[0]
    output_mp4 = _download(_absolute_url(backend_url, first_export["downloadUrl"]), DEFAULT_DOWNLOAD)
    container_mp4 = _container_storage_path(output_mp4)
    probe = compose_exec(
        "worker",
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            container_mp4,
        ],
        env=env,
    )
    if not probe.strip():
        raise RuntimeError("ffprobe returned no stream dimensions for downloaded MP4")

    zip_path = _download(_absolute_url(backend_url, results["zipDownloadUrl"]), DEFAULT_ZIP_DOWNLOAD)
    print(f"output mp4: {output_mp4}")
    print(f"zip: {zip_path}")
    print(f"job outputs: {ROOT / 'storage' / 'outputs' / job_id}")
    print("E2E PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real docker/API E2E with a generated sample MP4.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--sample-path", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--duration", type=float, default=25.0)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--start", action="store_true", help="Run docker compose up -d --build first.")
    args = parser.parse_args()

    try:
        return run_e2e(
            backend_url=args.backend_url.rstrip("/"),
            frontend_url=args.frontend_url.rstrip("/"),
            sample_path=args.sample_path,
            duration=args.duration,
            timeout_seconds=args.timeout_seconds,
            start_compose=args.start,
        )
    except Exception as exc:
        print(f"E2E FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
