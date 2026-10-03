import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_api_routes import client as client
from test_subtitle_bulk_correction import seed_review
from app.audio.silence_detect import SilenceSegment, write_silence_segments
from app.audio.transcribe_faster_whisper import TranscriptSegment, write_transcript_segments
from app.candidates.merge_boundaries import Candidate, ClipTextStyle, SubtitleStyleOverride
from app.candidates.select_candidates import CandidateSelection
from app.db import get_db
from app.jobs.queue import get_enqueue_subtitle_review_preview
from app.jobs.subtitle_gaps import detect_subtitle_gaps
from app.jobs.subtitle_review import apply_reviewed_text, build_subtitle_review, load_subtitle_review, write_subtitle_review
from app.main import app
from app.models import Job


@pytest.mark.parametrize(
    "duration,silence_seconds,expected",
    [(2.999, 0.0, 0), (3.0, 1.2, 1), (3.0, 1.20001, 0), (5.0, 2.0, 1), (5.0, 2.00001, 0)],
)
def test_gap_thresholds_are_inclusive(duration: float, silence_seconds: float, expected: int) -> None:
    gaps = detect_subtitle_gaps(
        clip_id="clip", clip_start=100.0, clip_end=100.0 + duration, subtitle_ranges=[],
        silence_ranges=[(100.0, 100.0 + silence_seconds)] if silence_seconds else [],
    )
    assert len(gaps) == expected


def test_overlapping_silence_and_subtitles_are_counted_once_and_clipped_to_clip() -> None:
    gaps = detect_subtitle_gaps(
        clip_id="clip", clip_start=10, clip_end=30,
        subtitle_ranges=[(27, 40), (5, 12), (18, 20), (19, 22)],
        silence_ranges=[(24, 25), (12, 13), (23, 25), (12.5, 14)],
    )
    assert [(gap.source_start, gap.source_end) for gap in gaps] == [(12, 18), (22, 27)]
    assert [(gap.start, gap.end) for gap in gaps] == [(2, 8), (12, 17)]


def test_hook_scene_is_excluded_and_body_gaps_use_player_seconds() -> None:
    gaps = detect_subtitle_gaps(
        clip_id="short", clip_start=100, clip_end=115,
        subtitle_ranges=[(105, 108)], silence_ranges=[], hook_duration=2,
    )
    assert [(gap.source_start, gap.source_end) for gap in gaps] == [(100, 105), (108, 115)]
    assert [(gap.start, gap.end) for gap in gaps] == [(2, 7), (10, 17)]
    assert all(gap.start >= 2 for gap in gaps)


def test_gap_ids_are_stable_but_boundary_and_hook_changes_reset_acknowledgement() -> None:
    kwargs = dict(clip_id="clip", clip_start=10.0, clip_end=25.0, subtitle_ranges=[(10, 12), (18, 25)], silence_ranges=[])
    original = detect_subtitle_gaps(**kwargs)[0]
    unchanged = detect_subtitle_gaps(**kwargs, acknowledged_ids=[original.id])[0]
    assert unchanged.id == original.id and unchanged.acknowledged
    for updated in ({"hook_duration": 2.0}, {"clip_start": 11.0}, {"subtitle_ranges": [(10, 13), (18, 25)]}):
        changed = detect_subtitle_gaps(**{**kwargs, **updated}, acknowledged_ids=[original.id])[0]
        assert changed.id != original.id and not changed.acknowledged


def test_empty_subtitle_text_does_not_cover_an_audible_gap(tmp_path: Path) -> None:
    candidate = Candidate(id="clip", type="normal", start=100, end=120, duration=20, transcript_text="字幕")
    review = build_subtitle_review(
        "job_gap", CandidateSelection(normalClips=[candidate]),
        [TranscriptSegment(start=100, end=103, text="前"), TranscriptSegment(start=103, end=108, text="  "),
         TranscriptSegment(start=108, end=120, text="後")],
    )
    write_silence_segments([], tmp_path / "silence_segments.json")
    path = tmp_path / "subtitle_review.json"
    write_subtitle_review(review, path)
    assert [(gap.start, gap.end) for gap in load_subtitle_review(path).clips[0].gaps] == [(3, 8)]


