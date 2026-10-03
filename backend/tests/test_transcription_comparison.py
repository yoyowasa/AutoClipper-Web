import json
from pathlib import Path
import sys
from types import SimpleNamespace
import wave

import pytest

from app.audio import transcription_comparison as comparison


def segment(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text, "words": []}


def whisper_segment(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        start=start, end=end, text=text, avg_logprob=-0.2, no_speech_prob=0.01, compression_ratio=1.1,
        words=[SimpleNamespace(start=start, end=end, word=text, probability=0.9)],
    )


def test_nonsilent_gaps_subtract_overlapping_silence_and_keep_exact_boundaries():
    segments = [segment(5, 8, "一"), segment(7, 9, "二"), segment(15, 16, "三")]
    silence = [(0, 2), (1, 2), (10, 12), (19, 20)]
    assert comparison.nonsilent_gaps(segments, 20, silence, 3) == [(2, 5), (12, 15), (16, 19)]
    assert comparison.nonsilent_gaps(segments, 20, silence, 5) == []
    assert comparison.nonsilent_gaps([], 5, [], 5) == [(0, 5)]
    assert comparison.nonsilent_gaps([], 4.999, [], 5) == []


def test_metrics_count_characters_phantom_suspicions_repetitions_and_time_shifts():
    segments = [
        segment(0, 2, "ご視聴ありがとうございました"),
        segment(3, 4, "チャンネル登録"),
        segment(5, 6, "同じ！"), segment(6, 7, "同じ"), segment(7, 8, "同じ。"),
    ]
    baseline = [dict(item, start=item["start"] + 1, end=item["end"] + 1) for item in segments]
    metrics = comparison.build_metrics(segments, duration=15, silence=[(0, 2)], baseline=baseline)
    assert metrics["total_text_characters"] == sum(len(item["text"]) for item in segments)
    assert metrics["phantom_phrase_occurrences"] == 2
    assert metrics["phantom_phrase_occurrences_in_majority_silence"] == 1
    assert metrics["phantom_phrase_occurrences_in_bgm_only"] is None
    assert metrics["repeated_text_run_count"] == 1
    assert metrics["repeated_text_runs"][0]["count"] == 3
    assert metrics["baseline_start_time_comparison"]["shifted_ge_1_second_count"] == 5
    assert metrics["audio_gaps"]["ge_5_seconds"]["count"] == 1
    assert metrics["audio_gaps"]["ge_5_seconds"]["total_seconds"] == 7


def test_repair_windows_pad_two_seconds_merge_and_clamp():
    segments = [segment(8, 10, "a"), segment(13, 15, "b")]
    assert comparison.repair_windows(segments, 20, []) == [(0, 20)]
    assert comparison.repair_windows([], 8, [(0, 8)]) == []


def test_word_audio_gaps_find_holes_inside_long_segments_and_subtract_silence():
    long_segment = segment(0, 30, "長い一行に複数の発話")
    long_segment["words"] = [
        {"start": 0, "end": 1, "word": "一"},
        {"start": 10, "end": 11, "word": "二"},
        {"start": 20, "end": 21, "word": "三"},
    ]
    metrics = comparison.build_metrics([long_segment], duration=30, silence=[(4, 6)])
    assert metrics["audio_gaps"]["ge_3_seconds"]["count"] == 0
    assert metrics["word_audio_gaps"]["ge_3_seconds"] == {
        "count": 4, "total_seconds": 25,
        "intervals": [
            {"start": 1, "end": 4, "duration": 3}, {"start": 6, "end": 10, "duration": 4},
            {"start": 11, "end": 20, "duration": 9}, {"start": 21, "end": 30, "duration": 9},
        ],
    }
    assert metrics["word_audio_gaps"]["ge_5_seconds"]["count"] == 2
    assert metrics["word_audio_gaps"]["ge_5_seconds"]["total_seconds"] == 18


