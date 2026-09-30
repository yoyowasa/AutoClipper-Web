import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, parse_selection_settings
from app.candidates.used_ranges import with_reselection_exclusions
from app.clip_allocation import allocate_selection, candidate_pool_counts, confirmed_counts
from app.jobs.clip_plan import build_clip_plan, load_clip_plan, write_clip_plan
from app.jobs.pipeline_common import _unused_candidates
from app.jobs.quality_gate import evaluate_selection_quality_gate
from app.jobs.reselection_keep import prepare_kept_candidates
from app.jobs.summaries import build_selected_clips_summary
from app.schemas import JobSettings
from test_codex_initial_selection import _request, _settings
from test_api_routes import client as client
from test_real_pipeline import fake_transcript
from test_clip_plan_type_conversion import seed_plan
from app.audio.volume_features import build_audio_features
from app.candidates.codex_initial_selection import CodexInitialSelectionResult
from app.db import get_db
from app.jobs.pipeline_common import AutoClipperPipelineDependencies
from app.jobs.runner import run_autoclipper_job
from app.jobs.clip_plan_runner import run_clip_plan_reselection
from app.jobs.queue import get_enqueue_clip_plan_reselection
import app.jobs.runner as runner
from app.main import app
from app.models import Job
from app.storage.paths import get_storage_paths
from app.video.probe import VideoMetadata
from app.video.scene_detect import SceneSegment


def candidate(name, kind="normal", score=90, start=0, **extra):
    duration = 90 if kind == "normal" else 30
    return Candidate(
        id=name,
        type=kind,
        start=start,
        end=start + duration,
        duration=duration,
        transcript_text="内容と見どころが成立する候補",
        topic_key=name,
        ai_score=score,
        final_score=score,
        used_ai_score=True,
        hard_gate_passed=True,
        should_use=True,
        boundary_refined=False,
        **extra,
    )


def settings(total=3, **overrides):
    return JobSettings(totalClipCount=total, **overrides).model_dump(by_alias=True, mode="json")


@pytest.mark.parametrize("total,valid", [(0, False), (1, True), (36, True), (37, False)])
def test_total_boundaries(total, valid):
    if valid:
        assert JobSettings(totalClipCount=total).clip_allocation_mode == "ai"
    else:
        with pytest.raises(ValidationError):
            JobSettings(totalClipCount=total)


@pytest.mark.parametrize(
    "values",
    [
        dict(totalClipCount=2, minNormalClipCount=2, minShortCount=1),
        dict(totalClipCount=36, minNormalClipCount=13),
        dict(totalClipCount=36, minShortCount=25),
        dict(clipAllocationMode="ai"),
    ],
)
def test_invalid_minima_and_missing_total(values):
    with pytest.raises(ValidationError):
        JobSettings(**values)


def test_legacy_settings_remain_fixed_and_ai_pool_is_capped():
    legacy = JobSettings(normalClipCount=1, shortCount=2)
    assert legacy.clip_allocation_mode == "fixed"
    old = {"normalClipCount": 1, "shortCount": 2}
    selection = CandidateSelection(normalClips=[candidate("n")])
    assert allocate_selection(selection, old) is selection
    assert candidate_pool_counts(old) == (1, 2)
    assert candidate_pool_counts(settings(36, minNormalClipCount=12, minShortCount=24)) == (24, 24)
    constraints = _request(settings=settings(36, minNormalClipCount=12, minShortCount=24)).constraints
    assert constraints.normal_candidate_count == constraints.short_candidate_count == 24
    assert constraints.total_clip_count == 36
    assert not parse_selection_settings(settings(crossTypeOverlapDedupe=True)).cross_type_overlap_dedupe
    assert old == {"normalClipCount": 1, "shortCount": 2}