@pytest.mark.parametrize("artifact", [None, "not json", "{}"])
def test_no_silence_artifact_means_no_gap_analysis_and_old_review_still_loads(tmp_path: Path, artifact: str | None) -> None:
    candidate = Candidate(id="clip", type="normal", start=0, end=10, duration=10, transcript_text="字幕")
    review = build_subtitle_review("job_gap", CandidateSelection(normalClips=[candidate]), [])
    payload = review.model_dump(by_alias=True, mode="json")
    payload["clips"][0].pop("gaps")
    path = tmp_path / "subtitle_review.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    if artifact is not None:
        (tmp_path / "silence_segments.json").write_text(artifact, encoding="utf-8")
    assert load_subtitle_review(path).clips[0].gaps == []


def _seed_gaps(api: TestClient):
    job_id, path, document = seed_review(api)
    write_silence_segments([], path.parent / "silence_segments.json")
    write_subtitle_review(document, path)
    return job_id, path, document


def test_gap_confirmation_persists_without_changing_review_or_enqueuing_preview(client: TestClient) -> None:  # noqa: F811
    job_id, path, document = _seed_gaps(client)
    clip = document.clips[0]
    gap = clip.gaps[0]
    before = document.model_dump(by_alias=True, mode="json")

    def unexpected_enqueue(*args):
        pytest.fail("Acknowledging a gap must not enqueue a preview")

    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: unexpected_enqueue
    url = f"/api/jobs/{job_id}/subtitle-review/clips/{clip.id}/gaps/{gap.id}"
    response = client.patch(url, json={"acknowledged": True})
    assert response.status_code == 200, response.text
    saved_payload = json.loads(path.read_text(encoding="utf-8"))
    assert saved_payload["clips"][0]["gaps"][0]["acknowledged"] is True
    saved = load_subtitle_review(path)
    assert saved.clips[0].gaps[0].acknowledged
    after = saved.model_dump(by_alias=True, mode="json")
    after["updatedAt"] = before["updatedAt"]
    after["clips"][0]["gaps"][0]["acknowledged"] = False
    assert after == before
    assert client.patch(url, json={"acknowledged": False}).status_code == 200
    assert not load_subtitle_review(path).clips[0].gaps[0].acknowledged


def test_text_edit_recalculates_gap_and_resets_changed_interval_confirmation(client: TestClient) -> None:  # noqa: F811
    job_id, path, document = _seed_gaps(client)
    clip = document.clips[0]
    gap = clip.gaps[0]
    url = f"/api/jobs/{job_id}/subtitle-review/clips/{clip.id}/gaps/{gap.id}"
    assert client.patch(url, json={"acknowledged": True}).status_code == 200
    first = document.segments[0]
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments",
                            json={"segments": [{"segmentId": first.id, "before": first.text, "text": ""}]})
    assert response.status_code == 200, response.text
    updated = response.json()["clips"][0]["gaps"][0]
    assert (updated["start"], updated["end"], updated["acknowledged"]) == (0, 6, False)
    assert updated["id"] != gap.id
    assert client.patch(url, json={"acknowledged": True}).status_code == 404
    assert load_subtitle_review(path).clips[0].gaps[0].id == updated["id"]


def test_inserting_subtitle_recalculates_gaps_and_retains_only_unchanged_confirmations(client: TestClient) -> None:  # noqa: F811
    job_id, path, document = _seed_gaps(client)
    clip = document.clips[0]
    for gap in clip.gaps:
        url = f"/api/jobs/{job_id}/subtitle-review/clips/{clip.id}/gaps/{gap.id}"
        assert client.patch(url, json={"acknowledged": True}).status_code == 200
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "insert_at_time", "segments": [], "clipId": clip.id, "start": 2.5, "end": 3, "text": "抜けた字幕",
    })
    assert response.status_code == 200, response.text
    gaps = load_subtitle_review(path).clips[0].gaps
    assert [(gap.start, gap.end, gap.acknowledged) for gap in gaps] == [(3, 6, False), (7, 10, True)]