def test_word_audio_gaps_are_independent_of_segment_split_and_have_inclusive_boundaries():
    words = [{"start": 0, "end": 1, "word": "一"}, {"start": 4, "end": 5, "word": "二"}]
    merged = [{**segment(0, 10, "一二"), "words": words}]
    split = [{**segment(word["start"], word["end"], word["word"]), "words": [word]} for word in words]
    metrics = comparison.word_audio_gap_metrics(merged, duration=10, silence=[])
    assert metrics == comparison.word_audio_gap_metrics(split, duration=10, silence=[])
    assert metrics["ge_3_seconds"]["count"] == 2
    assert metrics["ge_3_seconds"]["total_seconds"] == 8
    assert metrics["ge_5_seconds"]["count"] == 1
    assert metrics["ge_5_seconds"]["total_seconds"] == 5


@pytest.mark.parametrize("legacy_words", [None, "missing"])
def test_missing_word_timestamps_are_unavailable_without_changing_segment_metrics(legacy_words):
    current = segment(0, 5, "旧字幕")
    if legacy_words == "missing":
        current.pop("words")
    else:
        current["words"] = None
    metrics = comparison.build_metrics([current], duration=10, silence=[])
    assert metrics["word_audio_gaps"] is None
    assert "Unavailable" in metrics["word_gap_limitation"]
    assert metrics["audio_gaps"]["ge_5_seconds"]["total_seconds"] == 5


def test_repair_retimes_delayed_following_sentence_instead_of_duplicating_it():
    original = [segment(737, 741, "元の字幕"), segment(769.6, 770.8, "あれに似てね"), segment(775, 780, "次")]
    reread = [segment(741.7, 742.8, "あれに似てね"), segment(745, 748, "卵焼きの話"), segment(770, 771, "新しい話")]
    result, changes = comparison.merge_repair(original, reread, window=(739, 772), gaps=[(741, 769.6)])
    assert [(item["start"], item["text"]) for item in result] == [
        (737, "元の字幕"), (741.7, "あれに似てね"), (745, "卵焼きの話"), (775, "次"),
    ]
    assert changes["added_segments"] == 1
    assert changes["retimed_segments"] == 1
    assert changes["corrections"][0]["old_start"] == 769.6


def test_repair_does_not_drop_existing_speech_when_reread_is_empty():
    original = [segment(0, 1, "existing"), segment(10, 11, "following")]
    result, changes = comparison.merge_repair(original, [], window=(0, 15), gaps=[(1, 10)])
    assert result == original
    assert changes["retimed_segments"] == 0
    assert changes["added_segments"] == 0


def test_repair_keeps_different_occurrences_of_same_sentence():
    original = [segment(0, 1, "はい"), segment(10, 11, "はい")]
    reread = [segment(8, 9, "はい")]
    result, _ = comparison.merge_repair(original, reread, window=(6, 13), gaps=[(1, 10)])
    assert [(item["start"], item["text"]) for item in result] == [(0, "はい"), (8, "はい")]


def test_repair_adds_only_uncovered_words_and_clips_their_timestamps_at_gap_edges():
    original = [segment(0, 1, "前"), segment(10, 12, "既存の後続字幕")]
    reread = [{**segment(9, 11, "新しい境界既存"), "words": [
        {"start": 9, "end": 9.6, "word": "新しい"},
        {"start": 9.6, "end": 10.2, "word": "境界"},
        {"start": 10.2, "end": 11, "word": "既存"},
    ]}]
    result, changes = comparison.merge_repair(original, reread, window=(0, 12), gaps=[(1, 10)])
    assert result[0] == original[0] and result[-1] == original[-1]
    added = result[1]
    assert (added["start"], added["end"], added["text"]) == (9, 10, "新しい境界")
    assert added["words"][-1]["end"] == 10
    assert changes["added_segments"] == 1
    assert comparison.timestamp_metrics(result)["non_monotonic_timestamps"] == 0