@pytest.mark.parametrize("reverse", [False, True])
def test_minima_then_global_confidence_rank_and_no_cross_format_dedup(reverse):
    normals = [candidate("n1", score=97), candidate("n2", score=96, start=100)]
    shorts = [candidate("s1", "short", 70), candidate("s2", "short", 65, 150)]
    if reverse:
        normals.reverse()
        shorts.reverse()
    selected = allocate_selection(CandidateSelection(normalClips=normals, shorts=shorts), settings(minShortCount=1))
    assert [c.id for c in selected.normal_clips] == ["n1", "n2"]
    assert [c.id for c in selected.shorts] == ["s1"]
    assert selected.selected_by_type == {"normal": 2, "short": 1}
    assert selected.shortfall_reasons == {}
    # The normal and short at zero share the same scene.
    assert selected.normal_clips[0].start == selected.shorts[0].start


def test_partial_summary_keeps_rejection_counts_and_does_not_fill_with_weak_candidates(tmp_path):
    strong = candidate("strong")
    weak = candidate("weak", "short", 99, below_quality_threshold=True)
    selection = allocate_selection(
        CandidateSelection(
            normalClips=[strong],
            shorts=[weak],
            rejectedCandidates=[
                {"candidateId": "bad-duration", "type": "normal", "reasons": ["duration_out_of_range"]},
                {"candidateId": "bad-content", "type": "short", "reasons": ["rejected_by_user_no_content"]},
            ],
        ),
        settings(minShortCount=1),
    )
    summary = build_selected_clips_summary(selection, [])
    assert (summary["requestedTotal"], summary["selectedTotal"]) == (3, 1)
    assert summary["selectedByType"] == {"normal": 1, "short": 0}
    assert summary["shortfallReasons"] == {
        "duration_out_of_range": 1,
        "rejected_by_user_no_content": 1,
        "insufficient_strong_candidates": 2,
        "minimum_short_shortfall": 1,
    }
    plan = build_clip_plan("test", selection, settings(minShortCount=1))
    path = write_clip_plan(plan, tmp_path / "clip_plan.json")
    assert json.loads(path.read_text(encoding="utf-8"))["shortfallReasons"] == summary["shortfallReasons"]
    loaded = load_clip_plan(path)
    assert loaded.selected_total == 1 and loaded.minimum_shortfall["short"] == 1
    decision = evaluate_selection_quality_gate(
        job_id="test", selection=selection, transcript_segments=[], settings=settings(minShortCount=1), source_duration=1000
    )
    count_check = next(c for c in decision.checks if c.code == "selection.requested_counts")
    assert count_check.outcome == "pass" and count_check.evidence["shortage"] is True


def test_manual_and_keep_count_once_before_minima():
    manual = candidate("manual", selection_reason="manual_time_range")
    kept = manual.model_copy(update={"id": "kept", "selection_reason": "codex_direct"})
    selection = allocate_selection(
        CandidateSelection(normalClips=[manual, candidate("fresh", score=99, start=100)], shorts=[candidate("short", "short", 80)]),
        settings(2, minNormalClipCount=1, minShortCount=1),
        confirmed=[kept],
    )
    assert [c.id for c in selection.normal_clips] == ["kept"]
    assert [c.id for c in selection.shorts] == ["short"]
    assert selection.selected_total == 2


@pytest.mark.parametrize("exclude", [False, True])
def test_kept_scene_can_be_used_in_other_format_and_reduces_pool(exclude):
    previous = CandidateSelection(normalClips=[candidate("kept")])
    initial = settings(3, keptClipIds=["kept"], excludePreviousSelection=exclude)
    plan = build_clip_plan("test", previous, initial)
    reduced, kept = prepare_kept_candidates(with_reselection_exclusions(initial, plan), plan, previous)
    assert confirmed_counts(reduced) == {"normal": 1, "short": 0}
    assert candidate_pool_counts(reduced) == (2, 2)
    fresh = [candidate("duplicate"), candidate("other-format", "short")]
    assert [c.id for c in _unused_candidates(fresh, reduced)] == ["other-format"]
    allocated = allocate_selection(CandidateSelection(shorts=[fresh[1]]), initial, confirmed=kept)
    assert allocated.selected_total == 2
    request = _request(settings={**_settings(), **reduced})
    assert request.constraints.confirmed_normal_count == 1
    assert request.constraints.total_clip_count == 3
    assert request.constraints.normal.requested_count == request.constraints.short.requested_count == 2
    assert request.constraints.normal_candidate_count <= 24 and request.constraints.short_candidate_count <= 24