@pytest.mark.parametrize("failure,expected", [("clip", 404), ("gap", 404), ("completed", 409), ("render_queued", 409)])
def test_gap_confirmation_rejects_missing_or_uneditable_target(client: TestClient, failure: str, expected: int) -> None:  # noqa: F811
    job_id, path, document = _seed_gaps(client)
    clip = document.clips[0]
    clip_id = "missing" if failure == "clip" else clip.id
    gap_id = "missing" if failure == "gap" else clip.gaps[0].id
    if failure == "completed":
        with next(app.dependency_overrides[get_db]()) as db:
            db.get(Job, job_id).status = "completed"
            db.commit()
    elif failure == "render_queued":
        document.state = "render_queued"
        write_subtitle_review(document, path)
    before = path.read_bytes()
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/gaps/{gap_id}", json={"acknowledged": True})
    assert response.status_code == expected, response.text
    assert path.read_bytes() == before


def test_source_silence_excludes_quiet_interval_even_when_clip_has_no_subtitles(tmp_path: Path) -> None:
    review = build_subtitle_review("job_gap", CandidateSelection(
        normalClips=[Candidate(id="clip", type="normal", start=50, end=60, duration=10, transcript_text="")],
    ), [])
    write_silence_segments([SilenceSegment(start=50, end=55, duration=5)], tmp_path / "silence_segments.json")
    path = tmp_path / "subtitle_review.json"
    write_subtitle_review(review, path)
    assert load_subtitle_review(path).clips[0].gaps == []


@pytest.mark.parametrize("hook_seconds,scene_seconds,expected_source_start", [(3, 0, 103), (3, 2, 101), (1, 2, 100)])
def test_intentional_short_hook_text_suppression_is_not_marked(
    tmp_path: Path, hook_seconds: float, scene_seconds: float, expected_source_start: float,
) -> None:
    kwargs = {"hook_scene_start": 104, "hook_scene_end": 104 + scene_seconds} if scene_seconds else {}
    candidate = Candidate(
        id="short", type="short", start=100, end=110, duration=10, transcript_text="", hook_text="注目",
        hook_duration_seconds=hook_seconds, **kwargs,
    )
    review = build_subtitle_review("job_gap", CandidateSelection(shorts=[candidate]), [])
    write_silence_segments([], tmp_path / "silence_segments.json")
    path = tmp_path / "subtitle_review.json"
    write_subtitle_review(review, path)
    gap = load_subtitle_review(path).clips[0].gaps[0]
    assert gap.source_start == expected_source_start
    assert gap.start == max(hook_seconds, scene_seconds)
    assert gap.end == 10 + scene_seconds


