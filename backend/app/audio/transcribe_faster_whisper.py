import json
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.audio.transcription_runtime import (
    NvidiaMemorySampler,
    TranscriptionRuntime,
    resolve_transcription_runtime,
)


TRANSCRIPT_FILENAME = "transcript_segments.json"
DEFAULT_TRANSCRIPTION_CHUNK_SECONDS = 90.0
DEFAULT_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS = 5.0


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    clip_id: str | None = Field(default=None, alias="clipId")

    model_config = ConfigDict(populate_by_name=True)


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
        self._chunk_count: int | None = None
        self._chunk_seconds: float | None = None
        self._chunk_overlap_seconds: float | None = None

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
        diagnostics = payload | {
            "model": self.model_size,
            "language": self.language or "auto",
            "model_load_seconds": round(self._model_load_seconds, 3),
            "transcription_seconds": round(self._transcription_seconds, 3),
            "peak_vram_mb": self._peak_vram_mb,
            "chunked": self._chunk_count is not None,
        }
        if self._chunk_count is not None:
            diagnostics.update(
                {
                    "chunk_count": self._chunk_count,
                    "chunk_seconds": self._chunk_seconds,
                    "chunk_overlap_seconds": self._chunk_overlap_seconds,
                }
            )
        return diagnostics

    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        path = Path(wav_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        self._chunk_count = None
        self._chunk_seconds = None
        self._chunk_overlap_seconds = None
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

    def transcribe_chunked(
        self,
        wav_path: str | Path,
        *,
        chunk_seconds: float = DEFAULT_TRANSCRIPTION_CHUNK_SECONDS,
        overlap_seconds: float = DEFAULT_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[TranscriptSegment]:
        path = Path(wav_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be greater than zero")
        if overlap_seconds < 0 or overlap_seconds >= chunk_seconds:
            raise ValueError("overlap_seconds must be at least zero and shorter than chunk_seconds")

        self._chunk_count = None
        self._chunk_seconds = None
        self._chunk_overlap_seconds = None
        runtime = self._resolve_runtime()
        memory_sampler = NvidiaMemorySampler(enabled=runtime.actual_device == "cuda")
        memory_sampler.start()
        try:
            model_started = time.monotonic()
            model = self._load_model()
            self._model_load_seconds = time.monotonic() - model_started
            transcription_started = time.monotonic()
            result, chunk_count = _transcribe_pcm_wav_in_chunks(
                model,
                path,
                beam_size=self.beam_size,
                language=self.language,
                chunk_seconds=chunk_seconds,
                overlap_seconds=overlap_seconds,
                progress_callback=progress_callback,
            )
            self._transcription_seconds = time.monotonic() - transcription_started
            self._chunk_count = chunk_count
            self._chunk_seconds = chunk_seconds
            self._chunk_overlap_seconds = overlap_seconds
            return result
        finally:
            self._peak_vram_mb = memory_sampler.stop()


def _chunk_start_frames(total_frames: int, chunk_frames: int, overlap_frames: int) -> list[int]:
    if total_frames <= 0:
        return []
    step_frames = chunk_frames - overlap_frames
    starts = [0]
    while starts[-1] + chunk_frames < total_frames:
        starts.append(starts[-1] + step_frames)
    return starts


def _write_pcm_wav_chunk(
    reader: wave.Wave_read,
    output_path: Path,
    *,
    start_frame: int,
    frame_count: int,
) -> None:
    reader.setpos(start_frame)
    frames = reader.readframes(frame_count)
    with wave.open(str(output_path), "wb") as writer:
        writer.setnchannels(reader.getnchannels())
        writer.setsampwidth(reader.getsampwidth())
        writer.setframerate(reader.getframerate())
        writer.setcomptype(reader.getcomptype(), reader.getcompname())
        writer.writeframes(frames)


def _deduplicate_overlapping_segments(
    segments: Sequence[TranscriptSegment],
) -> list[TranscriptSegment]:
    deduplicated: list[TranscriptSegment] = []
    active_indices: list[int] = []
    for segment in sorted(segments, key=lambda item: (item.start, item.end)):
        active_indices = [
            index
            for index in active_indices
            if deduplicated[index].end > segment.start
        ]
        normalized = "".join(character for character in segment.text.casefold() if character.isalnum())
        duplicate_index: int | None = None
        for index in reversed(active_indices):
            previous = deduplicated[index]
            previous_normalized = "".join(
                character for character in previous.text.casefold() if character.isalnum()
            )
            shorter_length = min(len(normalized), len(previous_normalized))
            longer_length = max(len(normalized), len(previous_normalized))
            substantially_same = bool(
                shorter_length
                and longer_length
                and shorter_length / longer_length >= 0.7
                and (
                    normalized in previous_normalized
                    or previous_normalized in normalized
                )
            )
            if normalized and (normalized == previous_normalized or substantially_same):
                duplicate_index = index
                break
        if duplicate_index is None:
            deduplicated.append(segment)
            active_indices.append(len(deduplicated) - 1)
            continue
        previous = deduplicated[duplicate_index]
        previous_normalized = "".join(
            character for character in previous.text.casefold() if character.isalnum()
        )
        previous_confidence = previous.confidence if previous.confidence is not None else -1.0
        segment_confidence = segment.confidence if segment.confidence is not None else -1.0
        if len(normalized) > len(previous_normalized) or (
            len(normalized) == len(previous_normalized)
            and segment_confidence > previous_confidence
        ):
            deduplicated[duplicate_index] = segment
    return sorted(deduplicated, key=lambda item: (item.start, item.end))


def _transcribe_pcm_wav_in_chunks(
    model: Any,
    wav_path: Path,
    *,
    beam_size: int,
    language: str | None,
    chunk_seconds: float,
    overlap_seconds: float,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[TranscriptSegment], int]:
    shifted_segments: list[TranscriptSegment] = []
    with wave.open(str(wav_path), "rb") as reader:
        frame_rate = reader.getframerate()
        total_frames = reader.getnframes()
        if frame_rate <= 0:
            raise ValueError("WAV frame rate must be greater than zero")
        chunk_frames = max(1, round(chunk_seconds * frame_rate))
        overlap_frames = max(0, round(overlap_seconds * frame_rate))
        if overlap_frames >= chunk_frames:
            raise ValueError("overlap_seconds is too large after WAV frame rounding")
        starts = _chunk_start_frames(total_frames, chunk_frames, overlap_frames)
        media_duration = total_frames / frame_rate

        with tempfile.TemporaryDirectory(prefix="autoclipper-whisper-") as temp_dir:
            for index, start_frame in enumerate(starts):
                stop_frame = min(total_frames, start_frame + chunk_frames)
                chunk_path = Path(temp_dir) / f"chunk-{index:05d}.wav"
                _write_pcm_wav_chunk(
                    reader,
                    chunk_path,
                    start_frame=start_frame,
                    frame_count=stop_frame - start_frame,
                )
                chunk_segments, _info = model.transcribe(
                    str(chunk_path),
                    beam_size=beam_size,
                    language=language,
                    word_timestamps=True,
                    condition_on_previous_text=False,
                )
                materialized = [segment_from_faster_whisper(segment) for segment in chunk_segments]
                chunk_path.unlink(missing_ok=True)
                chunk_start = start_frame / frame_rate
                for segment in materialized:
                    global_start = min(media_duration, max(0.0, chunk_start + segment.start))
                    global_end = min(media_duration, max(global_start, chunk_start + segment.end))
                    if global_end <= global_start or not segment.text.strip():
                        continue
                    shifted_segments.append(
                        TranscriptSegment(
                            start=global_start,
                            end=global_end,
                            text=segment.text,
                            confidence=segment.confidence,
                        )
                    )
                if progress_callback is not None:
                    progress_callback(index + 1, len(starts))
    return _deduplicate_overlapping_segments(shifted_segments), len(starts)


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
