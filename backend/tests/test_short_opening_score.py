from types import SimpleNamespace

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import _select_initial_short_pairs
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.clip_allocation import allocate_selection
from app.jobs.clip_plan_runner import _codex_selection_with_diverse_refined_shorts
from app.scoring.clip_preferences import CandidateClipPreference, build_clip_selection_preferences
from app.scoring.rule_score import apply_rule_score, incomplete_boundary_penalty, opening_score, score_candidate
from app.schemas import JobSettings


def candidate(name="test", text="数字123の実験です", start=0, **fields):
    return Candidate(id=name, type="short", start=start, end=start + 30, duration=30, transcript_text=text, **fields)


def test_opening_uses_only_three_seconds_without_word_timestamps():
    clip = candidate()
    strong = [TranscriptSegment(start=0, end=3, text="数字123の実験です")]
    weak = [TranscriptSegment(start=0, end=3, text="で、えー")]
    assert opening_score(clip, strong) == 15
    assert opening_score(clip, weak) == 0
    assert opening_score(clip, [*weak, TranscriptSegment(start=4, end=8, text="数字123の実験です")]) == 0
    assert opening_score(clip, []) == 0
    assert opening_score(clip, [TranscriptSegment(start=0, end=30, text="えーえーえー数字123の実験です")]) < 15


def test_overlapping_segments_do_not_inflate_speech_density():
    segments = [TranscriptSegment(start=0, end=1.5, text="実験です")] * 3
    assert opening_score(candidate(), segments) == 12.5


@pytest.mark.parametrize("text", ["で、えー今日は話します", "数字123の実験です", "plain topic today", "だからそれを話します"])
def test_known_score_matches_main_before_task191(text):
    # Values recorded from main 06d011c's unmodified score_candidate.
    clip = candidate(text=text)
    segments = [TranscriptSegment(start=0, end=3, text=text)]
    assert score_candidate(clip, transcript_segments=segments).final_score == 62.5
    known = CandidateClipPreference(audience_familiarity="known")
    assert score_candidate(clip, transcript_segments=segments, selection_preference=known).final_score == 62.5


def test_unknown_bonus_and_japanese_penalty_are_short_only():
    preference = CandidateClipPreference(audience_familiarity="unknown")
    clip = candidate()
    segments = [TranscriptSegment(start=0, end=3, text=clip.transcript_text)]
    scored = apply_rule_score(clip, transcript_segments=segments, selection_preference=preference)
    assert scored.opening_score == 15
    assert scored.rule_score == 77.5
    assert incomplete_boundary_penalty("で、えー") == 0
    assert incomplete_boundary_penalty("で、えー", audience_familiarity="unknown") == 10
    normal = clip.model_copy(update={"type": "normal", "transcript_text": "で、えー"})
    assert score_candidate(normal, selection_preference=preference).final_score == score_candidate(normal).final_score
    assert JobSettings().audience_familiarity == "known"
    preferences = build_clip_selection_preferences({"audienceFamiliarity": "unknown"})
    assert preferences["short"].audience_familiarity == "unknown"
    assert preferences["normal"].audience_familiarity == "known"


@pytest.mark.parametrize("mode,expected", [("known", "weak"), ("unknown", "strong")])
def test_codex_pair_ranking_preserves_confidence_for_known(mode, expected):
    pairs = [(SimpleNamespace(confidence=.9, proposal_id="weak", moment_key="weak"), candidate("weak", opening_score=0)),
             (SimpleNamespace(confidence=.8, proposal_id="strong", moment_key="strong"), candidate("strong", start=60, opening_score=15))]
    selected = _select_initial_short_pairs(pairs, requested_count=1, normal_candidates=[], max_overlap_ratio=.8,
                                           cross_type_overlap_dedupe=False, audience_familiarity=mode)
    assert selected[0][1].id == expected


@pytest.mark.parametrize("mode,expected", [("known", "weak"), ("unknown", "strong")])
def test_final_codex_pipeline_and_ai_allocation_keep_opening_rank(monkeypatch, mode, expected):
    weak = candidate("weak", text="で、えー", final_score=90, selection_reason="codex_direct", moment_key="weak")
    strong = candidate("strong", start=60, final_score=80, selection_reason="codex_direct", moment_key="strong")
    result = SimpleNamespace(candidates=[weak, strong], selection=CandidateSelection(
        normalClips=[], shorts=[weak], requestedShortCount=1))
    monkeypatch.setattr("app.jobs.clip_plan_runner._selection_with_refined_boundaries",
                        lambda selection, candidates, **_: (selection, candidates))
    settings = {"audienceFamiliarity": mode, "normalClipCount": 0, "shortCount": 1}
    selection, _, _ = _codex_selection_with_diverse_refined_shorts(
        result, transcript_segments=[TranscriptSegment(start=0, end=3, text=weak.transcript_text),
                                    TranscriptSegment(start=60, end=63, text=strong.transcript_text)],
        silence_segments=[], scene_segments=[], settings=settings, timeline_duration=120)
    assert selection.shorts[0].id == expected
    pool = CandidateSelection(normalClips=[], shorts=[weak, strong.model_copy(update={"opening_score": 15})])
    allocated = allocate_selection(pool, {**settings, "clipAllocationMode": "ai", "totalClipCount": 1})
    assert allocated.shorts[0].id == expected