def test_manual_counts_are_separate_from_legacy_counts_and_preserved_when_kept():
    raw = settings(4, normalClipCount=0, shortCount=0, normalClipTimeRanges=[{"startSeconds": 0, "endSeconds": 90}])
    assert confirmed_counts(raw) == {"normal": 1, "short": 0}
    assert candidate_pool_counts(raw) == (3, 3)
    previous = CandidateSelection(normalClips=[candidate("manual", selection_reason="manual_time_range")])
    plan = build_clip_plan("test", previous, raw)
    reduced, _ = prepare_kept_candidates({**raw, "keptClipIds": ["manual"]}, plan, previous)
    assert confirmed_counts(reduced) == {"normal": 1, "short": 0}


def test_plan_counts_refresh_after_manual_edits(tmp_path):
    plan = build_clip_plan("test", CandidateSelection(normalClips=[candidate("n")]), settings(2))
    plan.clips.append(plan.clips[0].model_copy(update={"id": "short", "type": "short"}))
    path = write_clip_plan(plan, tmp_path / "plan.json")
    saved = load_clip_plan(path)
    assert saved.selected_total == 2 and saved.selected_by_type == {"normal": 1, "short": 1}
    assert saved.shortfall_reasons == {}


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("count", [0, 1])
def test_ai_pipeline_partial_goes_to_review_even_in_auto_mode_and_zero_fails(client, monkeypatch, count, manual):  # noqa: F811
    video = client.post("/api/videos/upload", files={"file": ("sample.mp4", b"media", "video/mp4")}).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": video["videoId"],
            "settings": {
                **({"normalClipTimeRanges": [{"startSeconds": 0, "endSeconds": 90}]} if manual else {}),
                "totalClipCount": 3,
                "initialSelectionProvider": "codex",
                "automationMode": "auto",
                "enableBoundaryRefinement": False,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["jobId"]
    paths = app.dependency_overrides[get_storage_paths]()
    candidates = [candidate("n", start=100 if manual else 0)] if count else []

    def fake_write(_input, output, **kwargs):
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake")
        return output

    def codex(**kwargs):
        return CodexInitialSelectionResult(
            selection=CandidateSelection(normalClips=candidates),
            candidates=candidates,
            summary={
                "provider": "codex",
                "status": "completed",
                "fallbackUsed": False,
                "error": None,
                "requestedNormalCount": 3,
                "requestedShortCount": 3,
                "selectedNormalCount": count,
                "selectedShortCount": 0,
                "threadId": None,
            },
        )

    monkeypatch.setattr(runner, "_evaluate_selection_quality_gate_for_mode", lambda **kwargs: (SimpleNamespace(route="continue"), None))
    visited = run_autoclipper_job(
        job_id,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=paths,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _: VideoMetadata(duration=240, width=1920, height=1080, fps=30, has_audio=True),
            extract_audio=fake_write,
            transcribe_audio=lambda _: fake_transcript(),
            detect_scenes=lambda _: [SceneSegment(start=0, end=240)],
            detect_silence=lambda *_: [],
            compute_audio_features=lambda _, duration, segments: build_audio_features(
                duration=duration, silence_segments=segments, volume_peak=0.5
            ),
            detect_black_screen=lambda _: [],
            codex_initial_selector=codex,
            subtitle_review_preview_renderer=fake_write,
        ),
    )
    status = client.get(f"/api/jobs/{job_id}").json()
    selected_count = count + int(manual)
    if selected_count:
        assert status["status"] == "awaiting_clip_review", status
        assert visited[-1] == "awaiting_clip_review"
        plan = client.get(f"/api/jobs/{job_id}/clip-plan").json()
        assert (plan["requestedTotal"], plan["selectedTotal"]) == (3, selected_count)
        if manual:
            assert any(c['selectionReason'] == 'manual_time_range' and c['start'] == 0 for c in plan['clips'])
        summary = json.loads((paths.job_outputs(job_id) / "selected_clips_summary.json").read_text(encoding="utf-8"))
        assert summary["shortfallReasons"]["insufficient_strong_candidates"] == 3 - selected_count
        if count == 1 and not manual:
            # A kept clip counts even if no new usable scene can be found.
            app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: lambda _: None
            response = client.post(f'/api/jobs/{job_id}/clip-plan/reselect', json={'keptClipIds': ['n'],
                **{key: settings()[key] for key in ('normalClipSelectionPreset', 'shortClipSelectionPreset',
                    'normalClipGuidance', 'shortClipGuidance', 'excludeIntroOutro', 'excludePromotionalContent', 'selectionPolicy')}})
            assert response.status_code == 202, response.text
            reselected = run_clip_plan_reselection(job_id,
                session_factory=lambda: next(app.dependency_overrides[get_db]()), paths=paths,
                dependencies=AutoClipperPipelineDependencies(codex_initial_selector=codex,
                                                            subtitle_review_preview_renderer=fake_write))
            assert reselected[-1] == 'awaiting_clip_review'
            updated = client.get(f'/api/jobs/{job_id}/clip-plan').json()
            assert updated['revision'] == 2 and updated['selectedTotal'] == 1
            assert [c['id'] for c in updated['clips']] == ['n']
            assert updated['shortfallReasons']['insufficient_strong_candidates'] == 2
    else:
        assert status["status"] == "failed"
        assert status["error"]["code"] in {"no_candidates_found", "no_usable_selection"}


