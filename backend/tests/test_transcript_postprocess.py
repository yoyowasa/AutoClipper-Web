import json
from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_postprocess import (
    postprocess_transcript_segments,
    postprocess_transcript_text,
    raw_transcript_output_path,
    transcript_postprocess_summary_path,
    write_transcript_postprocess_summary,
)


def test_postprocess_text_normalizes_unicode_whitespace_and_punctuation() -> None:
    text, summary = postprocess_transcript_text(" ＡＩ  って、、すごい！！ ")

    assert text == "AI って、すごい!"
    assert summary["changed"] is True
    assert summary["replacement_counts"] == {}
    assert summary["normalization_applied"] == ["unicode_nfkc", "whitespace", "punctuation"]


def test_postprocess_text_applies_default_dictionary() -> None:
    text, summary = postprocess_transcript_text("オープンエーアイとチャットGPTを使います")

    assert text == "OpenAIとChatGPTを使います"
    assert summary["replacement_counts"] == {"オープンエーアイ": 1, "チャットGPT": 1}


def test_postprocess_text_applies_custom_replacements_after_defaults() -> None:
    text, summary = postprocess_transcript_text(
        "ニューズピックスとリハック",
        {"transcriptReplacements": {"NewsPicks": "NewsPicks公式", "ReHacQ": "ReHacQ公式"}},
    )

    assert text == "NewsPicks公式とReHacQ公式"
    assert summary["replacement_counts"] == {"NewsPicks": 1, "ReHacQ": 1, "ニューズピックス": 1, "リハック": 1}


def test_postprocess_can_be_disabled() -> None:
    text, summary = postprocess_transcript_text(" ＡＩ  ", {"enableTranscriptPostProcessing": False})

    assert text == " ＡＩ  "
    assert summary["enabled"] is False
    assert summary["changed"] is False


def test_postprocess_segments_preserves_timing_and_confidence() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=1.0, text="オープンAI", confidence=0.8),
        TranscriptSegment(start=1.0, end=2.0, text="そのまま", confidence=None),
    ]

    result = postprocess_transcript_segments(segments)

    assert [segment.text for segment in result.segments] == ["OpenAI", "そのまま"]
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 1.0
    assert result.segments[0].confidence == 0.8
    assert result.summary["segment_count"] == 2
    assert result.summary["changed_segment_count"] == 1
    assert result.summary["replacement_counts"] == {"オープンAI": 1}


def test_postprocess_summary_paths_and_writer(tmp_path: Path) -> None:
    summary_path = transcript_postprocess_summary_path(tmp_path)
    written = write_transcript_postprocess_summary({"enabled": True}, summary_path)

    assert raw_transcript_output_path(tmp_path) == tmp_path / "raw_transcript_segments.json"
    assert summary_path == tmp_path / "transcript_postprocess_summary.json"
    assert written == summary_path
    assert json.loads(summary_path.read_text(encoding="utf-8")) == {"enabled": True}