@pytest.mark.parametrize("blank_ranges", [[(2, 8)], [(2, 5), (5, 8)]])
def test_gap_can_add_subtitle_inside_blank_rows_preserving_shared_clips_and_styles(
    client: TestClient, blank_ranges: list[tuple[float, float]],
) -> None:  # noqa: F811
    job_id, path, _ = _seed_gaps(client)
    selection = CandidateSelection.model_validate_json((path.parent / "selected_clips.json").read_text(encoding="utf-8"))
    original = [TranscriptSegment(start=1, end=2, text="前")]
    original.extend(TranscriptSegment(start=start, end=end, text=f"削除済み{index}")
                    for index, (start, end) in enumerate(blank_ranges))
    original.extend([TranscriptSegment(start=8, end=9, text="後"), TranscriptSegment(start=21, end=22, text="無関係")])
    review = build_subtitle_review(job_id, selection, original)
    blank_ids: set[str] = set()
    for segment in review.segments:
        if (segment.start, segment.end) in blank_ranges:
            segment.text = ""
            segment.edited = True
            blank_ids.add(segment.id)
    for clip in review.clips:
        clip.confirmed = True
        clip.subtitle_styles = [
            SubtitleStyleOverride(start=segment.start, end=segment.end,
                                  style=ClipTextStyle(fontSize=40 + 10 * index))
            for index, segment in enumerate(review.segments)
            if segment.id in blank_ids and clip.id in segment.affected_clip_ids
        ]
    before_styles = {clip.id: {(style.start, style.end): style.style for style in clip.subtitle_styles} for clip in review.clips}
    write_transcript_segments(original, path.parent / "transcript_segments.json")
    write_subtitle_review(review, path)
    old_gap = review.clips[0].gaps[0]
    assert (old_gap.source_start, old_gap.source_end) == (2, 8)
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/clips/normal/gaps/{old_gap.id}",
                        json={"acknowledged": True}).status_code == 200
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "insert_at_time", "segments": [], "clipId": "normal", "start": 4, "end": 6, "text": "拾えなかった発話",
    })
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    edited_range = [segment for segment in saved.segments if segment.start >= 2 and segment.end <= 8]
    assert [(segment.start, segment.end, segment.text) for segment in edited_range] == [
        (2, 4, ""), (4, 6, "拾えなかった発話"), (6, 8, ""),
    ]
    assert all(before.end <= after.start for before, after in zip(saved.segments, saved.segments[1:]))
    assert all(segment.id not in blank_ids for segment in saved.segments)
    assert {clip.id: clip.confirmed for clip in saved.clips} == {"normal": False, "other": True, "short": False}
    inserted = next(segment for segment in saved.segments if segment.text == "拾えなかった発話")
    assert inserted.source_indices == list(range(1, len(blank_ranges) + 1))
    for clip in saved.clips:
        assert clip.segment_ids == [segment.id for segment in saved.segments if clip.id in segment.affected_clip_ids]
        styles = {(style.start, style.end): style.style for style in clip.subtitle_styles}
        original_styles = before_styles[clip.id]
        if original_styles:
            first = next(iter(original_styles.values()))
            assert styles[(4, 6)] == first
            if clip.id == "normal":
                assert styles[(2, 4)] == first
            assert styles[(6, 8)] == list(original_styles.values())[-1]
    rendered = apply_reviewed_text(original, saved)
    assert [segment.text for segment in rendered] == ["前", "", "拾えなかった発話", "", "後", "無関係"]
    assert old_gap.id not in {gap.id for gap in saved.clips[0].gaps}
    assert saved.clips[0].gaps == []


def test_gap_insertion_still_rejects_nonempty_subtitle_without_partial_replacement(client: TestClient) -> None:  # noqa: F811
    job_id, path, _ = _seed_gaps(client)
    before = path.read_bytes()
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "insert_at_time", "segments": [], "clipId": "normal", "start": 1.5, "end": 3, "text": "重複禁止",
    })
    assert response.status_code == 422
    assert path.read_bytes() == before


def test_gap_insertion_preserves_legacy_one_millisecond_nonempty_boundary_tolerance(client: TestClient) -> None:  # noqa: F811
    job_id, path, review = _seed_gaps(client)
    previous = review.segments[0]
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "insert_at_time", "segments": [], "clipId": "normal", "start": 1.9995, "end": 3, "text": "境界から追加",
    })
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    retained = next(segment for segment in saved.segments if segment.id == previous.id)
    assert retained.model_dump() == previous.model_dump()
    assert any(segment.text == "境界から追加" for segment in saved.segments)


def test_gap_insertion_replaces_whole_empty_row_without_reviving_deleted_original(client: TestClient) -> None:  # noqa: F811
    job_id, path, review = _seed_gaps(client)
    blank = review.segments[0]
    blank.text = ""
    blank.edited = True
    write_subtitle_review(review, path)
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "insert_at_time", "segments": [], "clipId": "normal", "start": blank.start, "end": blank.end, "text": "新しい発話",
    })
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    assert blank.id not in {segment.id for segment in saved.segments}
    inserted = next(segment for segment in saved.segments if segment.text == "新しい発話")
    assert inserted.source_indices == [blank.index]
    original = [TranscriptSegment.model_validate(item) for item in json.loads(
        (path.parent / "transcript_segments.json").read_text(encoding="utf-8"),
    )]
    assert [segment.text for segment in apply_reviewed_text(original, saved)] == ["新しい発話", "アカネさんの話", "別の言葉"]
