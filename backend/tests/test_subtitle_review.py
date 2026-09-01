from pathlib import Path

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content,
    apply_reviewed_text,
    build_subtitle_review,
    confirm_review_clip,
    load_subtitle_review,
    queue_review_render,
    refresh_review_overlay_title_expectations,
    refresh_review_render_contract,
    reopen_completed_review,
    subtitle_review_preview_path,
    subtitle_review_preview_url,
    update_review_clip_content,
    update_review_clip_framing,
    update_review_hook_scene,
    update_review_segment,
    write_subtitle_review,
)
from app.posting_metadata import (
    NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
    YouTubeTitleCandidate,
)


def _candidate(candidate_id: str, candidate_type: str, start: float, end: float) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text="selected transcript",
        title=f"{candidate_type} title",
    )


def _review_fixture():
    transcript = [
        TranscriptSegment(start=0.0, end=10.0, text="first"),
        TranscriptSegment(start=10.0, end=20.0, text="shared"),
        TranscriptSegment(start=20.0, end=30.0, text="last"),
    ]
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[_candidate("short_1", "short", 10.0, 30.0)],
    )
    return transcript, build_subtitle_review("job_review", selection, transcript)


def test_posting_metadata_round_trips_from_review_to_selected_candidate(tmp_path: Path) -> None:
    transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[_candidate("short_1", "short", 10.0, 30.0)],
    )
    candidates = [
        YouTubeTitleCandidate(
            id="factual",
            title="事実中心のタイトル",
            intent="factual",
            reason="字幕に直接対応",
            evidenceSegmentIds=["seg_0001"],
        ),
        YouTubeTitleCandidate(
            id="engagement",
            title="続きを見たくなるタイトル",
            intent="engagement",
            reason="結論を言い切らない",
            evidenceSegmentIds=["seg_0001"],
        ),
        YouTubeTitleCandidate(
            id="concise",
            title="短いタイトル",
            intent="concise",
            reason="短く明確",
            evidenceSegmentIds=["seg_0001"],
        ),
    ]

    review = update_review_clip_content(
        review,
        "normal_1",
        title="動画内タイトル",
        publication_title="事実中心のタイトル",
        title_candidates=candidates,
        recommended_title_id="factual",
        selected_title_id="factual",
        youtube_description="動画内容を事実に沿って紹介します。",
        youtube_hashtags=["#切り抜き", "#Shorts"],
        description_evidence_segment_ids=["seg_0001"],
        post_metadata_source="codex",
        post_metadata_revision_hash="a" * 64,
        thumbnail_kicker="今回の美学",
        thumbnail_line1="美しいものって",
        thumbnail_line2="なんだろう？",
        thumbnail_frame_seconds=8.5,
    )
    output_path = tmp_path / "subtitle_review.json"
    write_subtitle_review(review, output_path)
    restored = load_subtitle_review(output_path)
    applied = apply_reviewed_clip_content(selection, restored).normal_clips[0]

    assert [candidate.id for candidate in restored.clips[0].title_candidates] == [
        candidate.id for candidate in candidates
    ]
    assert all(
        candidate.title.endswith(NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX)
        for candidate in restored.clips[0].title_candidates
    )
    assert restored.clips[0].description_evidence_segment_ids == ["seg_0001"]
    assert applied.recommended_title_id == "factual"
    assert applied.selected_title_id == "factual"
    assert applied.youtube_description == "動画内容を事実に沿って紹介します。"
    assert applied.youtube_hashtags == ["#切り抜き", "#Shorts"]
    assert applied.description_evidence_segment_ids == ["seg_0001"]
    assert applied.post_metadata_source == "codex"
    assert applied.post_metadata_revision_hash == "a" * 64
    assert restored.clips[0].thumbnail_kicker == "今回の美学"
    assert restored.clips[0].thumbnail_line1 == "美しいものって"
    assert restored.clips[0].thumbnail_line2 == "なんだろう？"
    assert restored.clips[0].thumbnail_frame_seconds == 8.5
    assert applied.thumbnail_kicker == "今回の美学"
    assert applied.thumbnail_frame_seconds == 8.5


