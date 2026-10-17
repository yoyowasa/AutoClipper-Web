import json
from pathlib import Path

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment, TranscriptWord
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    apply_reviewed_text, build_subtitle_review, load_subtitle_review, update_review_segment, write_subtitle_review,
)
from app.render.subtitles_ass import SubtitleLayout, build_ass_document, subtitle_events_for_candidate_output
from app.render.subtitle_timing import usable_words

FIXTURE = json.loads((Path(__file__).resolve().parents[2] / "tests/fixtures/subtitle_timing.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_preview_and_ass_use_identical_speech_timing(case):
    options = {**FIXTURE["options"], **case.get("options", {})}
    candidate = Candidate(id="timing", type="short", start=options["candidateStart"], end=options["candidateEnd"],
                          duration=options["candidateEnd"] - options["candidateStart"], transcript_text="字幕")
    if options["hookSceneDuration"]:
        candidate = candidate.model_copy(update={"hook_scene_start": 0, "hook_scene_end": options["hookSceneDuration"]})
    if options["suppressionEnd"] > options["hookSceneDuration"]:
        candidate = candidate.model_copy(update={"hook_text": "フック", "hook_duration_seconds": options["suppressionEnd"]})
    layout = SubtitleLayout.short({"maxCharsPerLineShort": options["maxCharsPerLine"], "maxLines": options["maxLines"],
                                   "minSubtitleDuration": options["minSubtitleDuration"],
                                   "maxSubtitleDuration": options["maxSubtitleDuration"],
                                   "minGapBetweenSubtitles": options["minGapBetweenSubtitles"]})
    segments = [TranscriptSegment.model_validate(item) for item in case["segments"]]
    events, _ = subtitle_events_for_candidate_output(segments, candidate, layout)
    assert [{"start": e.start, "end": e.end, "text": e.text} for e in events] == case["expected"]
    # Verify that the actual ASS dialogues also use these timings (ASS rounds to centiseconds).
    from app.render.subtitles_ass import format_ass_timestamp
    ass = build_ass_document(candidate, segments, layout=layout)
    lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,") and ",Subtitle," in line]
    assert [(line.split(",")[1], line.split(",")[2]) for line in lines] == [
        (format_ass_timestamp(e.start), format_ass_timestamp(e.end)) for e in events
    ]


def test_words_survive_review_persistence_and_edited_text_never_uses_stale_words(tmp_path):
    source = TranscriptSegment(start=10, end=22, text="元の字幕", words=[TranscriptWord(start=11, end=12, word="元の字幕")])
    candidate = Candidate(id="normal", type="normal", start=10, end=22, duration=12, transcript_text=source.text)
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    review = build_subtitle_review("timing", selection, [source])
    path = write_subtitle_review(review, tmp_path / "subtitle_review.json")
    loaded = load_subtitle_review(path)
    assert loaded.segments[0].words == source.words
    assert apply_reviewed_text([source], loaded)[0].words == source.words
    from app.jobs.quality_gate import _subtitle_events_for_review_clip
    events, _ = _subtitle_events_for_review_clip(loaded, loaded.clips[0], width=1920, height=1080)
    assert [(event.start, event.end, event.text) for event in events] == [(1, 2, source.text)]
    update_review_segment(loaded, loaded.segments[0].id, "手で変えた字幕")
    assert apply_reviewed_text([source], loaded)[0].words is None
    update_review_segment(loaded, loaded.segments[0].id, source.text)
    assert apply_reviewed_text([source], loaded)[0].words == source.words
    # Old subtitle_review.json has no words; do not silently borrow different timings from source.
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["segments"][0]["words"]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    old = load_subtitle_review(path)
    assert old.segments[0].words is None
    assert apply_reviewed_text([source], old)[0].words is None


def test_outlier_review_rows_keep_exact_word_groups_and_render_the_same():
    text = "今日はお菓子を作ります。そしてみんなで食べます。" * 6
    words = [TranscriptWord(start=10 + i * .2, end=10 + (i + 1) * .2, word=char) for i, char in enumerate(text)]
    source = TranscriptSegment(start=10, end=words[-1].end, text=text, words=words)
    candidate = Candidate(id="normal", type="normal", start=10, end=source.end, duration=source.end - 10, transcript_text=text)
    selection = CandidateSelection(normalClips=[candidate], shorts=[])
    review = build_subtitle_review("timing", selection, [source])
    assert len(review.segments) > 1
    assert "".join(row.text for row in review.segments) == text
    assert all(usable_words(row.text, row.words) for row in review.segments)
    assert [word for row in review.segments for word in row.words] == words
    before, _ = subtitle_events_for_candidate_output([source], candidate, SubtitleLayout.normal())
    after, _ = subtitle_events_for_candidate_output(apply_reviewed_text([source], review), candidate, SubtitleLayout.normal())
    assert before == after


def test_manual_structure_split_invalidates_asr_words():
    from app.jobs.subtitle_structure import edit_subtitle_structure
    from app.schemas import SubtitleStructureRequest
    source = TranscriptSegment(start=0, end=8, text="前半です後半です", words=[
        TranscriptWord(start=1, end=2, word="前半です"), TranscriptWord(start=5, end=6, word="後半です"),
    ])
    candidate = Candidate(id="normal", type="normal", start=0, end=8, duration=8, transcript_text=source.text)
    review = build_subtitle_review("timing", CandidateSelection(normalClips=[candidate], shorts=[]), [source])
    row = review.segments[0]
    edit_subtitle_structure(review, SubtitleStructureRequest.model_validate({
        "action": "split", "segments": [{"segmentId": row.id, "before": row.text, "text": row.text}],
        "splitOffset": 4, "splitTime": 4,
    }))
    assert all(item.words is None for item in review.segments)
    assert all(item.words is None for item in apply_reviewed_text([source], review))
