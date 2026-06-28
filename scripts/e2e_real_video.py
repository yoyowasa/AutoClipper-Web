from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from e2e_summary import print_job_summaries
from e2e_sample_video import _absolute_url, _download, _poll_job, _request_json, _upload_file, _wait_http
from generate_sample_video import _container_storage_path
from smoke_runtime import ROOT, check_services, compose_exec, docker_env


MIN_TRANSCRIPT_CHARS = 20
FIXTURE_TRANSCRIPT_MARKER = "Why automation mistakes matter before launch."


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got: {value}")


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real spoken-video E2E without fixture transcript.")
    parser.add_argument("--video", type=Path, required=True, help="Path to an MP4 with clear spoken audio.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds to wait for job completion.")
    parser.add_argument("--normal-count", type=non_negative_int, default=1)
    parser.add_argument("--short-count", type=non_negative_int, default=1)
    parser.add_argument("--mode", default="low_cost", choices=["low_cost", "fast", "high_quality"])
    parser.add_argument("--profile", default="talk", choices=["auto", "talk", "gameplay", "lecture"])
    parser.add_argument("--burn-subtitles", nargs="?", const=True, default=True, type=parse_bool)
    parser.add_argument("--no-burn-subtitles", dest="burn_subtitles", action="store_false")
    parser.add_argument("--normal-min-duration", type=positive_float, default=90.0)
    parser.add_argument("--normal-max-duration", type=positive_float, default=600.0)
    parser.add_argument("--short-min-duration", type=positive_float, default=20.0)
    parser.add_argument("--short-max-duration", type=positive_float, default=75.0)
    parser.add_argument("--selection-policy", default="fill_requested", choices=["fill_requested", "strict_quality"])
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def resolve_input_video(video_path: Path) -> Path:
    resolved = video_path if video_path.is_absolute() else Path.cwd() / video_path
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"input video not found: {resolved}")
    return resolved


def build_job_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.normal_max_duration < args.normal_min_duration:
        raise RuntimeError("normal-max-duration must be >= normal-min-duration")
    if args.short_max_duration < args.short_min_duration:
        raise RuntimeError("short-max-duration must be >= short-min-duration")

    use_openai_scoring = args.mode == "high_quality"
    return {
        "mode": args.mode,
        "profile": args.profile,
        "normalClipCount": args.normal_count,
        "shortCount": args.short_count,
        "normalMinDuration": args.normal_min_duration,
        "normalMaxDuration": args.normal_max_duration,
        "shortMinDuration": args.short_min_duration,
        "shortMaxDuration": args.short_max_duration,
        "selectionPolicy": args.selection_policy,
        "burnSubtitles": bool(args.burn_subtitles),
        "shortLayout": "auto",
        "useOpenAIScoring": use_openai_scoring,
        "normalizeAudio": False,
        "e2eFixtureTranscript": False,
    }


def job_output_dir(job_id: str) -> Path:
    return ROOT / "storage" / "outputs" / job_id


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def transcript_text_from_segments(segments: Any) -> str:
    if not isinstance(segments, list):
        raise RuntimeError("transcript_segments.json must contain a list")
    texts = [str(segment.get("text", "")).strip() for segment in segments if isinstance(segment, dict)]
    return " ".join(text for text in texts if text).strip()


def validate_transcript_artifact(output_dir: Path, min_chars: int = MIN_TRANSCRIPT_CHARS) -> str:
    transcript_path = output_dir / "transcript_segments.json"
    if not transcript_path.is_file():
        raise RuntimeError(f"transcript_segments.json not found: {transcript_path}")
    segments = read_json(transcript_path)
    text = transcript_text_from_segments(segments)
    if len(text) <= min_chars:
        raise RuntimeError(f"transcript text too short: {len(text)} chars")
    if FIXTURE_TRANSCRIPT_MARKER in text:
        raise RuntimeError("fixture transcript marker was found; e2eFixtureTranscript was not disabled")
    print(f"transcript: {len(segments)} segments, {len(text)} chars")
    print("fixture transcript: disabled and not detected in transcript artifact")
    return text


