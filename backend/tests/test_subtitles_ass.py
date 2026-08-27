from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.candidates.select_candidates import CandidateSelection
from app.overlay_text import normalize_overlay_text
from app.render.subtitles_ass import (
    SubtitleLayout,
    build_ass_document,
    clipped_transcript_segments,
    format_ass_timestamp,
    split_overlay_lines,
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


def test_overlay_lines_keep_manual_break_and_bound_three_lines_to_two() -> None:
    assert normalize_overlay_text("一行目\r\n二行目\n三行目") == "一行目\n二行目 三行目"
    assert normalize_overlay_text("一行目\u2028二行目\u2029三行目") == "一行目\n二行目 三行目"
    assert normalize_overlay_text(r"一行目\N二行目") == "一行目\n二行目"
    assert split_overlay_lines("ここで改行\n二行目を表示") == "ここで改行\\N二行目を表示"


def test_overlay_lines_keep_legacy_single_line_auto_wrap() -> None:
    text = "自動折り返しを維持する既存の一行タイトル"

    rendered = split_overlay_lines(text, max_chars_per_line=12, max_lines=2)

    assert rendered.count("\\N") == 1
    assert rendered.replace("\\N", "") == text


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


def test_short_hook_precedes_title_without_overlapping_title_events() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 10.0, overlay_title="本編タイトル").model_copy(
        update={
            "hook_text": "最初の3秒で続きを見たくなる一言",
            "hook_duration_seconds": 3.0,
        }
    )

    ass = build_ass_document(candidate, [], layout=SubtitleLayout.short())

    assert "Dialogue: 2,0:00:00.00,0:00:03.00,Hook,Hook" in ass
    assert "Dialogue: 1,0:00:03.00,0:00:10.00,Title,," in ass
    assert "Dialogue: 1,0:00:00.00,0:00:10.00,Title,," not in ass


def test_title_and_hook_render_at_manual_two_line_breaks() -> None:
    candidate = make_candidate(
        "short_1",
        "short",
        0.0,
        10.0,
        overlay_title="タイトル前半\nタイトル後半",
    ).model_copy(
        update={
            "hook_text": "フック前半\nフック後半",
            "hook_duration_seconds": 3.0,
        }
    )

    ass = build_ass_document(candidate, [], layout=SubtitleLayout.short())

    assert "タイトル前半\\Nタイトル後半" in ass
    assert "フック前半\\Nフック後半" in ass
    assert "Dialogue: 2,0:00:00.00,0:00:03.00,Hook,Hook" in ass
    assert "Dialogue: 1,0:00:03.00,0:00:10.00,Title" in ass


def test_short_hook_can_render_when_overlay_title_is_disabled() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 10.0).model_copy(
        update={"hook_text": "冒頭フック", "hook_duration_seconds": 2.0}
    )

    ass = build_ass_document(
        candidate,
        [],
        layout=SubtitleLayout.short(),
        top_title="",
    )

    assert "Dialogue: 2,0:00:00.00,0:00:02.00,Hook,Hook" in ass
    assert "Dialogue: 1," not in ass


def test_hook_text_without_cloned_scene_suppresses_overlapping_subtitles() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0).model_copy(
        update={"hook_text": "冒頭フック", "hook_duration_seconds": 3.0}
    )
    segments = [
        TranscriptSegment(start=10.0, end=12.0, text="重ねない字幕"),
        TranscriptSegment(start=12.0, end=14.0, text="境界をまたぐ字幕"),
    ]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Dialogue: 2,0:00:00.00,0:00:03.00,Hook,Hook" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" not in ass
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Subtitle" not in ass
    assert "Dialogue: 0,0:00:03.00,0:00:04.00,Subtitle" in ass


def test_hook_scene_suppresses_regular_subtitles_and_shifts_body_timeline() -> None:
    candidate = make_candidate(
        "short_1",
        "short",
        10.0,
        20.0,
        overlay_title="タイトル",
    ).model_copy(
        update={
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.0,
        }
    )
    segments = [
        TranscriptSegment(start=10.0, end=12.0, text="本編冒頭"),
        TranscriptSegment(start=14.0, end=16.0, text="見せ場"),
    ]

    ass = build_ass_document(
        candidate,
        segments,
        layout=SubtitleLayout.short(),
    )

    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" not in ass
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Subtitle,,0,0,0,,本編冒頭" in ass
    assert "Dialogue: 0,0:00:06.00,0:00:08.00,Subtitle,,0,0,0,,見せ場" in ass
    assert "Dialogue: 1,0:00:00.00,0:00:12.00,Title,," in ass


