from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.render.subtitles_ass import (
    SubtitleLayout,
    build_ass_document,
    clipped_transcript_segments,
    format_ass_timestamp,
    split_subtitle_lines,
    split_subtitle_text,
    subtitle_events_for_candidate,
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


def test_japanese_long_sentence_splits_into_two_line_chunks() -> None:
    text = "物価上昇が家計と企業収益に与える影響を、投資判断の観点から整理します。"

    chunks = split_subtitle_text(text, max_chars_per_event=32)
    rendered = [split_subtitle_lines(chunk, max_chars_per_line=16, max_lines=2) for chunk in chunks]

    assert len(chunks) >= 2
    assert all(line.count("\\N") <= 1 for line in rendered)
    assert all(len(part) <= 16 for line in rendered for part in line.split("\\N"))
    assert "".join(line.replace("\\N", "") for line in rendered) == text


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


def test_subtitle_events_split_long_segment_and_keep_valid_timing() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 12.0)
    layout = SubtitleLayout.short()
    segments = [
        TranscriptSegment(
            start=0.0,
            end=12.0,
            text="インフレが続く中で企業の価格転嫁力と賃金上昇の関係を丁寧に見る必要があります。",
        )
    ]

    events = subtitle_events_for_candidate(segments, candidate, layout)

    assert len(events) >= 2
    assert all(0.0 <= event.start < event.end <= candidate.duration for event in events)
    assert all(events[index].end <= events[index + 1].start for index in range(len(events) - 1))
    assert all(len(event.text) <= layout.max_chars_per_line * layout.max_lines for event in events)


def test_subtitle_events_merge_adjacent_short_segments_when_timing_allows() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0)
    layout = SubtitleLayout.short()
    segments = [
        TranscriptSegment(start=0.0, end=0.45, text="はい"),
        TranscriptSegment(start=0.45, end=0.9, text="次です"),
        TranscriptSegment(start=2.0, end=3.4, text="離れた字幕"),
    ]

    events = subtitle_events_for_candidate(segments, candidate, layout)

    assert events[0].text == "はい 次です"
    assert events[0].end - events[0].start >= 0.9
    assert len(events) == 2


def test_build_ass_document_contains_relative_dialogue_and_short_title() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0, overlay_title="Top title")
    segments = [
        TranscriptSegment(start=8.0, end=12.0, text="first subtitle"),
        TranscriptSegment(start=15.0, end=25.0, text="second subtitle"),
    ]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Subtitle,Noto Sans CJK JP" in ass
    assert "Style: Title,Noto Sans CJK JP" in ass
    assert "Dialogue: 1,0:00:00.00,0:00:10.00,Title" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" in ass
    assert "Dialogue: 0,0:00:05.00,0:00:07.06,Subtitle" in ass
    assert "Dialogue: 0,0:00:07.14,0:00:10.00,Subtitle" in ass


def test_build_ass_document_limits_short_subtitles_to_two_lines() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 12.0, overlay_title="Top title")
    segments = [
        TranscriptSegment(
            start=0.0,
            end=12.0,
            text="物価上昇が家計と企業収益に与える影響を投資判断の観点から整理します",
        )
    ]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())
    subtitle_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0")]

    assert subtitle_lines
    assert all(line.split(",", 9)[9].count("\\N") <= 1 for line in subtitle_lines)
    assert all("Subtitle" in line for line in subtitle_lines)


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
