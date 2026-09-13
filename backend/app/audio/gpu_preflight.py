from __future__ import annotations

import argparse
import ctypes
import json
from collections.abc import Callable, Sequence
from typing import Any

from app.audio.transcription_runtime import TranscriptionRuntimeError, resolve_transcription_runtime


CUDA_RUNTIME_LIBRARIES = ("libcublas.so.12", "libcudnn.so.9")
PREFLIGHT_SCHEMA_VERSION = 1


def verify_cuda_runtime_libraries(
    library_loader: Callable[[str], object] = ctypes.CDLL,
) -> tuple[str, ...]:
    loaded: list[str] = []
    for library in CUDA_RUNTIME_LIBRARIES:
        try:
            library_loader(library)
        except OSError as exc:
            raise TranscriptionRuntimeError(
                "transcription_cuda_libraries_unavailable",
                f"CUDA runtime library is unavailable: {library}",
                {"library": library},
            ) from exc
        loaded.append(library)
    return tuple(loaded)


def build_report(
    device: str,
    compute_type: str,
    *,
    library_loader: Callable[[str], object] = ctypes.CDLL,
) -> dict[str, Any]:
    import ctranslate2
    import faster_whisper

    runtime = resolve_transcription_runtime(device, compute_type)
    cuda_libraries = (
        verify_cuda_runtime_libraries(library_loader)
        if runtime.actual_device == "cuda"
        else ()
    )
    return {
        "ok": True,
        "preflight_schema_version": PREFLIGHT_SCHEMA_VERSION,
        "faster_whisper_version": faster_whisper.__version__,
        "ctranslate2_version": ctranslate2.__version__,
        "cuda_runtime_libraries": list(cuda_libraries),
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