def test_review_build_defaults_to_auto_and_exposes_title_expectation_alias() -> None:
    _transcript, review = _review_fixture()
    clips = {clip.type: clip for clip in review.clips}

    assert review.short_overlay_title_mode == "auto"
    assert review.short_layout == "auto"
    assert clips["normal"].overlay_title_expected is True
    assert clips["short"].overlay_title_expected is True
    assert clips["short"].preview_state == "queued"
    assert clips["short"].preview_spec_hash is None
    assert clips["short"].preview_error is None
    payload = review.model_dump(by_alias=True)
    payload_clips = {clip["type"]: clip for clip in payload["clips"]}
    assert payload_clips["normal"]["overlayTitleExpected"] is True
    assert payload_clips["short"]["overlayTitleExpected"] is True
    assert payload_clips["short"]["previewState"] == "queued"
    assert payload_clips["short"]["previewSpecHash"] is None
    assert payload_clips["short"]["previewError"] is None


def test_review_build_preserves_short_render_settings() -> None:
    transcript = [TranscriptSegment(start=0.0, end=10.0, text="short")]
    selection = CandidateSelection(
        shorts=[_candidate("short_1", "short", 0.0, 10.0)],
    )

    review = build_subtitle_review(
        "job_review",
        selection,
        transcript,
        short_overlay_title_mode="high_quality_only",
        short_layout="face_tracking_crop",
        short_top_banner_enabled=True,
        short_bottom_banner_enabled=True,
    )

    assert review.short_overlay_title_mode == "high_quality_only"
    assert review.short_layout == "face_tracking_crop"
    assert review.short_top_banner_enabled is True
    assert review.short_bottom_banner_enabled is True
    assert review.clips[0].overlay_title_expected is True


def test_review_clip_framing_round_trips_between_candidate_review_and_artifact(
    tmp_path: Path,
) -> None:
    transcript = [TranscriptSegment(start=0.0, end=10.0, text="short")]
    candidate = _candidate("short_1", "short", 0.0, 10.0).model_copy(
        update={
            "framing_offset_x": 12.5,
            "framing_offset_y": -8.25,
            "framing_zoom": 1.2,
        }
    )
    selection = CandidateSelection(shorts=[candidate])

    review = build_subtitle_review("job_review", selection, transcript)
    clip = review.clips[0]

    assert clip.framing_offset_x == 12.5
    assert clip.framing_offset_y == -8.25
    assert clip.framing_zoom == 1.2
    payload = review.model_dump(by_alias=True, mode="json")
    assert payload["clips"][0]["framingOffsetX"] == 12.5
    assert payload["clips"][0]["framingOffsetY"] == -8.25
    assert payload["clips"][0]["framingZoom"] == 1.2

    review = update_review_clip_framing(
        review,
        "short_1",
        framing_offset_x=33.336,
        framing_offset_y=-12.344,
        framing_zoom=1.23456,
    )
    updated = apply_reviewed_clip_content(selection, review).shorts[0]

    assert review.clips[0].framing_offset_x == 33.34
    assert review.clips[0].framing_offset_y == -12.34
    assert review.clips[0].framing_zoom == 1.235
    assert review.clips[0].confirmed is False
    assert updated.framing_offset_x == 33.34
    assert updated.framing_offset_y == -12.34
    assert updated.framing_zoom == 1.235

    output_path = tmp_path / "subtitle_review.json"
    write_subtitle_review(review, output_path)
    restored = load_subtitle_review(output_path)

    assert restored.clips[0].framing_offset_x == 33.34
    assert restored.clips[0].framing_offset_y == -12.34
    assert restored.clips[0].framing_zoom == 1.235


