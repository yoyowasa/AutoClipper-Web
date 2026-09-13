import pytest

from app.audio.gpu_preflight import CUDA_RUNTIME_LIBRARIES, verify_cuda_runtime_libraries
from app.audio.transcription_runtime import TranscriptionRuntimeError


def test_cuda_runtime_library_preflight_loads_required_libraries() -> None:
    loaded: list[str] = []

    result = verify_cuda_runtime_libraries(lambda library: loaded.append(library))

    assert result == CUDA_RUNTIME_LIBRARIES
    assert loaded == list(CUDA_RUNTIME_LIBRARIES)


def test_cuda_runtime_library_preflight_rejects_missing_cublas() -> None:
    def fail_to_load(library: str) -> object:
        raise OSError(f"missing {library}")

    with pytest.raises(TranscriptionRuntimeError) as raised:
        verify_cuda_runtime_libraries(fail_to_load)

    assert raised.value.code == "transcription_cuda_libraries_unavailable"
    assert raised.value.details == {"library": "libcublas.so.12"}


def test_cuda_runtime_library_preflight_identifies_missing_cudnn() -> None:
    loaded: list[str] = []

    def fail_on_cudnn(library: str) -> object:
        loaded.append(library)
        if library == "libcudnn.so.9":
            raise OSError(f"missing {library}")
        return object()

    with pytest.raises(TranscriptionRuntimeError) as raised:
        verify_cuda_runtime_libraries(fail_on_cudnn)

    assert loaded == ["libcublas.so.12", "libcudnn.so.9"]
    assert raised.value.code == "transcription_cuda_libraries_unavailable"
    assert raised.value.details == {"library": "libcudnn.so.9"}
