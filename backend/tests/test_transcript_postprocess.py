import json
from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_postprocess import (
    postprocess_transcript_segments,
    postprocess_transcript_text,
    finalize_transcript_width,
    fullwidth_transcript_text,
    raw_transcript_output_path,
    repair_known_transcript_artifact_text,
    transcript_postprocess_summary_path,
    write_transcript_postprocess_summary,
)


def test_postprocess_text_normalizes_unicode_whitespace_and_punctuation() -> None:
    text, summary = postprocess_transcript_text(" ＡＩ  って、、すごい！！ ")

    assert text == "ＡＩ って、すごい！"
    assert summary["changed"] is True
    assert summary["replacement_counts"] == {}
    assert summary["normalization_applied"] == ["unicode_nfkc", "whitespace", "punctuation", "fullwidth"]


def test_postprocess_text_applies_default_dictionary() -> None:
    text, summary = postprocess_transcript_text("オープンエーアイとチャットGPTを使います")

    assert text == "ＯｐｅｎＡＩとＣｈａｔＧＰＴを使います"
    assert summary["replacement_counts"] == {"オープンエーアイ": 1, "チャットGPT": 1}


def test_postprocess_text_corrects_known_multilingual_asr_error() -> None:
    text, summary = postprocess_transcript_text(
        "能面の話で、農منをつけて、その農منにしとったっちゃん"
    )

    assert text == "能面の話で、能面をつけて、その能面にしとったっちゃん"
    assert summary["replacement_counts"] == {"農من": 2}


def test_known_artifact_repair_is_idempotent_and_does_not_apply_custom_rules() -> None:
    original = "NewsPicks公式でその農منを見た"

    repaired = repair_known_transcript_artifact_text(original)

    assert repaired == "NewsPicks公式でその能面を見た"
    assert repair_known_transcript_artifact_text(repaired) == repaired


def test_postprocess_text_applies_custom_replacements_after_defaults() -> None:
    text, summary = postprocess_transcript_text(
        "ニューズピックスとリハック",
        {"transcriptReplacements": {"NewsPicks": "NewsPicks公式", "ReHacQ": "ReHacQ公式"}},
    )

    assert text == "ＮｅｗｓＰｉｃｋｓ公式とＲｅＨａｃＱ公式"
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

    assert [segment.text for segment in result.segments] == ["ＯｐｅｎＡＩ", "そのまま"]
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


def test_fullwidth_is_the_job_default_and_preserves_line_breaks_and_kana() -> None:
    from app.schemas import JobSettings

    settings = JobSettings().model_dump(by_alias=True)
    assert settings["transcriptNormalizeFullwidth"] is True
    original = "ABC xyz 123!?\nｶﾞｯﾂﾎﾟｰｽﾞ｡ 日本語、絵文字😀"
    text, _ = postprocess_transcript_text(original, settings)
    assert text == "ＡＢＣ ｘｙｚ １２３！？\nガッツポーズ。 日本語、絵文字😀"
    assert fullwidth_transcript_text(text) == text
    assert fullwidth_transcript_text("v2.5 (50%) + A/B #1") == "ｖ２．５ （５０％） ＋ Ａ／Ｂ ＃１"
    assert postprocess_transcript_text("AI 123!", {"transcriptNormalizeFullwidth": False})[0] == "AI 123!"


def test_final_width_normalization_preserves_metadata_and_does_not_repeat_dictionary() -> None:
    original = TranscriptSegment(start=1.2, end=3.4, text="NewsPicks公式 27万人!?\nｳﾞｧ", confidence=0.8, clipId="short")
    settings = {"transcriptReplacements": {"NewsPicks": "NewsPicks公式"}}
    result = finalize_transcript_width([original], settings)
    assert result[0].text == "ＮｅｗｓＰｉｃｋｓ公式 ２７万人！？\nヴァ"
    assert result[0].model_dump(exclude={"text"}) == original.model_dump(exclude={"text"})
    assert original.text.startswith("NewsPicks")
    assert finalize_transcript_width(result, settings) == result
    assert finalize_transcript_width([original], {"enableTranscriptPostProcessing": False}) == [original]


def test_analysis_scores_and_duplicate_detection_ignore_character_width() -> None:
    from app.candidates.boundary_refinement import _ends_incomplete
    from app.candidates.deduplicate import transcript_similarity
    from app.jobs.runner import _transcript_has_repeated_low_information_text
    from app.scoring.rule_score import hook_keyword_score, incomplete_boundary_penalty

    text = "why automation matters and"
    wide = fullwidth_transcript_text(text)
    assert hook_keyword_score(text) == hook_keyword_score(wide) > 0
    assert incomplete_boundary_penalty(text) == incomplete_boundary_penalty(wide) > 0
    assert transcript_similarity(text, wide) == 1
    assert _ends_incomplete(text) == _ends_incomplete(wide)
    assert _transcript_has_repeated_low_information_text(fullwidth_transcript_text("You You You You You"))
