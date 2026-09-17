from types import SimpleNamespace

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import build_codex_initial_selection_request
from app.candidates.merge_boundaries import Candidate
from app.candidates.used_ranges import with_reselection_exclusions, used_ranges
from app.jobs.runner import _unused_candidates


def test_reselection_excludes_previous_rounds_from_codex_and_local_candidates():
    original = {"excludePreviousSelection": True, "_usedSourceRanges": [(80, 90)],
                "shortClipSelectionPreset": "funny", "shortClipGuidance": "笑えるやり取り"}
    plan = SimpleNamespace(settings={"_reselectionExcludedRanges": [[10, 20]]},
                           clips=[SimpleNamespace(start=30, end=40)])
    settings = with_reselection_exclusions(original, plan)
    assert used_ranges(settings) == [(10, 20), (30, 40), (80, 90)]
    assert original["_usedSourceRanges"] == [(80, 90)]
    segments = [TranscriptSegment(start=start, end=start+5, text=f"scene {start}")
                for start in (10, 30, 50, 80)]
    request = build_codex_initial_selection_request(
        job_id="reselect", transcript_segments=segments, heatmap_segments=[],
        video_duration=100, settings=settings,
    )
    assert [segment.start for segment in request.transcript] == [50]
    assert request.constraints.short.preset == "funny"
    assert "笑えるやり取り" in request.constraints.short.guidance
    candidates = [Candidate(id=str(s.start), type="short", start=s.start, end=s.end,
                            duration=5, transcript_text=s.text) for s in segments]
    assert [c.start for c in _unused_candidates(candidates, settings)] == [50]
    next_plan = SimpleNamespace(settings=settings, clips=[SimpleNamespace(start=50, end=55)])
    again = with_reselection_exclusions(original, next_plan)
    assert used_ranges(again) == [(10, 20), (30, 40), (50, 55), (80, 90)]


def test_reselection_exclusions_can_be_disabled_without_losing_export_history():
    settings = {"excludePreviousSelection": False, "_usedSourceRanges": [(80, 90)]}
    plan = SimpleNamespace(settings={"_reselectionExcludedRanges": [[10, 20]]},
                           clips=[SimpleNamespace(start=30, end=40)])
    assert with_reselection_exclusions(settings, plan) == settings
    assert with_reselection_exclusions(settings, None) == settings
