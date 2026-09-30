import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.duration_rules as rules
import app.jobs.pipeline_common as pipeline
from app.candidates.merge_boundaries import Candidate, parse_generation_settings
from app.candidates.select_candidates import CandidateSelection, select_candidates
from app.schemas import JobSettings, ClipPlanReselectionRequest
from app.candidates.codex_initial_selection import _previous_proposal_guidance, convert_codex_initial_selection_response
from test_codex_initial_selection import _request, _response, _settings


def test_duration_constants_match_shared_fixture():
    fixture = json.loads((Path(__file__).parent / 'fixtures/duration_rules.json').read_text(encoding='utf-8-sig'))
    assert {name: getattr(rules, name) for name in fixture} == fixture


@pytest.mark.parametrize('duration,valid', [(89, False), (90, True), (600, True), (601, False)])
def test_normal_duration_boundaries(duration, valid):
    assert (rules.validate_clip_duration('normal', duration, short_max=75) is None) == valid
    for field in ['normalMinDuration', 'normalMaxDuration']:
        if valid:
            JobSettings(**{field: duration})
        else:
            with pytest.raises(ValidationError):
                JobSettings(**{field: duration})


@pytest.mark.parametrize('maximum,valid', [(0, False), (1, True), (180, True), (181, False)])
def test_short_max_settings_boundaries(maximum, valid):
    if valid:
        JobSettings(shortMaxDuration=maximum, shortMinDuration=0)
    else:
        with pytest.raises(ValidationError):
            JobSettings(shortMaxDuration=maximum, shortMinDuration=0)


@pytest.mark.parametrize('overrides', [
    {'normalMinDuration': 100, 'normalMaxDuration': 90},
    {'shortMinDuration': 76, 'shortMaxDuration': 75}, {'shortMinDuration': -1},
])
def test_settings_reject_inverted_ranges(overrides):
    with pytest.raises(ValidationError):
        JobSettings(**overrides)


def test_legacy_settings_read_without_rewrite_and_search_bounds():
    legacy = {'normalMinDuration': 20, 'normalMaxDuration': 800, 'shortMinDuration': 400, 'shortMaxDuration': 300}
    restored = JobSettings.model_validate(legacy, context={'persisted_job': True})
    assert restored.normal_min_duration == 20
    assert restored.short_max_duration == 300
    bounded = rules.duration_search_settings(legacy)
    assert bounded == {'normalMinDuration': 90, 'normalMaxDuration': 600, 'shortMinDuration': 180, 'shortMaxDuration': 180}
    assert legacy['normalMinDuration'] == 20
    assert parse_generation_settings({'shortMinDuration': 0}).short_min_duration == 0


def test_short_minimum_is_not_enforced_and_hook_duration_is_included():
    assert rules.validate_clip_duration('short', 0.1, short_max=1) is None
    candidates = [Candidate(transcript_text='完結した説明です。', id='tiny', type='short', start=0, end=0.5, duration=0.5),
                  Candidate(
                      transcript_text='完結した説明です。', id='hook', type='short', start=10, end=84, duration=74,
                      hook_scene_start=11, hook_scene_end=13)]
    selection = select_candidates(candidates, settings={'normalClipCount': 0, 'shortCount': 2, 'shortMinDuration': 20,
                                                      'minFinalScore': 0, 'rejectIncompleteSentence': False})
    assert [c.id for c in selection.shorts] == ['tiny']
    assert selection.rejected_candidates[0].reasons == ['duration_out_of_range']
    assert selection.unfilled_requested_counts['short'] == 1


@pytest.mark.parametrize('budget', [0, 5, 24, 60])
def test_previous_proposal_guidance_degrades_without_failure(budget):
    ranges = [(index * 100, index * 100 + 90) for index in range(39)]
    guidance = _previous_proposal_guidance(ranges, max_length=budget)
    assert len(guidance) <= budget
    if budget == 24:
        assert guidance == '過去の提案範囲がほか39件あります'
    if budget == 5:
        assert guidance == ''


