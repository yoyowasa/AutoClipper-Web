from __future__ import annotations

import subprocess
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable


TRANSCRIPTION_DEVICES = {"auto", "cpu", "cuda"}
TRANSCRIPTION_COMPUTE_TYPES = {"auto", "int8", "float16", "int8_float16"}


class TranscriptionRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class TranscriptionRuntime:
    requested_device: str
    actual_device: str
    requested_compute_type: str
    actual_compute_type: str
    cuda_device_count: int
    gpu_name: str | None
    gpu_memory_total_mb: int | None
    fallback_used: bool
    fallback_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cuda_device_count() -> int:
    try:
        import ctranslate2

        return max(0, int(ctranslate2.get_cuda_device_count()))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return 0


def query_nvidia_gpu() -> tuple[str | None, int | None]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None, None

    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    name, separator, memory = first_line.rpartition(",")
    if not separator:
        return first_line or None, None
    try:
        memory_mb = int(float(memory.strip()))
    except ValueError:
        memory_mb = None
    return name.strip() or None, memory_mb


def resolve_transcription_runtime(
    requested_device: str,
    requested_compute_type: str,
    *,
    cuda_counter: Callable[[], int] = cuda_device_count,
    gpu_query: Callable[[], tuple[str | None, int | None]] = query_nvidia_gpu,
) -> TranscriptionRuntime:
    device = str(requested_device).strip().lower()
    compute_type = str(requested_compute_type).strip().lower()
    if device not in TRANSCRIPTION_DEVICES:
        raise TranscriptionRuntimeError(
            "transcription_device_invalid",
            f"Unsupported transcription device: {requested_device}",
            {"requested_device": requested_device},
        )
    if compute_type not in TRANSCRIPTION_COMPUTE_TYPES:
        raise TranscriptionRuntimeError(
            "transcription_compute_type_invalid",
            f"Unsupported transcription compute type: {requested_compute_type}",
            {"requested_compute_type": requested_compute_type},
        )

    available_cuda_devices = cuda_counter() if device in {"auto", "cuda"} else 0
    if device == "cuda" and available_cuda_devices < 1:
        raise TranscriptionRuntimeError(
            "transcription_cuda_unavailable",
            "CUDA transcription was requested, but no CUDA device is visible to the worker.",
            {
                "requested_device": device,
                "requested_compute_type": compute_type,
                "cuda_device_count": available_cuda_devices,
            },
        )

    actual_device = "cuda" if device == "cuda" or (device == "auto" and available_cuda_devices > 0) else "cpu"
    fallback_used = device == "auto" and actual_device == "cpu"
    fallback_reason = "cuda_device_unavailable" if fallback_used else None
    actual_compute_type = (
        ("float16" if actual_device == "cuda" else "int8")
        if compute_type == "auto"
        else compute_type
    )
    if actual_device == "cpu" and actual_compute_type in {"float16", "int8_float16"}:
        raise TranscriptionRuntimeError(
            "transcription_compute_type_incompatible",
            f"{actual_compute_type} requires CUDA transcription in AutoClipper.",
            {
                "requested_device": device,
                "actual_device": actual_device,
                "requested_compute_type": compute_type,
                "actual_compute_type": actual_compute_type,
            },
        )

    gpu_name: str | None = None
    gpu_memory_total_mb: int | None = None
    if actual_device == "cuda":
        gpu_name, gpu_memory_total_mb = gpu_query()
    return TranscriptionRuntime(
        requested_device=device,
        actual_device=actual_device,
        requested_compute_type=compute_type,
        actual_compute_type=actual_compute_type,
        cuda_device_count=available_cuda_devices,
        gpu_name=gpu_name,
        gpu_memory_total_mb=gpu_memory_total_mb,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


def query_nvidia_memory_used_mb() -> int | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_value = result.stdout.strip().splitlines()[0]
        return int(float(first_value.strip()))
    except (FileNotFoundError, IndexError, OSError, subprocess.SubprocessError, ValueError):
        return None


class NvidiaMemorySampler:
    def __init__(
        self,
        *,
        enabled: bool,
        interval_seconds: float = 0.5,
        memory_query: Callable[[], int | None] = query_nvidia_memory_used_mb,
    ) -> None:
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self.memory_query = memory_query
        self.peak_memory_mb: int | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        value = self.memory_query()
        if value is not None:
            self.peak_memory_mb = value if self.peak_memory_mb is None else max(self.peak_memory_mb, value)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self._sample()

    def start(self) -> None:
        if not self.enabled:
            return
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> int | None:
        if not self.enabled:
            return None
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
        self._sample()
        return self.peak_memory_mb
