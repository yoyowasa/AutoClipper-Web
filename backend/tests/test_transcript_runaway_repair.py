import json
from unittest.mock import Mock

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment, TranscriptWord, write_transcript_segments
from app.audio.transcript_gap_repair import repair_transcript_gaps, _repair_transcript_gaps
from app.audio.transcript_runaway_repair import detect_runaway_segments, replace_runaway_segment
from app.jobs.summaries import build_transcript_summary
from test_transcript_gap_repair import Model, segment, wav


def runaway_segment(start=10, end=31):
    return TranscriptSegment(start=start, end=end, text="くっき" + "ぃ" * 112, words=[
        TranscriptWord(start=start + (end - start) * i / 112, end=start + (end - start) * (i + 1) / 112, word="ぃ")
        for i in range(112)
    ])


def test_112_words_covering_21_seconds_are_reread_and_replaced(tmp_path):
    bad = runaway_segment()
    baseline = [segment(0, 10, "直前の普通の台詞"), bad, segment(31, 40, "直後の普通の台詞")]
    # Reread timestamps are relative to the padded 8..33 second WAV.
    model = Model([segment(0, 2, "前の窓の台詞"), segment(2, 5, "クッキー!?"),
                   segment(7, 10, "むずいて！クッキーは！"), segment(12, 14, "まってぇぇ！"),
                   segment(15, 22, "こんな感じだった気がする！"), segment(23, 25, "後の窓の台詞")])
    load = Mock(return_value=model)
    result, summary = repair_transcript_gaps(wav(tmp_path), load, baseline, duration=40, silence=[], language="ja")
    assert load.call_count == len(model.calls) == 1
    assert model.calls == [(25, dict(language="ja", beam_size=5, word_timestamps=True,
                                    vad_filter=False, condition_on_previous_text=False))]
    assert result[0] == baseline[0] and result[-1] == baseline[-1]
    assert [item.text for item in result[1:-1]] == ["クッキー!?", "むずいて！クッキーは！", "まってぇぇ！", "こんな感じだった気がする！"]
    assert all(item.repaired and item.repair_windows[0].model_dump() == {"start": 8, "end": 33} for item in result[1:-1])
    assert summary["runaway_segment_count"] == summary["runaway_replaced_count"] == 1
    assert summary["runaway_skipped"] == [] and summary["reread_interval_count"] == 1
    detail = summary["windows"][0]
    assert detail["original_start"] == 10 and detail["original_end"] == 31
    assert detail["original_text_prefix"].startswith("くっきぃ") and detail["reason"] == "replaced"
    assert baseline[1] == bad and not bad.repaired
    path = write_transcript_segments(result, tmp_path / "transcript.json")
    restored = [TranscriptSegment.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
    assert restored == result
    saved_summary = build_transcript_summary(result, transcription_engine="faster_whisper", used_fixture_transcript=False,
                                            transcription_diagnostics={"gap_repair": summary})
    assert saved_summary["gap_repair"] == summary


@pytest.mark.parametrize("reread,reason", [
    ([runaway_segment(2, 23)], "reread_contains_runaway"),
    ([segment(2, 3, "くっき")], "insufficient_character_diversity"),
    ([TranscriptSegment(start=2, end=10, text="語の時刻がない結果")], "no_words_in_runaway_range"),
    ([], "no_words_in_runaway_range"),
])
def test_unsuitable_reread_keeps_original_with_reason(tmp_path, reread, reason):
    baseline = [runaway_segment(0, 21)]
    result, summary = repair_transcript_gaps(wav(tmp_path, 21), lambda: Model(reread), baseline, duration=21, silence=[])
    assert result == baseline
    assert summary["runaway_replaced_count"] == 0 and summary["runaway_skipped"][0]["reason"] == reason
    assert summary["runaway_skipped"][0]["original_text_prefix"].startswith("くっきぃ")


@pytest.mark.parametrize("seconds,expected", [(1.7, False), (2.999, False), (3.0, True)])
def test_word_run_time_boundary_and_normal_long_vowel(seconds, expected):
    item = TranscriptSegment(start=0, end=seconds, text="わーーー", words=[
        TranscriptWord(start=0, end=.1, word="わ"), TranscriptWord(start=.1, end=seconds, word="ー" * 12),
    ])
    assert bool(detect_runaway_segments([item.model_dump()])) is (expected and seconds - .1 >= 3)
    assert bool(detect_runaway_segments([runaway_segment(0, seconds).model_dump()])) is expected


@pytest.mark.parametrize("seconds,repeats,expected", [(4.999, 10, False), (5, 9, False), (5, 10, True)])
def test_text_fallback_thresholds(seconds, repeats, expected):
    item = TranscriptSegment(start=0, end=seconds, text="ぁ" * repeats)
    assert bool(detect_runaway_segments([item.model_dump()])) is expected


def test_normalization_and_same_word_runs():
    item = TranscriptSegment(start=0, end=3, text="ＣＯＯＫＩＥ cookie", words=[
        TranscriptWord(start=0, end=1.5, word="ＣＯＯＫＩＥ"), TranscriptWord(start=1.5, end=3, word=" cookie! "),
    ])
    assert detect_runaway_segments([item.model_dump()])[0].start == 0
    assert detect_runaway_segments([segment(0, 10, "普通の長い台詞").model_dump()]) == []


def test_wordless_runaway_is_reread_even_when_gap_repair_skips(tmp_path):
    baseline = [TranscriptSegment(start=0, end=10, text="ぃ" * 30)]
    result, summary = repair_transcript_gaps(wav(tmp_path, 10), lambda: Model([segment(0, 5, "クッキーの話題")]),
                                           baseline, duration=10, silence=[])
    assert result[0].text == "クッキーの話題" and result[0].repaired
    assert summary["runaway_replaced_count"] == 1 and summary["status"] == "completed"


def test_runaway_failure_keeps_original_and_records_error(tmp_path):
    baseline = [runaway_segment(0, 21)]
    result, summary = repair_transcript_gaps(wav(tmp_path, 21), lambda: Model([], fail=True), baseline, duration=21, silence=[])
    assert result == baseline
    assert summary["runaway_skipped"][0]["reason"] == "reread_failed"
    assert summary["runaway_skipped"][0]["error_type"] == "RuntimeError"


@pytest.mark.parametrize("gap_reread", [[segment(4, 6, "普通の補完")], [runaway_segment(4, 9)], []])
def test_without_baseline_runaway_the_existing_d_result_is_identical(tmp_path, monkeypatch, gap_reread):
    monkeypatch.setattr("app.audio.transcript_gap_repair.time.monotonic", lambda: 1.0)
    baseline = [segment(0, 1, "前"), segment(31, 40, "後")]
    old_model, new_model = Model(gap_reread), Model(gap_reread)
    path = wav(tmp_path)
    expected, old_summary = _repair_transcript_gaps(path, lambda: old_model, baseline, duration=40, silence=[])
    actual, summary = repair_transcript_gaps(path, lambda: new_model, baseline, duration=40, silence=[])
    assert actual == expected and new_model.calls == old_model.calls
    assert summary == {**old_summary, "runaway_segment_count": 0, "runaway_replaced_count": 0, "runaway_skipped": []}


def test_gap_and_runaway_use_same_model_and_failure_does_not_undo_gap(tmp_path):
    baseline = [segment(0, 1, "前"), segment(6, 10, "中"), runaway_segment(10, 31), segment(31, 40, "後")]
    model = Model([segment(3, 4, "補完した普通の台詞")])
    transcribe = model.transcribe
    def fail_second(path, **options):
        if model.calls:
            raise RuntimeError("runaway failed")
        return transcribe(path, **options)
    model.transcribe = fail_second
    load = Mock(return_value=model)
    result, summary = repair_transcript_gaps(wav(tmp_path), load, baseline, duration=40, silence=[])
    assert load.call_count == 1
    assert any(item.text == "補完した普通の台詞" and item.repaired for item in result)
    assert baseline[2] in result and summary["added_segment_count"] == 1
    assert summary["runaway_skipped"][0]["reason"] == "reread_failed"


def test_replacement_is_limited_to_run_and_rejects_neighbor_overlap():
    original = runaway_segment().model_dump()
    target = detect_runaway_segments([original])[0]
    reread = [segment(9, 32, "クッキーと普通の話題").model_dump()]
    result, detail = replace_runaway_segment(original, reread, runaway=target, window=(8, 33))
    assert detail["replaced"] and result[0]["start"] == 10 and result[0]["end"] == 31
    assert original["text"] == "くっき" + "ぃ" * 112
    result, detail = replace_runaway_segment(original, reread, runaway=target, window=(8, 33),
                                            other_segments=[segment(20, 22, "別の既存字幕").model_dump()])
    assert result == [original] and detail["reason"] == "would_overlap_existing_caption"