def test_codex_rejects_invalid_duration_and_retains_valid_normal():
    request = _request(settings=_settings(normalClipCount=2, shortCount=0))
    response = _response(request)
    valid = response.selected_clips[0]
    bad = valid.model_copy(update={'proposal_id': 'too_short', 'end': 89})
    converted = convert_codex_initial_selection_response(request, response.model_copy(update={'selected_clips': [bad, valid]}))
    assert len(converted.selection.normal_clips) == 1
    assert converted.dropped_normal_candidates[0].code == 'duration_out_of_range'
    assert converted.selection.rejected_candidates[0].reasons == ['duration_out_of_range']


def test_duration_checks_before_and_after_boundary_refinement(monkeypatch):
    candidates = [Candidate(transcript_text='完結した説明です。', id='before', type='normal', start=0, end=89, duration=89),
                  Candidate(transcript_text='完結した説明です。', id='after', type='normal', start=200, end=290, duration=90)]
    refined_ids = []
    def fake_refine(items, **kwargs):
        refined_ids.extend(item.id for item in items)
        return [item.model_copy(update={'end': item.start + 601, 'duration': 601}) for item in items]
    monkeypatch.setattr(pipeline, 'refine_selected_candidates', fake_refine)
    result, pool = pipeline._selection_with_refined_boundaries(
        CandidateSelection(normalClips=candidates, requestedNormalCount=2), candidates,
        transcript_segments=[], silence_segments=[], scene_segments=[], settings={}, timeline_duration=1000,
    )
    assert refined_ids == ['after']
    assert result.normal_clips == pool == []
    assert {r.candidate_id for r in result.rejected_candidates if r.reasons == ['duration_out_of_range']} == {'before', 'after'}
    assert result.unfilled_requested_counts['normal'] == 2


@pytest.mark.parametrize('duration', [89, 601])
def test_reselection_rejects_out_of_range_settings(duration):
    payload = {'normalMinDuration': duration, 'normalClipSelectionPreset': 'auto', 'shortClipSelectionPreset': 'auto',
               'normalClipGuidance': '', 'shortClipGuidance': '', 'excludeIntroOutro': True,
               'excludePromotionalContent': False, 'selectionPolicy': 'fill_requested'}
    with pytest.raises(ValidationError):
        ClipPlanReselectionRequest.model_validate(payload)


@pytest.mark.parametrize('context_length', [970, 999, 1000])
def test_previous_proposal_guidance_preserves_existing_context_and_user_guidance(monkeypatch, context_length):
    import app.candidates.codex_initial_selection as codex
    original = codex._build_constraints
    def existing_context(settings):
        constraints = original(settings)
        return constraints.model_copy(update={'normal': constraints.normal.model_copy(update={'context_guidance': '補' * context_length})})
    monkeypatch.setattr(codex, '_build_constraints', existing_context)
    ranges = [[index * 100, index * 100 + 90] for index in range(39)]
    settings = _settings(_previousProposedRanges=ranges, excludePreviousSelection=False, normalClipGuidance='指示' * 500)
    request = _request(settings=settings)
    assert request.constraints.normal.guidance == '指示' * 500
    assert request.constraints.normal.context_guidance.startswith('補' * context_length)
    assert len(request.constraints.normal.context_guidance) <= 1000
    assert settings['_previousProposedRanges'] == ranges
    if context_length == 970:
        assert 'ほか39件' in request.constraints.normal.context_guidance


def test_codex_short_hint_does_not_reject_below_hint_proposal():
    request = _request(settings=_settings(shortMinDuration=20))
    response = _response(request, short_start=100, short_end=105)
    response.selected_clips[1].evidence_segment_ids = ["seg_000004"]
    result = convert_codex_initial_selection_response(request, response)
    assert request.constraints.short.min_duration == 0
    assert '探索の目安は20秒以上' in request.constraints.short.context_guidance
    assert result.selection.shorts[0].duration == 5