def test_hook_scene_keeps_hook_text_while_regular_subtitles_start_with_body() -> None:
    candidate = make_candidate(
        "short_1",
        "short",
        10.0,
        20.0,
        overlay_title="タイトル",
    ).model_copy(
        update={
            "hook_text": "冒頭だけに出すフック文字",
            "hook_duration_seconds": 2.0,
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.0,
        }
    )
    segments = [
        TranscriptSegment(start=10.0, end=12.0, text="本編冒頭"),
        TranscriptSegment(start=14.0, end=16.0, text="見せ場"),
    ]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Dialogue: 2,0:00:00.00,0:00:02.00,Hook,Hook" in ass
    assert "冒頭だけに出すフック文字" in ass
    subtitle_dialogues = [
        line for line in ass.splitlines() if line.startswith("Dialogue: 0,")
    ]
    assert subtitle_dialogues
    assert all(
        not line.startswith("Dialogue: 0,0:00:00.")
        for line in subtitle_dialogues
    )
    assert subtitle_dialogues[0].startswith(
        "Dialogue: 0,0:00:02.00,0:00:04.00,Subtitle"
    )


def test_normal_hook_scene_renders_hook_text_and_shifts_body_subtitles() -> None:
    candidate = make_candidate("normal_1", "normal", 10.0, 20.0).model_copy(
        update={
            "hook_text": "通常切り抜きの冒頭フック",
            "hook_duration_seconds": 2.0,
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.0,
        }
    )
    segments = [TranscriptSegment(start=10.0, end=12.0, text="本編冒頭")]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.normal())

    assert "Dialogue: 2,0:00:00.00,0:00:02.00,Hook,Hook" in ass
    assert "通常切り抜きの冒頭フック" in ass
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Subtitle" in ass
    assert "Dialogue: 1," not in ass


def test_normal_title_starts_after_cloned_hook_scene_without_hook_text() -> None:
    candidate = make_candidate("normal_1", "normal", 10.0, 20.0).model_copy(
        update={
            "title": "通常切り抜きの表示タイトル",
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.5,
        }
    )

    ass = build_ass_document(
        candidate,
        [],
        layout=SubtitleLayout.normal(),
        top_title=candidate.title,
    )

    assert "Dialogue: 1,0:00:02.50,0:00:12.50,Title" in ass
    assert "Dialogue: 1,0:00:00.00,0:00:12.50,Title" not in ass


def test_hook_scene_boundary_does_not_hide_first_body_subtitle() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0).model_copy(
        update={
            "hook_scene_start": 10.0,
            "hook_scene_end": 10.5,
        }
    )
    segments = [TranscriptSegment(start=10.0, end=10.5, text="本編先頭")]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Dialogue: 0,0:00:00.00,0:00:00.50,Subtitle" not in ass
    assert "Dialogue: 0,0:00:00.50,0:00:01.60,Subtitle" in ass


def test_hook_text_and_regular_subtitles_never_overlap_when_hook_scene_is_shorter() -> None:
    candidate = make_candidate("short_1", "short", 10.0, 20.0).model_copy(
        update={
            "hook_text": "冒頭フック",
            "hook_duration_seconds": 3.0,
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.54,
        }
    )
    segments = [TranscriptSegment(start=10.0, end=12.0, text="本編先頭")]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Dialogue: 2,0:00:00.00,0:00:03.00,Hook,Hook" in ass
    assert "Dialogue: 0,0:00:02.54,0:00:04.54,Subtitle" not in ass
    assert "Dialogue: 0,0:00:03.00,0:00:04.54,Subtitle" in ass

    def timestamp_seconds(value: str) -> float:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    hook_line = next(
        line for line in ass.splitlines() if line.startswith("Dialogue: 2,")
    )
    hook_parts = hook_line.split(",", 4)
    hook_interval = (
        timestamp_seconds(hook_parts[1]),
        timestamp_seconds(hook_parts[2]),
    )
    subtitle_intervals = []
    for line in ass.splitlines():
        if not line.startswith("Dialogue: 0,"):
            continue
        parts = line.split(",", 4)
        subtitle_intervals.append(
            (timestamp_seconds(parts[1]), timestamp_seconds(parts[2]))
        )
    assert subtitle_intervals
    assert all(
        subtitle_end <= hook_interval[0] or subtitle_start >= hook_interval[1]
        for subtitle_start, subtitle_end in subtitle_intervals
    )