def test_repair_does_not_add_duplicate_reworded_following_sentence():
    original = [segment(134, 135.02, "前"), segment(135.02, 135.78, "やってくか")]
    reread = [{**segment(134.8399375, 135.7799375, "やっていくか"), "words": [
        {"start": 134.8399375, "end": 135.7799375, "word": "やっていくか"},
    ]}]
    result, changes = comparison.merge_repair(original, reread, window=(133, 138), gaps=[(135, 135.02)])
    assert result == original
    assert changes["added_segments"] == 0
    assert comparison.timestamp_metrics(result)["non_monotonic_timestamps"] == 0


def test_repair_without_words_skips_partial_overlap_but_accepts_wholly_uncovered_sentence():
    original = [segment(10, 12, "既存")]
    reread = [segment(9, 11, "半分重なる候補"), segment(3, 4, "全部空白内")]
    result, changes = comparison.merge_repair(original, reread, window=(0, 14), gaps=[(0, 10)])
    assert [(item["start"], item["text"]) for item in result] == [(3, "全部空白内"), (10, "既存")]
    assert changes["skipped_partial_segments"] == [
        {"start": 9, "end": 11, "text": "半分重なる候補", "reason": "words_unavailable_partial_overlap"},
    ]


def test_exact_sentence_retime_does_not_overwrite_or_overlap_another_existing_caption():
    original = [segment(0, 2, "前の発話"), segment(8, 9, "同じ文")]
    reread = [segment(1, 3, "同じ文")]
    result, changes = comparison.merge_repair(original, reread, window=(0, 12), gaps=[(2, 8)])
    assert result == original
    assert changes["retimed_segments"] == 0
    assert changes["skipped_retimes"][0]["reason"] == "would_overlap_existing_caption"


def test_word_timestamps_receive_chunk_offset():
    payload = comparison.segment_payload(whisper_segment(0.5, 1, "字幕"), offset=10)
    assert payload["start"] == 10.5
    assert payload["words"][0] == {"start": 10.5, "end": 11, "word": "字幕", "probability": 0.9}


@pytest.fixture
def local_inputs(tmp_path: Path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"fake")
    silence = tmp_path / "silence.json"
    silence.write_text("[]", encoding="utf-8")
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\0\0" * 16000 * 5)
    return audio, silence, model


@pytest.mark.parametrize("method", ["A", "B", "C8", "C16"])
def test_comparison_methods_use_requested_options_and_no_model_download(monkeypatch, local_inputs, method):
    calls = []

    class Model:
        def __init__(self, path, **kwargs):
            calls.append(("load", path, kwargs))

        def transcribe(self, path, **kwargs):
            calls.append(("model", path, kwargs))
            info = SimpleNamespace(transcription_options=SimpleNamespace(condition_on_previous_text=method == "A"))
            return iter([whisper_segment(1, 2, "テスト")]), info

    class Batched:
        def __init__(self, model):
            self.model = model

        def transcribe(self, path, **kwargs):
            calls.append(("batch", path, kwargs))
            return self.model.transcribe(path, **kwargs)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model, BatchedInferencePipeline=Batched))
    audio, silence, model = local_inputs
    result = comparison.run_comparison(audio, silence_path=silence, duration=5, method=method, model_path=model, device="cpu")
    assert calls[0][2]["local_files_only"] is True
    options = calls[-1][2]
    assert options["language"] == "ja"
    assert options["beam_size"] == 5
    assert options["word_timestamps"] is True
    if method == "A":
        assert "condition_on_previous_text" not in options
        assert options["vad_filter"] is False
    elif method == "B":
        assert options["condition_on_previous_text"] is False
        assert options["vad_filter"] is False
    else:
        assert options["vad_filter"] is True
        assert options["batch_size"] == int(method[1:])
        assert calls[1][0] == "batch"
    assert result["status"] == "completed"
    assert result["segments"][0]["words"][0]["start"] == 1
    assert result["peak_vram_mb"] is None