def test_review_build_exposes_exact_resolved_styles_and_layout_contract() -> None:
    transcript = [TranscriptSegment(start=0.0, end=10.0, text="字幕")]
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 10.0)],
        shorts=[_candidate("short_1", "short", 0.0, 10.0)],
    )

    review = build_subtitle_review(
        "job_review",
        selection,
        transcript,
        render_mode="low_cost",
        render_settings={
            "shortSubtitleFontName": "任意ショート書体",
            "titleFontName": "任意タイトル書体",
            "shortSubtitleFontSize": 82,
            "shortTitleFontSize": 91,
            "shortSubtitleOutline": 7,
            "shortSubtitleShadow": 3,
            "shortSubtitleXPercent": 61.5,
            "shortSubtitleYPercent": 72.25,
            "shortSubtitlePrimaryColor": "#12ABEF",
            "shortSubtitleOutlineColor": "#112233",
            "normalSubtitleFontName": "任意通常書体",
            "normalSubtitleFontSize": 55,
            "normalSubtitleAlignment": 1,
            "normalSubtitleMarginX": 128,
            "normalSubtitleLowerMargin": 96,
            "maxCharsPerLineShort": 14,
            "maxCharsPerLineNormal": 31,
            "maxLines": 2,
        },
        source_width=1280,
        source_height=720,
    )
    clips = {clip.type: clip for clip in review.clips}
    short = clips["short"]
    normal = clips["normal"]

    assert review.render_mode == "low_cost"
    assert short.preview_width == 1080
    assert short.preview_height == 1920
    assert short.subtitle_max_chars_per_line == 14
    assert short.subtitle_max_lines == 2
    assert short.subtitle_min_duration_seconds == 1.1
    assert short.subtitle_max_duration_seconds == 4.2
    assert short.subtitle_min_gap_seconds == 0.08
    assert short.resolved_subtitle_style is not None
    assert short.resolved_subtitle_style.font_preset is None
    assert short.resolved_subtitle_style.font_name == "任意ショート書体"
    assert short.resolved_subtitle_style.font_size == 82
    assert short.resolved_subtitle_style.primary_color == "#12ABEF"
    assert short.resolved_subtitle_style.outline_color == "#112233"
    assert short.resolved_subtitle_style.outline_width == 7
    assert short.resolved_subtitle_style.shadow == 3
    assert short.resolved_subtitle_style.bold is True
    assert short.resolved_subtitle_style.position_mode == "layout"
    assert short.resolved_subtitle_style.position_override is True
    assert short.resolved_subtitle_style.x_percent == 61.5
    assert short.resolved_subtitle_style.y_percent == 72.25
    assert short.resolved_title_style is not None
    assert short.resolved_title_style.font_name == "任意タイトル書体"
    assert short.resolved_title_style.x_percent == 50
    assert short.resolved_title_style.y_percent == 12.5
    assert short.resolved_hook_style is not None
    assert short.resolved_hook_style.y_percent == 18.75
    assert short.resolved_default_title_style == short.resolved_title_style
    assert short.resolved_default_hook_style == short.resolved_hook_style
    assert short.resolved_default_subtitle_style == short.resolved_subtitle_style

    assert normal.preview_width == 1280
    assert normal.preview_height == 720
    assert normal.subtitle_max_chars_per_line == 31
    assert normal.resolved_title_style is not None
    assert normal.resolved_title_style.font_name == "任意タイトル書体"
    assert normal.resolved_hook_style is not None
    assert normal.resolved_subtitle_style is not None
    assert normal.resolved_subtitle_style.font_name == "任意通常書体"
    assert normal.resolved_subtitle_style.alignment == 1
    assert normal.resolved_subtitle_style.x_percent == 10
    assert normal.resolved_subtitle_style.y_percent == pytest.approx(86.6666667)
    assert normal.resolved_default_title_style == normal.resolved_title_style
    assert normal.resolved_default_hook_style == normal.resolved_hook_style
    assert normal.resolved_default_subtitle_style == normal.resolved_subtitle_style

    payload = review.model_dump(by_alias=True, mode="json")
    payload_short = next(clip for clip in payload["clips"] if clip["type"] == "short")
    assert payload["renderMode"] == "low_cost"
    assert payload_short["subtitleMaxCharsPerLine"] == 14
    assert payload_short["previewWidth"] == 1080
    assert payload_short["resolvedSubtitleStyle"]["fontName"] == "任意ショート書体"
    assert payload_short["resolvedSubtitleStyle"]["positionOverride"] is True
    assert payload_short["resolvedDefaultSubtitleStyle"]["fontName"] == (
        "任意ショート書体"
    )
    assert payload_short["subtitleMinDurationSeconds"] == 1.1
    assert payload_short["subtitleMaxDurationSeconds"] == 4.2
    assert payload_short["subtitleMinGapSeconds"] == 0.08


def test_resolved_layout_coordinates_allow_values_outside_override_domain() -> None:
    transcript = [TranscriptSegment(start=0.0, end=10.0, text="字幕")]
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 10.0)],
    )

    review = build_subtitle_review(
        "job_review",
        selection,
        transcript,
        render_settings={
            "normalSubtitleAlignment": 1,
            "normalSubtitleMarginX": 1200,
            "normalSubtitleLowerMargin": 900,
        },
        source_width=640,
        source_height=360,
    )

    clip = review.clips[0]
    assert clip.resolved_subtitle_style is not None
    assert clip.resolved_subtitle_style.x_percent == 187.5
    assert clip.resolved_subtitle_style.y_percent == -150
    assert clip.resolved_default_subtitle_style == clip.resolved_subtitle_style
    assert clip.resolved_subtitle_style.position_mode == "layout"
    assert clip.resolved_subtitle_style.position_override is False