def test_short_subtitle_style_defaults_remain_stable() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0, overlay_title="Top title")
    segments = [TranscriptSegment(start=0.0, end=4.0, text="short subtitle")]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Style: Subtitle,Noto Sans CJK JP,76" in ass
    assert "Style: Title,Noto Sans CJK JP,88" in ass
    assert ",1,5,2,2,86,86,250,1" in ass
    assert ",1,5,2,8,86,86,150,1" in ass


def test_short_subtitle_style_can_be_overridden_from_settings() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0, overlay_title="Top title")
    segments = [TranscriptSegment(start=0.0, end=4.0, text="short subtitle")]
    layout = SubtitleLayout.short(
        settings={
            "subtitleFontName": "Source Han Sans JP Heavy",
            "subtitleTitleFontName": "Source Han Sans JP Heavy",
            "shortSubtitleFontSize": 86,
            "shortTitleFontSize": 92,
            "shortSubtitleOutline": 4,
            "shortSubtitleShadow": 0,
            "shortSubtitleMarginX": 30,
            "shortSubtitleLowerMargin": 680,
            "shortTitleTopMargin": 120,
            "shortSubtitleAlignment": 5,
            "shortTitleAlignment": 8,
        }
    )

    ass = build_ass_document(candidate, segments, layout=layout)

    assert "Style: Subtitle,Source Han Sans JP Heavy,86" in ass
    assert "Style: Title,Source Han Sans JP Heavy,92" in ass
    assert ",1,4,0,5,30,30,680,1" in ass
    assert ",1,4,0,8,30,30,120,1" in ass


def test_clip_title_hook_and_subtitle_styles_are_independent() -> None:
    candidate = make_candidate(
        "short_1",
        "short",
        0.0,
        10.0,
        overlay_title="本編タイトル",
    ).model_copy(
        update={
            "hook_text": "冒頭フック",
            "hook_duration_seconds": 2.0,
            "title_style": ClipTextStyle(
                fontPreset="heavy",
                fontSize=96,
                primaryColor="#FFF200",
                outlineColor="#000000",
                outlineWidth=6,
                xPercent=25,
                yPercent=15,
            ),
            "hook_style": ClipTextStyle(
                fontPreset="serif",
                fontSize=84,
                primaryColor="#FF8FAB",
                outlineColor="#FFFFFF",
                outlineWidth=3,
                xPercent=75,
                yPercent=25,
            ),
            "subtitle_style": ClipTextStyle(
                fontPreset="mono",
                fontSize=70,
                primaryColor="#5EE7F7",
                outlineColor="#000000",
                outlineWidth=4,
                xPercent=50,
                yPercent=80,
            ),
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="確認字幕")]

    ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

    assert "Style: Title,Source Han Sans JP Heavy,96,&H0000F2FF" in ass
    assert "Style: Hook,Noto Serif CJK JP,84,&H00AB8FFF" in ass
    assert "Style: Subtitle,Noto Sans Mono CJK JP,70,&H00F7E75E" in ass
    assert r"{\an5\pos(270,288)}本編タイトル" in ass
    assert r"{\an5\pos(810,480)}冒頭フック" in ass
    assert r"{\an5\pos(540,1536)}確認字幕" in ass


def test_job_subtitle_position_percent_is_used_without_clip_override() -> None:
    candidate = make_candidate(
        "short_1",
        "short",
        0.0,
        4.0,
        overlay_title="タイトル",
    ).model_copy(
        update={
            "hook_text": "フック",
            "hook_duration_seconds": 1.0,
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="会話字幕")]
    layout = SubtitleLayout.short(
        settings={
            "shortSubtitleXPercent": 40,
            "shortSubtitleYPercent": 68.75,
        }
    )

    ass = build_ass_document(candidate, segments, layout=layout)

    assert layout.subtitle_x_percent == 40
    assert layout.subtitle_y_percent == 68.75
    assert r"{\an5\pos(540,240)}タイトル" in ass
    assert r"{\an5\pos(540,360)}フック" in ass
    assert r"{\an5\pos(432,1320)}会話字幕" in ass


