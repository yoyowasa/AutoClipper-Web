import json
from pathlib import Path
from typing import Any, Protocol, Sequence

from pydantic import BaseModel, Field


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
        compute_type: str = "int8",
        language: str | None = "ja",
        beam_size: int = 5,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper is not installed") from exc

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        path = Path(wav_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        model = self._load_model()
        segments, _info = model.transcribe(
            str(path),
            beam_size=self.beam_size,
            language=self.language,
            word_timestamps=True,
        )

        return [segment_from_faster_whisper(segment) for segment in segments]


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
