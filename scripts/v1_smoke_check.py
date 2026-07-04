from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SUFFIXES = (".ass", ".srt", ".vtt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run lightweight AutoClipper v1 release smoke checks.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--job-id", help="Completed job id to validate results, downloads, and local output layout.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional path to write JSON summary.")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def join_backend_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    detail: str,
    *,
    data: dict[str, Any] | None = None,
) -> None:
    checks.append({"name": name, "status": status, "detail": detail, "data": data or {}})


def fetch_bytes(url: str, *, timeout: float, max_bytes: int = 4096) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "autoclipper-v1-smoke/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return int(response.status), response.read(max_bytes), headers


def fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    status, body, _headers = fetch_bytes(url, timeout=timeout, max_bytes=2_000_000)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("response JSON must be an object")
    return payload


def output_dir_for_job(job_id: str, *, root: Path = ROOT) -> Path:
    return root / "storage" / "outputs" / job_id


def scan_sidecar_autoload_risks(output_dir: Path) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if not output_dir.is_dir():
        return risks
    for video_path in sorted(output_dir.rglob("*.mp4")):
        for suffix in SIDECAR_SUFFIXES:
            subtitle_path = video_path.with_suffix(suffix)
            if subtitle_path.is_file():
                risks.append({"video_path": str(video_path), "subtitle_path": str(subtitle_path)})
    return risks


