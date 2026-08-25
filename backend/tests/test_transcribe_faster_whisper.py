import json
import wave
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.audio.transcribe_faster_whisper import (
    FasterWhisperTranscriptionEngine,
    OpenAITranscriptionEngine,
    TranscriptSegment,
    _deduplicate_overlapping_segments,
    _transcribe_pcm_wav_in_chunks,
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
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def transcribe(self, wav_path: str, **kwargs: object) -> tuple[list[FakeFasterWhisperSegment], object]:
        assert wav_path.endswith(".wav")
        assert kwargs["word_timestamps"] is True
        self.kwargs = kwargs
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
    engine = FasterWhisperTranscriptionEngine(model_size="small", language="ja")
    fake_model = FakeWhisperModel()
    engine._model = fake_model

    segments = engine.transcribe(wav_path)

    assert len(segments) == 1
    assert segments[0].start == 0.25
    assert segments[0].end == 1.5
    assert segments[0].text == "hello world"
    assert segments[0].confidence == pytest.approx(0.7)
    assert engine.model_size == "small"
    assert fake_model.kwargs["language"] == "ja"
    assert engine.diagnostics["requested_device"] == "cpu"
    assert engine.diagnostics["actual_device"] == "cpu"
    assert engine.diagnostics["actual_compute_type"] == "int8"
    assert engine.diagnostics["fallback_used"] is False


def test_faster_whisper_engine_transcribes_long_wav_in_overlapping_chunks(
    tmp_path: Path,
) -> None:
    wav_path = tmp_path / "long.wav"
    with wave.open(str(wav_path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(1000)
        writer.writeframes(b"\x00\x00" * 2000)

    class ChunkModel:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def transcribe(
            self,
            chunk_path: str,
            **kwargs: object,
        ) -> tuple[list[FakeFasterWhisperSegment], object]:
            assert Path(chunk_path).is_file()
            self.calls.append(kwargs)
            return (
                [
                    FakeFasterWhisperSegment(
                        start=0.25,
                        end=0.45,
                        text=f" chunk {len(self.calls)} ",
                        words=[FakeWord(0.9)],
                    )
                ],
                object(),
            )

    model = ChunkModel()
    progress: list[tuple[int, int]] = []
    engine = FasterWhisperTranscriptionEngine(model_size="turbo", language="ja")
    engine._model = model

    segments = engine.transcribe_chunked(
        wav_path,
        chunk_seconds=1.0,
        overlap_seconds=0.2,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert [segment.start for segment in segments] == pytest.approx([0.25, 1.05, 1.85])
    assert [segment.end for segment in segments] == pytest.approx([0.45, 1.25, 2.0])
    assert [segment.text for segment in segments] == ["chunk 1", "chunk 2", "chunk 3"]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert all(call["condition_on_previous_text"] is False for call in model.calls)
    assert engine.diagnostics["chunked"] is True
    assert engine.diagnostics["chunk_count"] == 3
    assert engine.diagnostics["chunk_seconds"] == 1.0
    assert engine.diagnostics["chunk_overlap_seconds"] == 0.2


def test_chunk_deduplication_only_merges_similar_overlapping_segments() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="同じ発話内容", confidence=0.7),
        TranscriptSegment(start=1.0, end=2.5, text="同じ発話内容です", confidence=0.8),
        TranscriptSegment(start=1.5, end=2.2, text="別の発話", confidence=0.9),
        TranscriptSegment(start=3.0, end=4.0, text="同じ発話内容", confidence=0.9),
    ]

    deduplicated = _deduplicate_overlapping_segments(segments)

    assert [(segment.start, segment.text) for segment in deduplicated] == [
        (1.0, "同じ発話内容です"),
        (1.5, "別の発話"),
        (3.0, "同じ発話内容"),
    ]


def test_chunk_deduplication_finds_long_overlap_behind_interleaved_segments() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=10.0, text="長い重複発話", confidence=0.9),
        TranscriptSegment(start=1.0, end=2.0, text="途中の別発話", confidence=0.8),
        TranscriptSegment(start=3.0, end=4.0, text="長い重複発話", confidence=0.7),
        TranscriptSegment(start=5.0, end=6.0, text="長い重複発話", confidence=0.6),
        TranscriptSegment(start=11.0, end=12.0, text="長い重複発話", confidence=0.95),
    ]

    deduplicated = _deduplicate_overlapping_segments(segments)

    assert [(segment.start, segment.end, segment.text) for segment in deduplicated] == [
        (0.0, 10.0, "長い重複発話"),
        (1.0, 2.0, "途中の別発話"),
        (11.0, 12.0, "長い重複発話"),
    ]


@pytest.mark.parametrize(
    ("first_timing", "second_timing", "expected_start"),
    [
        ((85.0, 89.0), (1.0, 5.0), 86.0),
        ((86.0, 90.0), (0.0, 4.0), 85.0),
    ],
    ids=["both_midpoints_owned", "both_midpoints_unowned"],
)
def test_chunk_boundary_jitter_keeps_one_representative(
    tmp_path: Path,
    first_timing: tuple[float, float],
    second_timing: tuple[float, float],
    expected_start: float,
) -> None:
    wav_path = tmp_path / "boundary.wav"
    with wave.open(str(wav_path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(10)
        writer.writeframes(b"\x00\x00" * 1000)

    class BoundaryModel:
        def __init__(self) -> None:
            self.calls = 0

        def transcribe(
            self,
            _chunk_path: str,
            **_kwargs: object,
        ) -> tuple[list[FakeFasterWhisperSegment], object]:
            timing = first_timing if self.calls == 0 else second_timing
            confidence = 0.7 if self.calls == 0 else 0.9
            self.calls += 1
            return (
                [
                    FakeFasterWhisperSegment(
                        start=timing[0],
                        end=timing[1],
                        text="境界の同じ発話",
                        words=[FakeWord(confidence)],
                    )
                ],
                object(),
            )

    model = BoundaryModel()
    segments, chunk_count = _transcribe_pcm_wav_in_chunks(
        model,
        wav_path,
        beam_size=5,
        language="ja",
        chunk_seconds=90.0,
        overlap_seconds=5.0,
    )

    assert chunk_count == 2
    assert len(segments) == 1
    assert segments[0].start == expected_start
    assert segments[0].text == "境界の同じ発話"


def test_chunked_transcription_accepts_empty_pcm_wav(tmp_path: Path) -> None:
    wav_path = tmp_path / "empty.wav"
    with wave.open(str(wav_path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"")

    class NoCallModel:
        def transcribe(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("empty WAV must not invoke the model")

    engine = FasterWhisperTranscriptionEngine()
    engine._model = NoCallModel()

    assert engine.transcribe_chunked(wav_path) == []
    assert engine.diagnostics["chunked"] is True
    assert engine.diagnostics["chunk_count"] == 0


def test_faster_whisper_engine_rejects_missing_wav() -> None:
    engine = FasterWhisperTranscriptionEngine()

    with pytest.raises(FileNotFoundError):
        engine.transcribe("missing.wav")


def test_openai_transcription_engine_placeholder() -> None:
    engine = OpenAITranscriptionEngine()

    with pytest.raises(NotImplementedError, match="not implemented"):
        engine.transcribe("sample.wav")
