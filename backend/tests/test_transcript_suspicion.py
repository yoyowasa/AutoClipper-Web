import json

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_suspicion import (
    analyze_transcript_suspicion,
    select_read_only_context_indices,
    write_suspicion_artifacts,
    write_suspicion_failure_summary,
)


def segment(text: str, confidence: float | None = 0.95) -> TranscriptSegment:
    return TranscriptSegment(start=0.0, end=1.0, text=text, confidence=confidence)


def test_low_confidence_and_mixed_script_are_suspicious() -> None:
    result = analyze_transcript_suspicion(
        [segment("普通の字幕"), segment("FFMペグを使います", 0.95), segment("聞き取りづらい字幕", 0.60)],
        threshold=0.45,
    )

    assert {1, 2}.issubset(result.target_indices)
    assert "mixed_script_token" in result.segments[1].reasons
    assert "low_asr_confidence" in result.segments[2].reasons


def test_kanji_katakana_boundary_combines_with_moderate_confidence() -> None:
    result = analyze_transcript_suspicion(
        [segment("通常の冒頭です", 0.99), segment("対応コーパネルの性能", 0.89)],
        threshold=0.4,
    )

    assert result.target_indices == [1]
    assert "kanji_katakana_boundary" in result.segments[1].reasons


def test_repeated_entity_and_spelling_variants_are_candidates() -> None:
    result = analyze_transcript_suspicion(
        [
            segment("ジェインストリートについて"),
            segment("ジェインストリートの利益"),
            segment("ジェーンストリートでした"),
        ],
        threshold=0.45,
    )

    assert result.target_indices == [0, 1, 2]
    assert "inconsistent_spelling" in result.segments[0].reasons


def test_repeated_cjk_compound_marks_high_confidence_segments() -> None:
    source = [segment(f"かな{index}", 0.98) for index in range(100)]
    source[0] = segment("名柄を選びます", 0.98)
    source[99] = segment("別の名柄を確認します", 0.98)
    result = analyze_transcript_suspicion(
        source,
        threshold=0.4,
    )

    assert 99 in result.target_indices
    assert "repeated_cjk_compound" in result.segments[99].reasons


def test_rare_katakana_or_high_confidence_alone_is_not_suspicious() -> None:
    result = analyze_transcript_suspicion(
        [segment("冒頭は安全確認です", 0.99), segment("アルゴリズムを確認します", 0.99)]
    )

    assert 1 not in result.target_indices


def test_context_indices_are_unique_and_exclude_targets() -> None:
    result = analyze_transcript_suspicion(
        [segment("a", 0.5), segment("b"), segment("c", 0.5), segment("d")],
        context_segments=1,
    )

    assert result.target_indices == [0, 2]
    assert result.context_indices == (1, 3)


def test_context_planner_caps_dense_context_without_losing_temporal_neighbors() -> None:
    context = select_read_only_context_indices(
        [0, 2, 4, 6, 8, 10, 12, 14],
        segment_count=16,
        context_segments=2,
    )

    assert len(context) == 4
    assert set(context).isdisjoint({0, 2, 4, 6, 8, 10, 12, 14})


def test_zero_targets_produces_zero_ratio_and_no_context() -> None:
    result = analyze_transcript_suspicion([segment("正常な字幕です", 0.99)], threshold=0.9)

    assert result.summary()["suspicious_ratio"] == 0.0
    assert result.context_indices == ()


def test_artifacts_include_targets_and_summary(tmp_path) -> None:
    result = analyze_transcript_suspicion([segment("低信頼字幕", 0.5)])
    paths = write_suspicion_artifacts(result, tmp_path)

    assert {path.name for path in paths} == {
        "transcript_suspicion_segments.json",
        "transcript_suspicion_summary.json",
        "subtitle_correction_targets.json",
    }
    assert json.loads((tmp_path / "transcript_suspicion_summary.json").read_text(encoding="utf-8"))[
        "suspicious_segment_count"
    ] == 1


def test_filter_failure_summary_is_explicit(tmp_path) -> None:
    path = write_suspicion_failure_summary(
        tmp_path,
        segment_count=3,
        threshold=0.35,
        exc=RuntimeError("failed"),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["filter_failed"] is True
    assert payload["unique_segments_sent"] == 0