def first_clip(results: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("normalClips", "shorts"):
        clips = results.get(key)
        if isinstance(clips, list) and clips:
            clip = clips[0]
            if isinstance(clip, dict):
                return clip
    return None


def clip_counts(results: dict[str, Any]) -> dict[str, int]:
    return {
        "normal": len(results.get("normalClips") or []),
        "short": len(results.get("shorts") or []),
    }


def check_backend_health(args: argparse.Namespace, checks: list[dict[str, Any]]) -> None:
    url = join_backend_url(args.backend_url, "/health")
    try:
        payload = fetch_json(url, timeout=args.timeout)
        if payload.get("status") != "ok":
            add_check(checks, "backend_health", "fail", f"unexpected payload: {payload}")
            return
        add_check(checks, "backend_health", "pass", "backend /health returned ok")
    except Exception as exc:
        add_check(checks, "backend_health", "fail", str(exc))


def check_frontend(args: argparse.Namespace, checks: list[dict[str, Any]]) -> None:
    if args.skip_frontend:
        add_check(checks, "frontend_reachable", "info", "skipped")
        return
    try:
        status, body, _headers = fetch_bytes(args.frontend_url, timeout=args.timeout)
        if status != 200:
            add_check(checks, "frontend_reachable", "fail", f"HTTP {status}")
            return
        add_check(checks, "frontend_reachable", "pass", f"HTTP 200, {len(body)} bytes read")
    except Exception as exc:
        add_check(checks, "frontend_reachable", "fail", str(exc))


def check_local_scripts(checks: list[dict[str, Any]]) -> None:
    required = [
        ROOT / "scripts" / "e2e_real_video.py",
        ROOT / "scripts" / "audit_outputs.py",
        ROOT / "scripts" / "check_subtitle_sidecar_risk.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        add_check(checks, "local_smoke_scripts", "fail", "required scripts missing", data={"missing": missing})
        return
    add_check(checks, "local_smoke_scripts", "pass", "required smoke scripts exist")


def check_job_results(args: argparse.Namespace, checks: list[dict[str, Any]]) -> None:
    if not args.job_id:
        add_check(checks, "job_results", "info", "no --job-id supplied")
        return

    try:
        results = fetch_json(join_backend_url(args.backend_url, f"/api/jobs/{args.job_id}/results"), timeout=args.timeout)
    except Exception as exc:
        add_check(checks, "job_results", "fail", str(exc))
        return

    counts = clip_counts(results)
    if counts["normal"] + counts["short"] <= 0:
        add_check(checks, "job_results", "fail", "results contain no generated clips", data=counts)
        return
    add_check(checks, "job_results", "pass", "results API returned generated clips", data=counts)

    audit_summary = results.get("auditSummary")
    add_check(
        checks,
        "job_audit_summary",
        "pass" if isinstance(audit_summary, dict) else "info",
        "auditSummary present" if isinstance(audit_summary, dict) else "auditSummary not present",
    )

    clip = first_clip(results)
    if clip is None:
        add_check(checks, "first_clip_downloads", "fail", "no clip available")
    else:
        check_clip_downloads(args, checks, clip)

    zip_url = results.get("zipDownloadUrl")
    if not isinstance(zip_url, str) or not zip_url:
        add_check(checks, "zip_download", "fail", "zipDownloadUrl missing")
    else:
        check_download_url(args, checks, "zip_download", zip_url, min_bytes=2)

    output_dir = output_dir_for_job(args.job_id)
    if output_dir.is_dir():
        risks = scan_sidecar_autoload_risks(output_dir)
        status = "fail" if risks else "pass"
        detail = f"subtitle sidecar autoload risks: {len(risks)}"
        add_check(checks, "local_sidecar_risk", status, detail, data={"risk_count": len(risks), "risks": risks})
    else:
        add_check(checks, "local_sidecar_risk", "info", f"local output dir not found: {output_dir}")


def check_clip_downloads(args: argparse.Namespace, checks: list[dict[str, Any]], clip: dict[str, Any]) -> None:
    metadata_url = clip.get("metadataUrl")
    subtitle_url = clip.get("subtitleUrl")
    download_url = clip.get("downloadUrl")
    clip_id = str(clip.get("id") or clip.get("candidateId") or "unknown")

    if isinstance(metadata_url, str) and metadata_url:
        try:
            metadata = fetch_json(join_backend_url(args.backend_url, metadata_url), timeout=args.timeout)
            title = metadata.get("title")
            if not isinstance(title, str) or not title.strip():
                add_check(checks, "metadata_download", "fail", f"metadata title missing for {clip_id}")
            else:
                add_check(checks, "metadata_download", "pass", f"metadata downloaded for {clip_id}")
        except Exception as exc:
            add_check(checks, "metadata_download", "fail", str(exc))
    else:
        add_check(checks, "metadata_download", "fail", f"metadataUrl missing for {clip_id}")

    if isinstance(subtitle_url, str) and subtitle_url:
        try:
            status, body, _headers = fetch_bytes(join_backend_url(args.backend_url, subtitle_url), timeout=args.timeout)
            if status == 200 and b"[Script Info]" in body:
                add_check(checks, "subtitle_download", "pass", f"subtitle downloaded for {clip_id}")
            else:
                add_check(checks, "subtitle_download", "fail", f"unexpected subtitle response for {clip_id}")
        except Exception as exc:
            add_check(checks, "subtitle_download", "fail", str(exc))
    else:
        add_check(checks, "subtitle_download", "fail", f"subtitleUrl missing for {clip_id}")

    if isinstance(download_url, str) and download_url:
        check_download_url(args, checks, "mp4_download", download_url, min_bytes=2)
    else:
        add_check(checks, "mp4_download", "fail", f"downloadUrl missing for {clip_id}")


def check_download_url(
    args: argparse.Namespace,
    checks: list[dict[str, Any]],
    name: str,
    path_or_url: str,
    *,
    min_bytes: int,
) -> None:
    try:
        status, body, headers = fetch_bytes(join_backend_url(args.backend_url, path_or_url), timeout=args.timeout)
        content_length = headers.get("content-length")
        length = int(content_length) if content_length and content_length.isdigit() else len(body)
        if status != 200 or length < min_bytes:
            add_check(checks, name, "fail", f"HTTP {status}, bytes={length}")
            return
        add_check(checks, name, "pass", f"HTTP 200, bytes={length}")
    except Exception as exc:
        add_check(checks, name, "fail", str(exc))


def build_summary(args: argparse.Namespace, checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "backend_url": args.backend_url,
        "frontend_url": args.frontend_url,
        "job_id": args.job_id,
        "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "failed": any(check["status"] == "fail" for check in checks),
        "checks": checks,
    }


def run(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []
    check_local_scripts(checks)
    check_backend_health(args, checks)
    check_frontend(args, checks)
    check_job_results(args, checks)

    summary = build_summary(args, checks)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 1 if summary["failed"] else 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except KeyboardInterrupt:
        print("SMOKE CHECK INTERRUPTED", file=sys.stderr)
        return 130
    except urllib.error.URLError as exc:
        print(f"SMOKE CHECK FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