def test_clip_subtitle_position_takes_priority_over_job_position() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0).model_copy(
        update={
            "subtitle_style": ClipTextStyle(
                xPercent=60,
                yPercent=57.3,
            )
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="ツッコミ")]
    layout = SubtitleLayout.short(
        settings={
            "shortSubtitleXPercent": 40,
            "shortSubtitleYPercent": 68.75,
        }
    )

    ass = build_ass_document(candidate, segments, layout=layout)

    assert r"{\an5\pos(648,1100)}ツッコミ" in ass
    assert r"{\an5\pos(432,1320)}" not in ass


def test_clip_style_preserves_arbitrary_font_and_can_inherit_layout_position() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0).model_copy(
        update={
            "subtitle_style": ClipTextStyle(
                fontPreset=None,
                fontName="ユーザー指定の任意フォント",
                bold=False,
                fontSize=70,
                primaryColor="#12AB34",
                outlineColor="#102030",
                outlineWidth=4,
                xPercent=90,
                yPercent=10,
                positionMode="layout",
            )
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="任意書体を保持")]
    layout = SubtitleLayout.short(
        settings={
            "shortSubtitleAlignment": 2,
            "shortSubtitleMarginX": 86,
            "shortSubtitleLowerMargin": 250,
        }
    )

    ass = build_ass_document(candidate, segments, layout=layout)

    assert "Style: Subtitle,ユーザー指定の任意フォント,70" in ass
    assert ",0,0,0,0,100,100,0,0,1,4,2,2,86,86,250,1" in ass
    subtitle_line = next(
        line for line in ass.splitlines() if line.startswith("Dialogue: 0,")
    )
    assert r"\pos(" not in subtitle_line
    assert "任意書体を保持" in subtitle_line


def test_layout_position_mode_uses_job_percent_instead_of_stored_coordinates() -> None:
    candidate = make_candidate("short_1", "short", 0.0, 4.0).model_copy(
        update={
            "subtitle_style": ClipTextStyle(
                primaryColor="#12AB34",
                xPercent=90,
                yPercent=10,
                positionMode="layout",
            )
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="位置を保持")]
    layout = SubtitleLayout.short(
        settings={
            "shortSubtitleXPercent": 40,
            "shortSubtitleYPercent": 68.75,
        }
    )

    ass = build_ass_document(candidate, segments, layout=layout)

    assert r"{\an5\pos(432,1320)}位置を保持" in ass
    assert r"{\an5\pos(972,192)}" not in ass


def test_normal_twelve_pixel_layout_style_can_round_trip_as_clip_override() -> None:
    layout = SubtitleLayout.normal(
        width=640,
        height=360,
        settings={
            "normalSubtitleFontName": "小さい任意フォント",
            "normalSubtitleFontSize": 12,
        },
    )
    candidate = make_candidate("normal_1", "normal", 0.0, 4.0).model_copy(
        update={
            "subtitle_style": ClipTextStyle(
                fontPreset=None,
                fontName=layout.font_name,
                bold=True,
                fontSize=layout.font_size,
                primaryColor="#12AB34",
                outlineColor=layout.outline_color,
                outlineWidth=layout.outline,
                xPercent=50,
                yPercent=85,
                positionMode="layout",
            )
        }
    )
    segments = [TranscriptSegment(start=0.0, end=4.0, text="12pxを維持")]

    ass = build_ass_document(candidate, segments, layout=layout)

    assert layout.font_size == 12
    assert "Style: Subtitle,小さい任意フォント,12" in ass
    assert "12pxを維持" in ass


