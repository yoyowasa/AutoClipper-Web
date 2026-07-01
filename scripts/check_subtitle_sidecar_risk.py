from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SUFFIXES = (".ass", ".srt", ".vtt")


def job_output_dir(job_id: str, *, root: Path = ROOT) -> Path:
    return root / "storage" / "outputs" / job_id


def scan_sidecar_risks(job_id: str, *, root: Path = ROOT) -> list[dict[str, str]]:
    output_dir = job_output_dir(job_id, root=root)
    risks: list[dict[str, str]] = []
    if not output_dir.is_dir():
        raise RuntimeError(f"job output directory not found: {output_dir}")
    for video_path in sorted(output_dir.rglob("*.mp4")):
        for suffix in SIDECAR_SUFFIXES:
            subtitle_path = video_path.with_suffix(suffix)
            if subtitle_path.is_file():
                risks.append(
                    {
                        "video_path": str(video_path),
                        "subtitle_path": str(subtitle_path),
                    }
                )
    return risks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan AutoClipper outputs for subtitle sidecars that players autoload.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run(args: argparse.Namespace) -> int:
    risks = scan_sidecar_risks(args.job_id)
    if args.json:
        print(json.dumps({"job_id": args.job_id, "risk_count": len(risks), "risks": risks}, ensure_ascii=False, indent=2))
    else:
        print(f"subtitle sidecar autoload risks: {len(risks)}")
        for risk in risks:
            print(f"- video={risk['video_path']}")
            print(f"  subtitle={risk['subtitle_path']}")
    return 1 if risks else 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"SIDECAR RISK CHECK FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
