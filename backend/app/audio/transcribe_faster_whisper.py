import json
import time
from pathlib import Path
from typing import Any, Protocol, Sequence

from pydantic import BaseModel, Field

from app.audio.transcription_runtime import (
    NvidiaMemorySampler,
    TranscriptionRuntime,
    resolve_transcription_runtime,
)


TRANSCRIPT_FILENAME = "transcript_segments.json"


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class TranscriptionEngine(Protocol):
    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        pass


class FasterWhisperTranscriptionEngine:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "auto",
        language: str | None = None,
        beam_size: int = 5,
    ) -> None:
        self.model_size = model_size
        self.requested_device = device
        self.requested_compute_type = compute_type
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self._model: Any | None = None
        self._runtime: TranscriptionRuntime | None = None
        self._model_load_seconds = 0.0
        self._transcription_seconds = 0.0
        self._peak_vram_mb: int | None = None

    def _resolve_runtime(self) -> TranscriptionRuntime:
        if self._runtime is None:
            self._runtime = resolve_transcription_runtime(
                self.requested_device,
                self.requested_compute_type,
            )
            self.device = self._runtime.actual_device
            self.compute_type = self._runtime.actual_compute_type
        return self._runtime

    def _load_model(self) -> Any:
        runtime = self._resolve_runtime()
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper is not installed") from exc

            self._model = WhisperModel(
                self.model_size,
                device=runtime.actual_device,
                compute_type=runtime.actual_compute_type,
            )
        return self._model

    @property
    def diagnostics(self) -> dict[str, Any]:
        runtime = self._runtime
        payload = (
            runtime.to_dict()
            if runtime is not None
            else {
                "requested_device": self.requested_device,
                "actual_device": None,
                "requested_compute_type": self.requested_compute_type,
                "actual_compute_type": None,
                "cuda_device_count": None,
                "gpu_name": None,
                "gpu_memory_total_mb": None,
                "fallback_used": False,
                "fallback_reason": None,
            }
        )
        return payload | {
            "model": self.model_size,
            "language": self.language or "auto",
            "model_load_seconds": round(self._model_load_seconds, 3),
            "transcription_seconds": round(self._transcription_seconds, 3),
            "peak_vram_mb": self._peak_vram_mb,
        }

    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        path = Path(wav_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        runtime = self._resolve_runtime()
        memory_sampler = NvidiaMemorySampler(enabled=runtime.actual_device == "cuda")
        memory_sampler.start()
        try:
            model_started = time.monotonic()
            model = self._load_model()
            self._model_load_seconds = time.monotonic() - model_started
            transcription_started = time.monotonic()
            segments, _info = model.transcribe(
                str(path),
                beam_size=self.beam_size,
                language=self.language,
                word_timestamps=True,
            )
            result = [segment_from_faster_whisper(segment) for segment in segments]
            self._transcription_seconds = time.monotonic() - transcription_started
            return result
        finally:
            self._peak_vram_mb = memory_sampler.stop()


class OpenAITranscriptionEngine:
    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        raise NotImplementedError("OpenAI transcription is not implemented yet")


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_from_words(segment: Any) -> float | None:
    words = getattr(segment, "words", None)
    if not words:
        return None

    probabilities = [
        probability
        for word in words
        if (probability := _float_or_none(getattr(word, "probability", None))) is not None
    ]
    if not probabilities:
        return None
    return sum(probabilities) / len(probabilities)


def _segment_confidence(segment: Any) -> float | None:
    direct_confidence = _float_or_none(getattr(segment, "confidence", None))
    if direct_confidence is not None:
        return direct_confidence
    return _confidence_from_words(segment)


def segment_from_faster_whisper(segment: Any) -> TranscriptSegment:
    confidence = _segment_confidence(segment)
    return TranscriptSegment(
        start=float(segment.start),
        end=float(segment.end),
        text=str(segment.text).strip(),
        confidence=confidence,
    )


def transcript_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / TRANSCRIPT_FILENAME


def segments_to_jsonable(segments: Sequence[TranscriptSegment]) -> list[dict[str, Any]]:
    return [segment.model_dump(exclude_none=True) for segment in segments]


def write_transcript_segments(
    segments: Sequence[TranscriptSegment],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(segments_to_jsonable(segments), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def transcribe_wav_to_json(
    wav_path: str | Path,
    output_path: str | Path,
    engine: TranscriptionEngine | None = None,
) -> Path:
    transcription_engine = engine or FasterWhisperTranscriptionEngine()
    segments = transcription_engine.transcribe(wav_path)
    return write_transcript_segments(segments, output_path)