def test_legacy_get_retry_keep_fixed_settings_unchanged(client):  # noqa: F811
    job_id, _ = seed_plan(client)
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        legacy = dict(job.settings_json)
        for key in ("clipAllocationMode", "totalClipCount", "minNormalClipCount", "minShortCount"):
            legacy.pop(key, None)
        job.settings_json = legacy
        job.status, job.error_code = "failed", "no_usable_selection"
        db.commit()
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    plan = client.get(f"/api/jobs/{job_id}/clip-plan").json()
    assert plan["requestedTotal"] is None
    response = client.post(f"/api/jobs/{job_id}/retry")
    assert response.status_code == 202, response.text
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.get(Job, job_id).settings_json == legacy
        retry_settings = db.get(Job, response.json()["jobId"]).settings_json
        assert all(retry_settings[key] == value for key, value in legacy.items())
        assert retry_settings["clipAllocationMode"] == "fixed" and retry_settings["totalClipCount"] is None


def test_normal_can_use_kept_short_scene_with_extended_short_limit():
    from app.jobs.pipeline_common import _is_repeated_normal_proposal
    kept = candidate("kept", "short").model_copy(update={"end": 90, "duration": 90})
    previous = CandidateSelection(shorts=[kept])
    raw = settings(2, shortMaxDuration=180, keptClipIds=["kept"], excludePreviousSelection=False)
    plan = build_clip_plan("test", previous, raw)
    reduced, _ = prepare_kept_candidates(with_reselection_exclusions(raw, plan), plan, previous)
    replacement = candidate("normal")
    assert _unused_candidates([replacement], reduced) == [replacement]
    assert not _is_repeated_normal_proposal(replacement, reduced)


def test_manual_workflow_counts_cannot_exceed_total(client):  # noqa: F811
    from test_duration_rules_api import editable_plan
    job_id, output = editable_plan(client, manual=True)
    plan = load_clip_plan(output / 'clip_plan.json')
    plan.settings.update(clipAllocationMode='ai', totalClipCount=2, minNormalClipCount=0, minShortCount=0)
    write_clip_plan(plan, output / 'clip_plan.json')
    response = client.post(f'/api/jobs/{job_id}/clip-plan/clips', json={'type': 'normal', 'start': 0, 'end': 90})
    assert response.status_code == 422
    assert len(load_clip_plan(output / 'clip_plan.json').clips) == 2
    plan.settings['totalClipCount'] = 3
    write_clip_plan(plan, output / 'clip_plan.json')
    response = client.post(f'/api/jobs/{job_id}/clip-plan/clips', json={'type': 'normal', 'start': 0, 'end': 90})
    assert response.status_code == 201, response.text
    assert response.json()['selectedTotal'] == 3
    assert response.json()['selectedByType'] == {'normal': 2, 'short': 1}