def test_legacy_review_render_contract_hydrates_without_touching_review_timestamp() -> None:
    _transcript, review = _review_fixture()
    legacy_payload = review.model_dump(by_alias=True, mode="json")
    legacy_payload.pop("renderMode")
    for clip in legacy_payload["clips"]:
        for key in (
            "resolvedTitleStyle",
            "resolvedHookStyle",
            "resolvedSubtitleStyle",
            "resolvedDefaultTitleStyle",
            "resolvedDefaultHookStyle",
            "resolvedDefaultSubtitleStyle",
            "subtitleMaxCharsPerLine",
            "subtitleMaxLines",
            "subtitleMinDurationSeconds",
            "subtitleMaxDurationSeconds",
            "subtitleMinGapSeconds",
            "previewWidth",
            "previewHeight",
        ):
            clip.pop(key)
    legacy = type(review).model_validate(legacy_payload)
    original_updated_at = legacy.updated_at

    legacy, changed = refresh_review_render_contract(
        legacy,
        render_mode="high_quality",
        render_settings={"shortSubtitleFontName": "旧artifact書体"},
        source_width=854,
        source_height=480,
    )

    assert changed is True
    assert legacy.updated_at == original_updated_at
    normal = next(clip for clip in legacy.clips if clip.type == "normal")
    short = next(clip for clip in legacy.clips if clip.type == "short")
    assert (normal.preview_width, normal.preview_height) == (854, 480)
    assert short.resolved_subtitle_style is not None
    assert short.resolved_subtitle_style.font_name == "旧artifact書体"

    _legacy, changed_again = refresh_review_render_contract(
        legacy,
        render_mode="high_quality",
        render_settings={"shortSubtitleFontName": "旧artifact書体"},
        source_width=854,
        source_height=480,
    )
    assert changed_again is False


def test_shared_segment_edit_invalidates_and_updates_both_clips() -> None:
    transcript, review = _review_fixture()
    review = confirm_review_clip(review, "normal_1")
    review = confirm_review_clip(review, "short_1")
    shared = next(segment for segment in review.segments if len(segment.affected_clip_ids) == 2)

    review = update_review_segment(review, shared.id, "corrected shared text")

    assert review.confirmed_clip_count == 0
    assert review.edited_segment_count == 1
    assert all(not clip.confirmed for clip in review.clips)
    assert all(clip.edited_segment_count == 1 for clip in review.clips)

    reviewed = apply_reviewed_text(transcript, review)
    assert reviewed[shared.index].text == "corrected shared text"
    assert [(segment.start, segment.end) for segment in reviewed] == [
        (segment.start, segment.end) for segment in transcript
    ]


def test_review_requires_every_clip_confirmation_before_render() -> None:
    _transcript, review = _review_fixture()
    review = confirm_review_clip(review, "normal_1")

    with pytest.raises(ValueError, match="all clips must be confirmed"):
        queue_review_render(review)

    review = confirm_review_clip(review, "short_1")
    review = queue_review_render(review)

    assert review.state == "render_queued"
    assert review.confirmed_clip_count == review.total_clip_count == 2


def test_completed_review_can_be_reopened_for_another_render() -> None:
    _transcript, review = _review_fixture()
    review = confirm_review_clip(review, "normal_1")
    review = confirm_review_clip(review, "short_1")
    review = queue_review_render(review)
    review.state = "completed"

    review = reopen_completed_review(review)

    assert review.state == "awaiting_review"
    assert review.render_revision == 2
    assert review.reopened_at is not None
    assert review.confirmed_clip_count == 0
    assert all(not clip.confirmed for clip in review.clips)


