import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle, SubtitleStyleOverride
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content, build_subtitle_review, update_review_clip_content,
    update_review_clip_framing,
)
from app.render.subtitles_ass import build_ass_document, subtitle_events_for_candidate
from app.render.crop_strategy import _framing_scale


def fixture():
    candidate = Candidate(id="a", type="short", start=10, end=18, duration=8, transcript_text="test")
    segments = [TranscriptSegment(start=10, end=12, text="いつもの字幕"),
                TranscriptSegment(start=12, end=14, text="ここだけ強調"),
                TranscriptSegment(start=14, end=18, text="共通に戻る")]
    style = ClipTextStyle(fontPreset="keifont", fontSize=88, primaryColor="#FF0000",
                          outlineColor="#FFFFFF", outlineWidth=4,
                          outerOutlineColor="#0000FF", outerOutlineWidth=6,
                          xPercent=50, yPercent=50)
    return candidate, segments, SubtitleStyleOverride(start=12, end=14, style=style)


def test_phrase_style_roundtrip_and_isolation():
    candidate, segments, override = fixture()
    other = candidate.model_copy(update={"id": "b"})
    selection = CandidateSelection(shorts=[candidate, other])
    review = build_subtitle_review("test", selection, segments)
    review = update_review_clip_content(review, "a", title="test", hook_text="", subtitle_styles=[override])
    assert review.clips[0].subtitle_styles == [override]
    assert review.clips[1].subtitle_styles == []
    reviewed = apply_reviewed_clip_content(selection, review)
    assert reviewed.shorts[0].subtitle_styles == [override]
    assert reviewed.shorts[1].subtitle_styles == []
    rebuilt = build_subtitle_review("reedit", reviewed, segments)
    assert rebuilt.clips[0].subtitle_styles == [override]
    # Old clients may omit the field without clearing individual styles.
    review = update_review_clip_content(review, "a", title="changed", hook_text="")
    assert review.clips[0].subtitle_styles == [override]
    review = update_review_clip_content(review, "a", title="changed", hook_text="", subtitle_styles=[])
    assert review.clips[0].subtitle_styles == []


def test_invalid_or_duplicate_phrase_rejected():
    candidate, segments, override = fixture()
    for overrides in [[override, override], [override.model_copy(update={"start": 100, "end": 102})]]:
        review = build_subtitle_review("test", CandidateSelection(shorts=[candidate]), segments)
        with pytest.raises(ValueError, match="unique segment"):
            update_review_clip_content(review, "a", title="test", hook_text="", subtitle_styles=overrides)


def test_render_keeps_style_boundaries_and_two_outline_layers():
    candidate, segments, override = fixture()
    candidate.subtitle_styles = [override]
    events = subtitle_events_for_candidate(segments, candidate)
    assert [event.style for event in events] == [None, override.style, None]
    ass = build_ass_document(candidate, segments)
    styled = [line for line in ass.splitlines() if line.startswith("Dialogue:") and "ここだけ強調" in line]
    assert len(styled) == 2
    assert r"\bord10\3c&HFF0000&" in styled[0]
    assert r"\bord4" in styled[1]
    assert all(r"\fnKeifont" in line and r"\1c&H0000FF&" in line for line in styled)
    assert styled[0].split(",")[1:3] == styled[1].split(",")[1:3]
    assert ass.count("共通に戻る") == 1


def test_title_hook_double_outline_and_hook_suppression():
    candidate, segments, override = fixture()
    candidate.overlay_title = "タイトル"
    candidate.hook_text = "フック"
    candidate.hook_duration_seconds = 3
    candidate.title_style = candidate.hook_style = override.style
    candidate.subtitle_styles = [override]
    ass = build_ass_document(candidate, segments)
    dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len([line for line in dialogues if "タイトル" in line]) == 2
    assert len([line for line in dialogues if "フック" in line]) == 2
    assert all(line.split(",")[1] >= "0:00:03.00" for line in dialogues if ",Subtitle," in line)


def test_overlapping_transcript_does_not_inherit_neighbour_style():
    candidate, _segments, override = fixture()
    candidate.start = 12.5
    candidate.duration = candidate.end - candidate.start
    candidate.subtitle_styles = [override]
    segments = [TranscriptSegment(start=12, end=14, text="強調"),
                TranscriptSegment(start=13, end=15, text="別の字幕")]
    events = subtitle_events_for_candidate(segments, candidate)
    assert events[0].style == override.style
    assert events[1].style is None


@pytest.mark.parametrize("zoom", [1.8, 2.4, 3])
def test_face_zoom_roundtrip(zoom):
    candidate, segments, _ = fixture()
    selection = CandidateSelection(shorts=[candidate])
    review = build_subtitle_review("test", selection, segments)
    review = update_review_clip_framing(review, "a", framing_offset_x=0, framing_offset_y=-20, framing_zoom=zoom)
    assert apply_reviewed_clip_content(selection, review).shorts[0].framing_zoom == zoom
    assert _framing_scale(1080, zoom) == round(1080 * zoom)
    with pytest.raises(ValueError):
        _framing_scale(1080, 3.1)