def _json_list_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    payload = read_json(path)
    return len(payload) if isinstance(payload, list) else None


def _selected_summary(output_dir: Path) -> tuple[int | None, str]:
    path = output_dir / "selected_clips.json"
    if not path.is_file():
        return None, "selected_clips.json missing"
    payload = read_json(path)
    normal = payload.get("normalClips", []) if isinstance(payload, dict) else []
    shorts = payload.get("shorts", []) if isinstance(payload, dict) else []
    rejected = payload.get("rejectedCandidates", []) if isinstance(payload, dict) else []
    reason_counter: Counter[str] = Counter()
    for item in rejected:
        if isinstance(item, dict):
            reason_counter.update(str(reason) for reason in item.get("reasons", []))
    reason_text = ", ".join(f"{reason}={count}" for reason, count in sorted(reason_counter.items()))
    summary = f"selected normal={len(normal)} shorts={len(shorts)} rejected={len(rejected)}"
    if reason_text:
        summary = f"{summary}; rejection reasons: {reason_text}"
    return len(normal) + len(shorts), summary


def _render_failure_summary(output_dir: Path) -> tuple[int | None, str]:
    path = output_dir / "render_failures.json"
    if not path.is_file():
        return None, "render_failures.json missing"
    payload = read_json(path)
    if not isinstance(payload, list):
        return None, "render_failures.json is not a list"
    errors = Counter(str(item.get("error", "unknown")) for item in payload if isinstance(item, dict))
    error_text = ", ".join(f"{error}={count}" for error, count in errors.most_common(3))
    return len(payload), f"render failures={len(payload)}" + (f"; {error_text}" if error_text else "")


def diagnose_no_clips(job_id: str, final_status: dict[str, Any] | None = None) -> str:
    output_dir = job_output_dir(job_id)
    parts: list[str] = []
    error = (final_status or {}).get("error") or {}
    code = str(error.get("code", "")).strip()
    message = str(error.get("message", "")).strip()
    if code:
        parts.append(f"job error={code}: {message}")

    transcript_path = output_dir / "transcript_segments.json"
    if not transcript_path.is_file():
        parts.append("cause=no transcript: transcript_segments.json missing")
        return "; ".join(parts)
    try:
        transcript_text = transcript_text_from_segments(read_json(transcript_path))
    except Exception as exc:
        parts.append(f"cause=no transcript: transcript artifact unreadable: {exc}")
        return "; ".join(parts)
    if len(transcript_text) <= MIN_TRANSCRIPT_CHARS:
        parts.append(f"cause=no transcript: transcript text too short ({len(transcript_text)} chars)")
        return "; ".join(parts)

    candidates_count = _json_list_count(output_dir / "candidates.json")
    if code == "no_candidates_found" or candidates_count == 0:
        parts.append(f"cause=no candidates: candidates={candidates_count}")
        return "; ".join(parts)
    if candidates_count is not None:
        parts.append(f"candidates={candidates_count}")

    selected_count, selected_summary = _selected_summary(output_dir)
    parts.append(selected_summary)
    if selected_count == 0:
        parts.append("cause=quality gate rejection: no selected clips")
        return "; ".join(parts)

    render_failure_count, render_summary = _render_failure_summary(output_dir)
    parts.append(render_summary)
    if code == "no_usable_output" or (render_failure_count and render_failure_count > 0):
        parts.append("cause=render failure: selected clips did not produce usable exports")
        return "; ".join(parts)

    parts.append("cause=unknown: inspect worker logs and job artifacts")
    return "; ".join(parts)


def validate_selected_artifact(output_dir: Path) -> None:
    selected_count, selected_summary = _selected_summary(output_dir)
    if selected_count is None:
        raise RuntimeError(selected_summary)
    if selected_count <= 0:
        raise RuntimeError(f"selected_clips.json has no selected clips: {selected_summary}")
    print(selected_summary)