def test_bundled_normal_and_emphasis_font_presets_map_to_ass_names() -> None:
    expected_fonts = {
        "noto_black": "Noto Sans JP Black",
        "mplus_extrabold": "M PLUS 1 ExtraBold",
        "mplus_rounded_extrabold": "Rounded Mplus 1c ExtraBold",
        "chikara": "851CHIKARA-DZUYOKU-KANA-A",
        "dela_gothic": "Dela Gothic One",
        "corporate_logo": "Corporate-Logo-Bold-ver3",
    }
    segments = [TranscriptSegment(start=0.0, end=4.0, text="確認字幕")]

    for preset, font_name in expected_fonts.items():
        candidate = make_candidate("short_1", "short", 0.0, 4.0).model_copy(
            update={
                "subtitle_style": ClipTextStyle(
                    fontPreset=preset,
                    fontSize=70,
                    primaryColor="#FFFFFF",
                    outlineColor="#000000",
                    outlineWidth=4,
                    xPercent=50,
                    yPercent=80,
                )
            }
        )

        ass = build_ass_document(candidate, segments, layout=SubtitleLayout.short())

        assert f"Style: Subtitle,{font_name},70" in ass


def test_short_and_normal_subtitle_styles_use_independent_fonts_and_colors() -> None:
    short_layout = SubtitleLayout.short(
        settings={
            "shortSubtitleFontName": "Source Han Sans JP Heavy",
            "shortSubtitlePrimaryColor": "#12AB34",
            "shortSubtitleOutlineColor": "#56789A",
        }
    )
    normal_layout = SubtitleLayout.normal(
        settings={
            "normalSubtitleFontName": "Noto Serif CJK JP",
            "normalSubtitlePrimaryColor": "#FEDCBA",
            "normalSubtitleOutlineColor": "#102030",
        }
    )
    short_candidate = make_candidate("short_1", "short", 0.0, 4.0)
    normal_candidate = make_candidate("normal_1", "normal", 0.0, 4.0)
    segments = [TranscriptSegment(start=0.0, end=4.0, text="subtitle")]

    short_ass = build_ass_document(short_candidate, segments, layout=short_layout)
    normal_ass = build_ass_document(normal_candidate, segments, layout=normal_layout)

    assert (
        "Style: Subtitle,Source Han Sans JP Heavy,76,&H0034AB12,&H000000FF,&H009A7856"
        in short_ass
    )
    assert (
        "Style: Subtitle,Noto Serif CJK JP,65,&H00BADCFE,&H000000FF,&H00302010"
        in normal_ass
    )
    assert "Style: Title,Noto Sans CJK JP,88,&H00FFFFFF,&H000000FF,&H00000000" in short_ass
    assert "Style: Title,Noto Sans CJK JP,76,&H00FFFFFF,&H000000FF,&H00000000" in normal_ass


def test_subtitle_layout_preserves_zero_margin_overrides() -> None:
    short_layout = SubtitleLayout.short(
        settings={
            "shortSubtitleMarginX": 0,
            "shortSubtitleLowerMargin": 0,
            "shortTitleTopMargin": 0,
        }
    )
    normal_layout = SubtitleLayout.normal(
        settings={
            "normalSubtitleMarginX": 0,
            "normalSubtitleLowerMargin": 0,
            "normalTitleTopMargin": 0,
        }
    )

    assert short_layout.margin_x == 0
    assert short_layout.lower_margin == 0
    assert short_layout.top_margin == 0
    assert normal_layout.margin_x == 0
    assert normal_layout.lower_margin == 0
    assert normal_layout.top_margin == 0


def test_common_subtitle_style_overrides_ignore_type_specific_nulls() -> None:
    layout = SubtitleLayout.short(
        settings={
            "subtitleFontName": "Noto Sans CJK JP",
            "subtitleFontSize": 54,
            "subtitleOutline": 1,
            "subtitleLowerMargin": 500,
            "subtitleAlignment": 8,
            "shortSubtitleFontSize": None,
            "shortSubtitleOutline": None,
            "shortSubtitleLowerMargin": None,
            "shortSubtitleAlignment": None,
        }
    )

    assert layout.font_name == "Noto Sans CJK JP"
    assert layout.font_size == 54
    assert layout.outline == 1
    assert layout.lower_margin == 500
    assert layout.subtitle_alignment == 8


def test_normal_subtitle_style_can_be_overridden_from_settings() -> None:
    layout = SubtitleLayout.normal(
        width=1280,
        height=720,
        settings={
            "subtitleFontSize": 60,
            "subtitleOutline": 4,
            "subtitleMarginX": 70,
            "subtitleLowerMargin": 110,
            "subtitleAlignment": 2,
        },
    )

    assert layout.font_size == 60
    assert layout.outline == 4
    assert layout.margin_x == 70
    assert layout.lower_margin == 110
    assert layout.subtitle_alignment == 2


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