def test_D_reads_only_padded_gaps_and_includes_A_time(monkeypatch, local_inputs, tmp_path):
    audio, silence, model_path = local_inputs
    baseline = tmp_path / "A.json"
    baseline.write_text(json.dumps({"method": "A", "status": "completed", "segments": [], "wall_seconds": 10}), encoding="utf-8")
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            with wave.open(path, "rb") as reader:
                calls.append((reader.getnframes(), kwargs))
            return iter([whisper_segment(0.5, 2, "拾った")]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model, BatchedInferencePipeline=None))
    result = comparison.run_comparison(
        audio, silence_path=silence, duration=5, method="D", model_path=model_path, device="cpu", baseline_path=baseline,
    )
    assert calls == [(80000, {"language": "ja", "beam_size": 5, "word_timestamps": True,
                             "vad_filter": False, "condition_on_previous_text": False})]
    assert result["repairs"]["window_count"] == 1
    assert result["baseline_wall_seconds"] == 10
    assert result["total_pipeline_wall_seconds"] >= 10
    assert result["segments"][0]["text"] == "拾った"


def test_repair_reads_a_gap_window_not_the_full_audio_and_offsets_word_times(local_inputs):
    audio, _silence, _model = local_inputs
    with wave.open(str(audio), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\0\0" * 16000 * 20)
    observed = []

    class Model:
        def transcribe(self, path, **kwargs):
            with wave.open(path, "rb") as reader:
                observed.append(reader.getnframes() / reader.getframerate())
            return iter([whisper_segment(2.5, 3.5, "空白の中")]), None

    result, repairs = comparison.repair_transcript(
        audio, Model(), [segment(0, 10, "前"), segment(14, 20, "後")], duration=20, silence=[], progress=lambda _: None,
    )
    assert observed == [8]
    assert repairs["windows"][0]["start"] == 8
    new_segment = next(item for item in result if item["text"] == "空白の中")
    assert new_segment["start"] == 10.5
    assert new_segment["words"][0]["start"] == 10.5


def test_baseline_for_d_must_be_A_and_the_same_audio_duration(local_inputs, tmp_path):
    audio, silence, model = local_inputs
    baseline = tmp_path / "other.json"
    baseline.write_text('{"status":"completed","method":"B"}', encoding="utf-8")
    with pytest.raises(ValueError, match="completed A"):
        comparison.run_comparison(audio, silence_path=silence, duration=5, method="D", model_path=model, baseline_path=baseline)
    baseline.write_text('{"status":"completed","method":"A","duration_seconds":99}', encoding="utf-8")
    with pytest.raises(ValueError, match="duration does not match"):
        comparison.run_comparison(audio, silence_path=silence, duration=5, method="D", model_path=model, baseline_path=baseline)


def test_rejects_missing_local_model_and_unfinished_baseline(local_inputs, tmp_path):
    audio, silence, model = local_inputs
    with pytest.raises(ValueError, match="downloading is disabled"):
        comparison.run_comparison(audio, silence_path=silence, duration=5, method="A", model_path=tmp_path / "missing")
    unfinished = tmp_path / "unfinished.json"
    unfinished.write_text('{"status":"interrupted"}', encoding="utf-8")
    with pytest.raises(ValueError, match="completed comparison"):
        comparison.run_comparison(
            audio, silence_path=silence, duration=5, method="D", model_path=model, baseline_path=unfinished,
        )


def test_cli_publishes_only_after_success_and_does_not_overwrite(monkeypatch, tmp_path):
    output = tmp_path / "result.json"
    argv = ["--audio", "a.wav", "--silence-json", "s.json", "--duration", "5", "--method", "A",
            "--output", str(output), "--model-path", "cached"]

    def fail(*args, **kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(comparison, "run_comparison", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        comparison.main(argv)
    assert not output.exists()
    monkeypatch.setattr(comparison, "run_comparison", lambda *args, **kwargs: {"status": "completed", "segments": []})
    assert comparison.main(argv) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "completed"
    with pytest.raises(SystemExit, match="overwrite"):
        comparison.main(argv)
    assert list(tmp_path.glob(".*.tmp")) == []
