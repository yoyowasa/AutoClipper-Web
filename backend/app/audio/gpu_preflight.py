from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from app.audio.transcription_runtime import TranscriptionRuntimeError, resolve_transcription_runtime


def build_report(device: str, compute_type: str) -> dict[str, Any]:
    import ctranslate2
    import faster_whisper

    runtime = resolve_transcription_runtime(device, compute_type)
    return {
        "ok": True,
        "faster_whisper_version": faster_whisper.__version__,
        "ctranslate2_version": ctranslate2.__version__,
        **runtime.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate faster-whisper CUDA visibility inside the worker.")
    parser.add_argument("--device", default="cuda", choices=["auto", "cpu", "cuda"])
    parser.add_argument(
        "--compute-type",
        default="float16",
        choices=["auto", "int8", "float16", "int8_float16"],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.device, args.compute_type)
    except TranscriptionRuntimeError as exc:
        report = {
            "ok": False,
            "error_code": exc.code,
            "message": str(exc),
            "details": exc.details,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
