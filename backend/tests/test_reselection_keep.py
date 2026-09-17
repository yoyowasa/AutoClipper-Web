import pytest

from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.candidates.select_candidates import CandidateSelection
from app.candidates.used_ranges import used_ranges
from app.jobs.clip_plan import build_clip_plan
from app.jobs.reselection_keep import merge_kept_candidates, prepare_kept_candidates


def candidate(index, kind="short"):
    return Candidate(id=f"clip_{index}", type=kind, start=index * 100, end=index * 100 + 30,
                     duration=30, transcript_text=f"scene {index}", short_layout="blur_background", boundary_refined=False,
                     title_style=ClipTextStyle(font_size=88))


@pytest.mark.parametrize("replacement_count", [3, 1])
def test_keep_two_of_five_preserves_metadata_and_only_replaces_remaining_slots(replacement_count):
    previous = CandidateSelection(shorts=[candidate(i) for i in range(5)])
    plan = build_clip_plan(job_id="test", selection=previous, settings={})
    plan.clips[0].start = 2
    plan.clips[0].duration = 28
    plan.clips[0].manually_adjusted = True
    settings = {"keptClipIds": ["clip_0", "clip_3"], "shortCount": 5, "normalClipCount": 0,
                "excludePreviousSelection": False}
    reduced, kept = prepare_kept_candidates(settings, plan, previous)
    assert reduced["shortCount"] == 3
    assert reduced["normalClipCount"] == 0
    assert used_ranges(reduced) == [(2, 30), (300, 330)]
    assert "_usedSourceRanges" not in settings
    fresh = [candidate(i + 10) for i in range(replacement_count)]
    merged = merge_kept_candidates(CandidateSelection(shorts=fresh), kept, plan)
    assert len(merged.shorts) == replacement_count + 2
    assert merged.shorts[0].start == 2
    assert merged.shorts[0].title_style == previous.shorts[0].title_style
    assert merged.shorts[0].short_layout == "blur_background"
    assert merged.shorts[0].title_style is not previous.shorts[0].title_style
    assert previous.shorts[0].start == 0
    assert merged.requested_short_count == 5
    assert merged.unfilled_requested_counts["short"] == 3 - replacement_count
    assert [c.id for c in merged.shorts] == (
        ["clip_0", "clip_10", "clip_11", "clip_3", "clip_12"] if replacement_count == 3
        else ["clip_0", "clip_10", "clip_3"])


def test_keep_counts_each_video_type_independently():
    previous = CandidateSelection(normal_clips=[candidate(0, "normal")], shorts=[candidate(1), candidate(2)])
    plan = build_clip_plan(job_id="test", selection=previous, settings={})
    reduced, kept = prepare_kept_candidates({"keptClipIds": ["clip_0"]}, plan, previous)
    assert reduced["normalClipCount"] == 0
    assert reduced["shortCount"] == 2
    merged = merge_kept_candidates(CandidateSelection(shorts=[candidate(10), candidate(11)]), kept, plan)
    assert merged.normal_clips == previous.normal_clips
    assert len(merged.shorts) == 2


@pytest.mark.parametrize("existing_count", [4, 5])
def test_four_kept_out_of_five_requested_can_reselect_one(existing_count):
    previous = CandidateSelection(shorts=[candidate(i) for i in range(existing_count)])
    settings = {"shortCount": 5, "normalClipCount": 0,
                "keptClipIds": [f"clip_{i}" for i in range(4)]}
    plan = build_clip_plan(job_id="test", selection=previous, settings=settings)
    reduced, kept = prepare_kept_candidates(settings, plan, previous)
    assert reduced["shortCount"] == 1
    merged = merge_kept_candidates(CandidateSelection(shorts=[candidate(10)]), kept, plan)
    assert len(merged.shorts) == 5
    assert merged.shorts[:4] == previous.shorts[:4]
    assert merged.shorts[4].id == "clip_10"
    assert merged.unfilled_requested_counts["short"] == 0