def probe_downloaded_mp4(path: Path, env: dict[str, str]) -> ProbeResult:
    container_path = _container_storage_path(path)
    output = compose_exec(
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
            container_path,
        ],
        env=env,
    )
    first_line = output.splitlines()[0].strip() if output.strip() else ""
    values = [value.strip() for value in first_line.split(",")]
    if len(values) < 2:
        raise RuntimeError(f"could not parse ffprobe dimensions for {path}: {output}")
    return ProbeResult(width=int(values[0]), height=int(values[1]))


def download_and_probe_outputs(
    *,
    backend_url: str,
    job_id: str,
    results: dict[str, Any],
    env: dict[str, str],
) -> list[tuple[dict[str, Any], Path, ProbeResult]]:
    exports = [*results.get("normalClips", []), *results.get("shorts", [])]
    if not exports:
        raise RuntimeError(f"no output exports returned; {diagnose_no_clips(job_id)}")

    zip_path = ROOT / "storage" / "temp" / f"e2e_real_{job_id}.zip"
    _download(_absolute_url(backend_url, results["zipDownloadUrl"]), zip_path)
    print(f"zip: {zip_path}")

    probed: list[tuple[dict[str, Any], Path, ProbeResult]] = []
    for index, export in enumerate(exports, start=1):
        export_type = str(export.get("type", "export"))
        export_id = str(export.get("id", index))
        output_path = ROOT / "storage" / "temp" / f"e2e_real_{job_id}_{index:02d}_{export_type}_{export_id}.mp4"
        _download(_absolute_url(backend_url, export["downloadUrl"]), output_path)
        probe = probe_downloaded_mp4(output_path, env)
        print(f"{export_type} mp4: {output_path} ({probe.width}x{probe.height})")
        if export_type == "short" and (probe.width, probe.height) != (1080, 1920):
            raise RuntimeError(f"short output must be 1080x1920, got {probe.width}x{probe.height}: {output_path}")
        probed.append((export, output_path, probe))
    return probed


def run_e2e(args: argparse.Namespace) -> int:
    video_path = resolve_input_video(args.video)
    env = docker_env()
    check_services(env)
    _wait_http(f"{args.backend_url}/health", '"status":"ok"')

    settings = build_job_settings(args)
    if settings.get("e2eFixtureTranscript") is not False:
        raise RuntimeError("e2eFixtureTranscript must be false for real spoken-video E2E")
    print("fixture transcript: explicitly disabled")

    upload = _upload_file(f"{args.backend_url}/api/videos/upload", video_path)
    video_id = upload["videoId"]
    print(f"uploaded video: {video_id}")

    job = _request_json(
        f"{args.backend_url}/api/jobs",
        method="POST",
        payload={"videoId": video_id, "settings": settings},
    )
    job_id = job["jobId"]
    print(f"created job: {job_id}")

    final_status = _poll_job(args.backend_url, job_id, args.timeout)
    if final_status["status"] == "failed":
        print_job_summaries(job_id)
        raise RuntimeError(f"job failed; {diagnose_no_clips(job_id, final_status)}")

    output_dir = job_output_dir(job_id)
    validate_transcript_artifact(output_dir)
    results = _request_json(f"{args.backend_url}/api/jobs/{job_id}/results")
    exports = [*results.get("normalClips", []), *results.get("shorts", [])]
    if not exports:
        print_job_summaries(job_id)
        raise RuntimeError(f"job completed with no clips; {diagnose_no_clips(job_id, final_status)}")

    validate_selected_artifact(output_dir)
    print_job_summaries(job_id)
    download_and_probe_outputs(backend_url=args.backend_url, job_id=job_id, results=results, env=env)
    print(f"job outputs: {output_dir}")
    print("REAL VIDEO E2E PASSED")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    args.backend_url = args.backend_url.rstrip("/")
    try:
        return run_e2e(args)
    except Exception as exc:
        print(f"REAL VIDEO E2E FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
