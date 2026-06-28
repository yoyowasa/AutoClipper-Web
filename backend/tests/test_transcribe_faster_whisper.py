import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine,
    OpenAITranscriptionEngine,
    TranscriptSegment,
    segment_from_faster_whisper,
    segments_to_jsonable,
    transcript_output_path,
    transcribe_wav_to_json,
    write_transcript_segments,
)


class FakeEngine:
    def __init__(self, segments: list[TranscriptSegment]) -> None:
        self.segments = segments

    def transcribe(self, wav_path: str | Path) -> list[TranscriptSegment]:
        assert Path(wav_path).is_file()
        return self.segments


@dataclass
class FakeWord:
    probability: float


@dataclass
class FakeFasterWhisperSegment:
    start: float
    end: float
    text: str
    words: list[FakeWord] | None = None


class FakeWhisperModel:
    def transcribe(self, wav_path: str, **kwargs: object) -> tuple[list[FakeFasterWhisperSegment], object]:
        assert wav_path.endswith(".wav")
        assert kwargs["word_timestamps"] is True
        return (
            [
                FakeFasterWhisperSegment(
                    start=0.25,
                    end=1.5,
                    text=" hello world ",
                    words=[FakeWord(0.8), FakeWord(0.6)],
                )
            ],
            object(),
        )


def test_write_transcript_segments_json_schema(tmp_path: Path) -> None:
    output_path = tmp_path / "transcript_segments.json"
    segments = [
        TranscriptSegment(start=0.0, end=1.25, text="hello", confidence=0.91),
        TranscriptSegment(start=1.25, end=2.0, text="world"),
    ]

    written_path = write_transcript_segments(segments, output_path)
    payload = json.loads(written_path.read_text(encoding="utf-8"))

    assert written_path == output_path
    assert payload == [
        {"start": 0.0, "end": 1.25, "text": "hello", "confidence": 0.91},
        {"start": 1.25, "end": 2.0, "text": "world"},
    ]


def test_transcribe_wav_to_json_writes_empty_audio_segments(tmp_path: Path) -> None:
    wav_path = tmp_path / "empty.wav"
    output_path = tmp_path / "transcript_segments.json"
    wav_path.write_bytes(b"")

    written_path = transcribe_wav_to_json(wav_path, output_path, engine=FakeEngine([]))

    assert written_path == output_path
    assert json.loads(output_path.read_text(encoding="utf-8")) == []


def test_transcript_output_path_uses_expected_filename(tmp_path: Path) -> None:
    assert transcript_output_path(tmp_path) == tmp_path / "transcript_segments.json"


def test_segments_to_jsonable_omits_missing_confidence() -> None:
    payload = segments_to_jsonable([TranscriptSegment(start=0.0, end=1.0, text="silent")])

    assert payload == [{"start": 0.0, "end": 1.0, "text": "silent"}]


def test_segment_from_faster_whisper_uses_word_probability_confidence() -> None:
    segment = segment_from_faster_whisper(
        FakeFasterWhisperSegment(
            start=0.25,
            end=1.5,
            text=" hello world ",
            words=[FakeWord(0.8), FakeWord(0.6)],
        )
    )

    assert segment.start == 0.25
    assert segment.end == 1.5
    assert segment.text == "hello world"
    assert segment.confidence == pytest.approx(0.7)


def test_faster_whisper_engine_maps_segments_with_injected_model(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    wav_path.write_bytes(b"fake wav")
    engine = FasterWhisperTranscriptionEngine()
    engine._model = FakeWhisperModel()

    segments = engine.transcribe(wav_path)

    assert len(segments) == 1
    assert segments[0].start == 0.25
    assert segments[0].end == 1.5
    assert segments[0].text == "hello world"
    assert segments[0].confidence == pytest.approx(0.7)


def test_faster_whisper_engine_rejects_missing_wav() -> None:
    engine = FasterWhisperTranscriptionEngine()

    with pytest.raises(FileNotFoundError):
        engine.transcribe("missing.wav")


def test_openai_transcription_engine_placeholder() -> None:
    engine = OpenAITranscriptionEngine()

    with pytest.raises(NotImplementedError, match="not implemented"):
        engine.transcribe("sample.wav")