def test_clip_title_and_hook_update_invalidates_confirmation_and_updates_selection() -> None:
    transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[
            _candidate("short_1", "short", 10.0, 30.0).model_copy(
                update={"overlay_title": "short title", "title_source": "existing"}
            )
        ],
    )
    review = confirm_review_clip(review, "short_1")
    title_style = ClipTextStyle(
        fontPreset="heavy",
        fontSize=96,
        primaryColor="#FFF200",
        yPercent=12,
    )
    hook_style = ClipTextStyle(
        fontPreset="serif",
        fontSize=84,
        primaryColor="#FF8FAB",
        yPercent=24,
    )
    subtitle_style = ClipTextStyle(
        fontPreset="mono",
        fontSize=72,
        yPercent=82,
    )

    review = update_review_clip_content(
        review,
        "short_1",
        title="魚は「耳石」で音を聞く？",
        hook_text="魚の耳には、本当に「石」が入ってるらしい",
        hook_duration_seconds=3.5,
        title_style=title_style,
        hook_style=hook_style,
        subtitle_style=subtitle_style,
    )
    updated = apply_reviewed_clip_content(selection, review)
    short = updated.shorts[0]

    assert review.confirmed_clip_count == 0
    assert review.clips[1].title_edited is True
    assert review.clips[1].confirmed is False
    assert short.title == "魚は「耳石」で音を聞く？"
    assert short.overlay_title == "魚は「耳石」で音を聞く？"
    assert short.title_source == "manual_review"
    assert short.hook_text == "魚の耳には、本当に「石」が入ってるらしい"
    assert short.hook_duration_seconds == 3.5
    assert short.title_style == title_style
    assert short.hook_style == hook_style
    assert short.subtitle_style == subtitle_style
    assert [(segment.start, segment.end) for segment in transcript] == [
        (segment.start, segment.end) for segment in apply_reviewed_text(transcript, review)
    ]


def test_hook_scene_update_is_applied_to_rerendered_short() -> None:
    _transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[_candidate("short_1", "short", 10.0, 30.0)],
    )
    review = confirm_review_clip(review, "short_1")

    review = update_review_hook_scene(
        review,
        "short_1",
        start=12.0,
        end=14.0,
    )
    updated = apply_reviewed_clip_content(selection, review)

    assert review.clips[1].confirmed is False
    assert review.clips[1].hook_scene_start == 12.0
    assert review.clips[1].hook_scene_end == 14.0
    assert updated.shorts[0].hook_scene_start == 12.0
    assert updated.shorts[0].hook_scene_end == 14.0

    review = update_review_hook_scene(
        review,
        "short_1",
        start=None,
        end=None,
    )
    cleared = apply_reviewed_clip_content(selection, review)

    assert review.clips[1].hook_scene_start is None
    assert review.clips[1].hook_scene_end is None
    assert cleared.shorts[0].hook_scene_start is None
    assert cleared.shorts[0].hook_scene_end is None


def test_hook_scene_update_respects_review_short_duration_limit() -> None:
    _transcript, review = _review_fixture()
    review.short_max_duration = 21.0

    with pytest.raises(ValueError, match="short maximum duration"):
        update_review_hook_scene(
            review,
            "short_1",
            start=12.0,
            end=14.0,
        )


def test_hook_scene_update_allows_clip_already_over_duration_limit() -> None:
    _transcript, review = _review_fixture()
    review.short_max_duration = 19.0

    updated = update_review_hook_scene(
        review,
        "short_1",
        start=12.0,
        end=14.0,
    )

    assert updated.clips[1].hook_scene_start == 12.0
    assert updated.clips[1].hook_scene_end == 14.0


def test_normal_clip_accepts_hook_text_and_hook_scene() -> None:
    _transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[_candidate("short_1", "short", 10.0, 30.0)],
    )
    review.short_max_duration = 1.0

    review = update_review_clip_content(
        review,
        "normal_1",
        title="通常タイトル",
        hook_text="通常clipの冒頭フック",
        hook_duration_seconds=2.5,
    )
    review = update_review_hook_scene(
        review,
        "normal_1",
        start=12.0,
        end=14.0,
    )
    updated = apply_reviewed_clip_content(selection, review)

    assert review.clips[0].hook_text == "通常clipの冒頭フック"
    assert review.clips[0].hook_scene_start == 12.0
    assert review.clips[0].hook_scene_end == 14.0
    assert updated.normal_clips[0].hook_text == "通常clipの冒頭フック"
    assert updated.normal_clips[0].hook_duration_seconds == 2.5
    assert updated.normal_clips[0].hook_scene_start == 12.0
    assert updated.normal_clips[0].hook_scene_end == 14.0


