import unicodedata

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.transcript_postprocess import postprocess_transcript_segments, postprocess_transcript_text, strip_transcript_ellipsis
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import build_subtitle_review
from app.render.subtitles_ass import SubtitleLayout, _segment_events


@pytest.mark.parametrize("before,after", [
    ("明…明治", "明、明治"), ("タブ…タブレット", "タブ、タブレット"),
    ("シュークリーム…カスタード", "シュークリーム、カスタード"),
    ("プリん…", "プリん"), ("…プリん", "プリん"), ("…", ""), ("‥", ""),
    ("あ..い", "あ、い"), ("あ......い", "あ、い"), ("あ‥い", "あ、い"),
    ("あ・・・い", "あ、い"), ("・・・", ""), ("あ．．．い", "あ、い"), ("．．．", ""),
    ("あ……い", "あ、い"), ("あ… …い", "あ、い"), ("あ…、…い", "あ、い"),
    ("あ、…い", "あ、い"), ("あ…、い", "あ、い"), ("あ…、…！？", "あ！？"),
    ("あ…。", "あ。"), ("あ、…？", "あ？"), ("あ…！", "あ！"), ("あ…、", "あ"),
    ("「…はい…」", "「はい」"), ("あ…\n…い", "あ\nい"),
    ("v2.5 / １．５ / A・B / A・・B", "v2.5 / １．５ / A・B / A・・B"),
])
def test_strip_ellipsis_forms_and_punctuation_without_other_normalization(before, after):
    assert strip_transcript_ellipsis(before) == after
    assert strip_transcript_ellipsis(after) == after
    assert postprocess_transcript_text(before, {"transcriptNormalizeFullwidth": False})[0] == unicodedata.normalize("NFKC", after)


def test_punctuation_switch_keeps_existing_ellipsis_and_width_behavior():
    original = "Ａ…Ｂ"
    assert postprocess_transcript_text(original)[0] == "Ａ、Ｂ"
    assert postprocess_transcript_text(original, {"transcriptNormalizePunctuation": False})[0] == "Ａ．．．Ｂ"
    assert postprocess_transcript_text(original, {"transcriptNormalizePunctuation": False,
        "transcriptNormalizeUnicode": False, "transcriptNormalizeFullwidth": False})[0] == original
    assert postprocess_transcript_text(original, {"enableTranscriptPostProcessing": False})[0] == original


def test_symbol_only_row_uses_existing_empty_caption_handling():
    item = TranscriptSegment(start=0, end=5, text="・・・")
    cleaned = postprocess_transcript_segments([item]).segments[0]
    assert cleaned.text == "" and cleaned.start == 0 and cleaned.end == 5
    assert _segment_events(cleaned, SubtitleLayout.normal()) == []
    candidate = Candidate(id="normal", type="normal", start=0, end=100, duration=100, transcript_text="")
    review = build_subtitle_review("job", CandidateSelection(normalClips=[candidate]), [cleaned])
    assert not any(segment.text.strip() for segment in review.segments)


def test_runaway_replacement_is_cleaned_without_losing_repair_metadata(tmp_path):
    from app.audio.transcript_gap_repair import repair_transcript_gaps
    from test_transcript_gap_repair import Model, wav
    from test_transcript_runaway_repair import runaway_segment, segment

    reread = segment(0, 5, "クッキー…だ！")
    repaired, summary = repair_transcript_gaps(wav(tmp_path, 21), lambda: Model([reread]),
                                             [runaway_segment(0, 21)], duration=21, silence=[])
    assert summary["runaway_replaced_count"] == 1 and repaired[0].repaired
    cleaned = postprocess_transcript_segments(repaired).segments[0]
    assert cleaned.text == "クッキー、だ！"
    assert cleaned.model_dump(exclude={"text"}) == repaired[0].model_dump(exclude={"text"})
