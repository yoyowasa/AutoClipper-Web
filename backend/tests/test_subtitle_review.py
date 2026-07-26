from pathlib import Path

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content,
    apply_reviewed_text,
    build_subtitle_review,
    confirm_review_clip,
    load_subtitle_review,
    queue_review_render,
    subtitle_review_preview_path,
    subtitle_review_preview_url,
    update_review_clip_content,
    update_review_segment,
    write_subtitle_review,
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

    review = update_review_clip_content(
        review,
        "short_1",
        title="魚は「耳石」で音を聞く？",
        hook_text="魚の耳には、本当に「石」が入ってるらしい",
        hook_duration_seconds=3.5,
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
    assert [(segment.start, segment.end) for segment in transcript] == [
        (segment.start, segment.end) for segment in apply_reviewed_text(transcript, review)
    ]


def test_normal_clip_rejects_hook_text() -> None:
    _transcript, review = _review_fixture()

    with pytest.raises(ValueError, match="only supported for short clips"):
        update_review_clip_content(
            review,
            "normal_1",
            title="通常タイトル",
            hook_text="通常clipでは使わない",
        )


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