def test_normal_clip_accepts_title_hook_and_subtitle_styles() -> None:
    _transcript, review = _review_fixture()
    title_style = ClipTextStyle(fontPreset="sans_bold", fontSize=76, yPercent=8)
    subtitle_style = ClipTextStyle(fontPreset="serif", fontSize=58, yPercent=90)
    hook_style = ClipTextStyle(fontPreset="heavy", fontSize=72, yPercent=25)

    review = update_review_clip_content(
        review,
        "normal_1",
        title="通常タイトル",
        hook_text="通常フック",
        title_style=title_style,
        hook_style=hook_style,
        subtitle_style=subtitle_style,
    )
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
    )
    updated = apply_reviewed_clip_content(selection, review)

    assert review.clips[0].title_style == title_style
    assert review.clips[0].hook_style == hook_style
    assert review.clips[0].subtitle_style == subtitle_style
    assert review.clips[0].title == "通常タイトル"
    assert review.clips[0].publication_title == (
        f"通常タイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    )
    assert updated.normal_clips[0].title_style == title_style
    assert updated.normal_clips[0].title == (
        f"通常タイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    )


def test_normal_clip_allows_empty_overlay_title_and_keeps_publication_title() -> None:
    _transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
    )

    review = update_review_clip_content(
        review,
        "normal_1",
        title="",
        publication_title="公開用タイトル",
    )
    review = refresh_review_overlay_title_expectations(
        review,
        render_mode="high_quality",
    )
    updated = apply_reviewed_clip_content(selection, review).normal_clips[0]

    assert review.clips[0].title == ""
    assert review.clips[0].publication_title == (
        f"公開用タイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    )
    assert review.clips[0].overlay_title_expected is False
    assert updated.title == f"公開用タイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    assert updated.overlay_title == ""
    assert updated.title_source == "manual_review"


def test_review_preserves_manual_title_and_hook_line_breaks() -> None:
    _transcript, review = _review_fixture()
    selection = CandidateSelection(
        normalClips=[_candidate("normal_1", "normal", 0.0, 20.0)],
        shorts=[_candidate("short_1", "short", 10.0, 30.0)],
    )

    review = update_review_clip_content(
        review,
        "short_1",
        title="タイトル前半\r\nタイトル後半\n三行目",
        hook_text="フック前半\nフック後半",
    )
    updated = apply_reviewed_clip_content(selection, review)

    assert review.clips[1].title == "タイトル前半\nタイトル後半 三行目"
    assert review.clips[1].publication_title == "タイトル前半 タイトル後半 三行目"
    assert review.clips[1].hook_text == "フック前半\nフック後半"
    assert updated.shorts[0].title == "タイトル前半 タイトル後半 三行目"
    assert updated.shorts[0].overlay_title == "タイトル前半\nタイトル後半 三行目"
    assert updated.shorts[0].hook_text == "フック前半\nフック後半"


def test_review_artifact_round_trip(tmp_path: Path) -> None:
    _transcript, review = _review_fixture()
    output_path = tmp_path / "subtitle_review.json"

    write_subtitle_review(review, output_path)
    restored = load_subtitle_review(output_path)

    assert restored == review
    assert not output_path.with_suffix(".json.tmp").exists()


def test_review_preview_path_is_stable_and_not_derived_from_raw_clip_id(
    tmp_path: Path,
) -> None:
    first = subtitle_review_preview_path(tmp_path, "../short 1")
    second = subtitle_review_preview_path(tmp_path, "../short 1")

    assert first == second
    assert first.parent.name == "subtitle_review_previews"
    assert first.suffix == ".mp4"
    assert ".." not in first.name
    assert subtitle_review_preview_url("job_review", "short_1") == (
        "/api/jobs/job_review/subtitle-review/clips/short_1/preview-video"
    )


def test_fallback_titles_are_numbered_per_clip_type() -> None:
    transcript = [TranscriptSegment(start=0.0, end=30.0, text="shared")]
    normal = _candidate("normal_1", "normal", 0.0, 20.0).model_copy(
        update={"title": None}
    )
    short = _candidate("short_1", "short", 10.0, 30.0).model_copy(
        update={"title": None}
    )

    review = build_subtitle_review(
        "job_review",
        CandidateSelection(normalClips=[normal], shorts=[short]),
        transcript,
    )

    assert [clip.title for clip in review.clips] == ["通常切り抜き 01", "ショート 01"]
