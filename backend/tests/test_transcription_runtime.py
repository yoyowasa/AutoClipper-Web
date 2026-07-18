import pytest

from app.audio.transcription_runtime import (
    NvidiaMemorySampler,
    TranscriptionRuntimeError,
    resolve_transcription_runtime,
)


def test_cpu_auto_compute_preserves_int8_runtime() -> None:
    runtime = resolve_transcription_runtime(
        "cpu",
        "auto",
        cuda_counter=lambda: 1,
    )

    assert runtime.actual_device == "cpu"
    assert runtime.actual_compute_type == "int8"
    assert runtime.cuda_device_count == 0
    assert runtime.fallback_used is False


def test_auto_uses_cuda_float16_when_gpu_is_available() -> None:
    runtime = resolve_transcription_runtime(
        "auto",
        "auto",
        cuda_counter=lambda: 1,
        gpu_query=lambda: ("RTX Test", 16384),
    )

    assert runtime.actual_device == "cuda"
    assert runtime.actual_compute_type == "float16"
    assert runtime.gpu_name == "RTX Test"
    assert runtime.gpu_memory_total_mb == 16384
    assert runtime.fallback_used is False


def test_auto_records_cpu_fallback_when_cuda_is_unavailable() -> None:
    runtime = resolve_transcription_runtime(
        "auto",
        "auto",
        cuda_counter=lambda: 0,
    )

    assert runtime.actual_device == "cpu"
    assert runtime.actual_compute_type == "int8"
    assert runtime.fallback_used is True
    assert runtime.fallback_reason == "cuda_device_unavailable"


def test_explicit_cuda_fails_instead_of_silently_using_cpu() -> None:
    with pytest.raises(TranscriptionRuntimeError) as raised:
        resolve_transcription_runtime(
            "cuda",
            "float16",
            cuda_counter=lambda: 0,
        )

    assert raised.value.code == "transcription_cuda_unavailable"


def test_cpu_rejects_float16_compute_type() -> None:
    with pytest.raises(TranscriptionRuntimeError) as raised:
        resolve_transcription_runtime(
            "cpu",
            "float16",
        )

    assert raised.value.code == "transcription_compute_type_incompatible"


def test_memory_sampler_keeps_highest_observation() -> None:
    values = iter([100, 240, 180])
    sampler = NvidiaMemorySampler(
        enabled=True,
        interval_seconds=10,
        memory_query=lambda: next(values),
    )

    sampler.start()
    peak = sampler.stop()

    assert peak == 240
