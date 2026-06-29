from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.render.subtitles_ass import (
    DEFAULT_ASS_FONT,
    SubtitleLayout,
    build_ass_document,
    clipped_transcript_segments,
    format_ass_timestamp,
    split_subtitle_lines,
    write_ass_for_selected_clips,
)


def make_candidate(
    candidate_id: str,
    candidate_type: str,
    start: float,
    end: float,
    overlay_title: str | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text="candidate transcript",
        overlay_title=overlay_title,
    )


def test_format_ass_timestamp_uses_centiseconds() -> None:
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(62.345) == "0:01:02.35"
    assert format_ass_timestamp(3661.999) == "1:01:02.00"


def test_split_subtitle_lines_uses_max_two_lines() -> None:
    text = "why this automation mistake matters before the final export"
    split = split_subtitle_lines(text, max_chars_per_line=24)

    assert split.count("\\N") == 1
    assert split.replace("\\N", " ") == text


def test_clipped_transcript_segments_are_relative_to_candidate_start() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0)
    segments = [
        TranscriptSegment(start=0.0, end=8.0, text="outside"),
        TranscriptSegment(start=8.0, end=12.0, text="first"),
        TranscriptSegment(start=15.0, end=25.0, text="second"),
    ]

    clipped = clipped_transcript_segments(segments, candidate)

    assert [(segment.start, segment.end, segment.text) for segment in clipped] == [
        (0.0, 2.0, "first"),
        (5.0, 10.0, "second"),
    ]


def test_build_ass_document_contains_relative_dialogue_and_short_title() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0, overlay_title="Top title")
    segments = [
        TranscriptSegment(start=8.0, end=12.0, text="first subtitle"),
        TranscriptSegment(start=15.0, end=25.0, text="second subtitle"),
    ]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert f"Style: Subtitle,{DEFAULT_ASS_FONT}," in ass
    assert f"Style: Title,{DEFAULT_ASS_FONT}," in ass
    assert "Dialogue: 1,0:00:00.00,0:00:10.00,Title" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" in ass
    assert "Dialogue: 0,0:00:05.00,0:00:10.00,Subtitle" in ass


def test_write_ass_for_selected_clips_generates_file_for_each_clip(tmp_path: Path) -> None:
    normal = make_candidate("normal_1", "normal", 0.0, 120.0)
    short = make_candidate("short_1", "short", 130.0, 175.0, overlay_title="Short title")
    selection = CandidateSelection(normal_clips=[normal], shorts=[short])
    segments = [
        TranscriptSegment(start=10.0, end=20.0, text="normal subtitle"),
        TranscriptSegment(start=135.0, end=140.0, text="short subtitle"),
    ]

    paths = write_ass_for_selected_clips(
        selection,
        segments,
        tmp_path,
        normal_width=1280,
        normal_height=720,
    )

    assert set(paths) == {"normal_1", "short_1"}
    assert paths["normal_1"].is_file()
    assert paths["short_1"].is_file()
    assert "PlayResX: 1280" in paths["normal_1"].read_text(encoding="utf-8")
    assert "PlayResY: 720" in paths["normal_1"].read_text(encoding="utf-8")
    assert "PlayResX: 1080" in paths["short_1"].read_text(encoding="utf-8")
    assert "Title" in paths["short_1"].read_text(encoding="utf-8")
