import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

import app.db as db_module
import app.jobs.pipeline_common as pipeline
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.candidates.used_ranges import with_reselection_exclusions, used_ranges, near_duplicate_of_previous
from app.candidates.user_rejections import (
    user_rejection_reason,
    near_previous_except_context_expansion,
    rejection_context_guidance,
)
from app.config import Settings
from app.db import Base, get_db
from app.jobs.clip_plan_runner import run_clip_plan_reselection
from app.jobs.queue import get_enqueue_clip_plan_reselection
from app.main import app
from app.models import ClipRejection, Job, Video
from app.schemas import JobSettings
from app.source_clip_history import source_key
from app.storage.paths import get_storage_paths
from test_api_routes import client as client
from test_clip_plan_type_conversion import seed_plan
from test_codex_initial_selection import _request, _settings
from test_storage_api import storage_client as storage_client, _seed_expired_job


def judgment(reason, kind="normal", start=100, end=200, note=None):
    return dict(start=start, end=end, type=kind, reason=reason, note=note)


@pytest.mark.parametrize(
    "reason,kind,expected",
    [
        ("no_content", "normal", "rejected_by_user_no_content"),
        ("no_content", "short", "rejected_by_user_no_content"),
        ("weak_highlight", "normal", "rejected_by_user_weak_highlight"),
        ("weak_highlight", "short", None),
    ],
)
@pytest.mark.parametrize("exclude", [False, True])
def test_reason_coverage_is_half_the_rejected_range_across_types(reason, kind, expected, exclude):
    settings = {"_rejectedRanges": [judgment(reason)], "excludePreviousSelection": exclude}
    assert user_rejection_reason(150, 200, kind, settings) == expected
    assert user_rejection_reason(150.01, 200, kind, settings) is None
    assert user_rejection_reason(0, 1000, kind, settings) == expected


def test_context_first_allows_containing_expansion_and_second_rejects_without_changing_reason():
    row = judgment("missing_context")
    settings = {"_rejectedRanges": [row], "_previousProposedRanges": [(100, 200)]}
    assert user_rejection_reason(100, 200, "normal", settings) == "rejected_by_user_missing_context"
    assert user_rejection_reason(101, 199, "normal", settings) == "rejected_by_user_missing_context"
    assert near_duplicate_of_previous(95, 205, settings)
    assert user_rejection_reason(95, 205, "normal", settings) is None
    assert not near_previous_except_context_expansion(95, 205, "normal", settings)
    assert user_rejection_reason(100, 200, "short", settings) is None
    settings["_rejectedRanges"].append(dict(row))
    assert user_rejection_reason(95, 205, "normal", settings) == "rejected_by_user_missing_context_repeated"
    assert all(item["reason"] == "missing_context" for item in settings["_rejectedRanges"])


@pytest.mark.parametrize("reason", ["other", "unspecified"])
def test_other_and_unspecified_keep_near_duplicate_rule(reason):
    settings = {"_rejectedRanges": [judgment(reason)], "excludePreviousSelection": False}
    assert user_rejection_reason(101, 201, "normal", settings) == f"rejected_by_user_{reason}"
    assert user_rejection_reason(90, 290, "normal", settings) is None


def test_first_context_range_survives_on_merged_previous_exclusions_but_exports_stay_excluded():
    plan = SimpleNamespace(
        settings={"_previousProposedRanges": [(100, 200), (200, 300)], "_reselectionExcludedRanges": [(100, 300)]}, clips=[]
    )
    settings = with_reselection_exclusions(
        {"excludePreviousSelection": True, "_rejectedRanges": [judgment("missing_context")], "_usedSourceRanges": [(400, 500)]}, plan
    )
    assert used_ranges(settings) == [(200, 300), (400, 500)]
    assert settings["_previousProposedRanges"] == [(100, 200), (200, 300)]


def test_reason_is_recorded_before_and_after_boundary_refinement(monkeypatch):
    raw_bad = Candidate(id="raw", type="normal", start=100, end=200, duration=100, transcript_text="説明")
    refined_bad = Candidate(id="refined", type="normal", start=0, end=100, duration=100, transcript_text="説明")
    settings = {"_rejectedRanges": [judgment("no_content")], "excludePreviousSelection": True, "_usedSourceRanges": [(100, 200)]}

    def refine(candidates, **kwargs):
        return [candidate.model_copy(update={"start": 100, "end": 200}) for candidate in candidates]

    monkeypatch.setattr(pipeline, "refine_selected_candidates", refine)
    selection, candidates = pipeline._selection_with_refined_boundaries(
        CandidateSelection(normalClips=[raw_bad, refined_bad], requestedNormalCount=2),
        [raw_bad, refined_bad],
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings=settings,
        timeline_duration=300,
    )
    assert not selection.normal_clips and not candidates
    assert {r.candidate_id: r.reasons for r in selection.rejected_candidates} == {
        "raw": ["rejected_by_user_no_content"],
        "refined": ["rejected_by_user_no_content"],
    }
    assert selection.unfilled_requested_counts["normal"] == 2


def test_guidance_preserves_notes_for_all_reasons_and_context_expansion():
    rows = [
        judgment(reason, note=f"note-{reason}") for reason in ["no_content", "missing_context", "weak_highlight", "other", "unspecified"]
    ]
    request = _request(settings=_settings(_rejectedRanges=rows, normalClipGuidance="ユーザーの指示"))
    guidance = request.constraints.normal.context_guidance
    assert "前後へ広げた" in guidance and "より見どころの強い別の場面" in guidance
    for row in rows:
        assert row["note"] in guidance
    assert request.constraints.normal.guidance == "ユーザーの指示"
    assert len(guidance) <= 1000


@pytest.mark.parametrize("budget", [0, 5, 100, 1000])
def test_guidance_overflow_summarizes_without_failure(budget):
    rows = [judgment("no_content", start=i * 100, end=i * 100 + 90, note="補足" * 250) for i in range(39)]
    text = rejection_context_guidance("short", {"_rejectedRanges": rows}, max_length=budget)
    assert len(text) <= budget
    if budget >= 100:
        assert "39件" in text
    request = _request(settings=_settings(_rejectedRanges=rows, _previousProposedRanges=[(r["start"], r["end"]) for r in rows]))
    assert len(request.constraints.normal.context_guidance) <= 1000
    assert len(request.constraints.short.context_guidance) <= 1000


def reselection_request(**overrides):
    settings = JobSettings().model_dump(by_alias=True)
    names = [
        "normalClipSelectionPreset",
        "shortClipSelectionPreset",
        "normalClipGuidance",
        "shortClipGuidance",
        "excludeIntroOutro",
        "excludePromotionalContent",
        "selectionPolicy",
    ]
    return {**{name: settings[name] for name in names}, **overrides}


def enqueue_override(callback):
    app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: callback


def read_rows(job_id):
    with next(app.dependency_overrides[get_db]()) as db:
        return list(db.scalars(select(ClipRejection).where(ClipRejection.job_id == job_id)))


def test_api_records_explicit_notes_omissions_and_only_non_kept_clips(client):  # noqa: F811
    job_id, output = seed_plan(client, duration=100)
    queued = []
    enqueue_override(queued.append)
    response = client.post(
        f"/api/jobs/{job_id}/clip-plan/reselect",
        json=reselection_request(keptClipIds=["normal1"], rejections=[{"clipId": "normal0", "reason": "no_content", "note": "補足"}]),
    )
    assert response.status_code == 202, response.text
    assert queued == [job_id]
    rows = {row.clip_id: row for row in read_rows(job_id)}
    assert set(rows) == {"normal0", "short0"}
    assert (rows["normal0"].reason, rows["normal0"].note) == ("no_content", "補足")
    assert (rows["short0"].reason, rows["short0"].note) == ("unspecified", None)
    document = json.loads((output / "clip_plan.json").read_text(encoding="utf-8"))
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        video = db.get(Video, job.video_id)
        assert rows["normal0"].source_key == source_key(video, job.settings_json)
        assert rows["normal0"].clip_plan_revision == document["revision"]
        assert len(job.settings_json["_rejectedRanges"]) == 2
    history = client.get(f"/api/jobs/{job_id}/clip-plan/rejections")
    assert history.status_code == 200
    assert {r["clipId"] for r in history.json()} == set(rows)


def test_legacy_request_assigns_unspecified_and_worker_failure_keeps_ledger_and_latest_keeps(client):  # noqa: F811
    job_id, output = seed_plan(client, duration=100)
    enqueue_override(lambda _: None)
    assert client.post(f"/api/jobs/{job_id}/clip-plan/reselect", json=reselection_request(keptClipIds=["normal1"])).status_code == 202
    assert [r.reason for r in read_rows(job_id)] == ["unspecified", "unspecified"]

    def sessions():
        return next(app.dependency_overrides[get_db]())

    with pytest.raises(FileNotFoundError):
        run_clip_plan_reselection(job_id, session_factory=sessions, paths=app.dependency_overrides[get_storage_paths]())
    with sessions() as db:
        assert db.get(Job, job_id).status == "awaiting_clip_review"
    assert len(read_rows(job_id)) == 2
    with sessions() as db:
        settings = db.get(Job, job_id).settings_json
        assert len(settings["_rejectedRanges"]) == 2
        assert settings["keptClipIds"] == ["normal1"]
    restored = json.loads((output / "clip_plan.json").read_text(encoding="utf-8"))
    assert restored["settings"]["_rejectedRanges"] == settings["_rejectedRanges"]
    assert restored["settings"]["keptClipIds"] == ["normal1"]


@pytest.mark.parametrize(
    "payload",
    [
        {"keptClipIds": ["normal0"], "rejections": [{"clipId": "normal0", "reason": "other"}]},
        {"rejections": [{"clipId": "absent", "reason": "other"}]},
        {"rejections": [{"clipId": "normal0", "reason": "other"}] * 2},
        {"rejections": [{"clipId": "normal0", "reason": "guessed"}]},
        {"rejections": [{"clipId": "normal0", "reason": "other", "note": "x" * 501}]},
    ],
)
def test_invalid_rejections_fail_without_mutation(client, payload):  # noqa: F811
    job_id, output = seed_plan(client)
    before = (output / "clip_plan.json").read_bytes()
    enqueue_override(lambda _: pytest.fail("must not enqueue"))
    assert client.post(f"/api/jobs/{job_id}/clip-plan/reselect", json=reselection_request(**payload)).status_code == 422
    assert not read_rows(job_id)
    assert (output / "clip_plan.json").read_bytes() == before


def test_queue_failure_does_not_record_decisions_or_changed_settings(client):  # noqa: F811
    job_id, output = seed_plan(client)

    def fail(_):
        raise RuntimeError("queue unavailable")

    enqueue_override(fail)
    response = client.post(
        f"/api/jobs/{job_id}/clip-plan/reselect",
        json=reselection_request(rejections=[{"clipId": "normal0", "reason": "missing_context", "note": "context"}]),
    )
    assert response.status_code == 503
    assert not read_rows(job_id)
    with next(app.dependency_overrides[get_db]()) as db:
        assert "_rejectedRanges" not in db.get(Job, job_id).settings_json
        assert db.get(Job, job_id).status == "awaiting_clip_review"
    assert json.loads((output / "clip_plan.json").read_text(encoding="utf-8"))["state"] == "awaiting_review"


def test_init_db_adds_ledger_to_existing_database_without_losing_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name != "clip_rejections"])
    with Session(engine) as db:
        db.add(Video(id="existing", original_filename="old.mp4", stored_path="old.mp4"))
        db.commit()
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "settings", Settings(_env_file=None, storage_root=str(tmp_path / "storage")))
    db_module.init_db()
    db_module.init_db()
    assert "clip_rejections" in inspect(engine).get_table_names()
    assert not inspect(engine).get_foreign_keys("clip_rejections")
    with Session(engine) as db:
        assert db.get(Video, "existing") is not None
    engine.dispose()


def test_ledger_survives_job_video_and_file_cleanup(storage_client):  # noqa: F811
    api, sessions, paths = storage_client
    job_id, _ = _seed_expired_job(sessions, paths)
    with sessions() as db:
        db.add(
            ClipRejection(
                id="decision",
                job_id=job_id,
                video_id="vid_expired",
                source_key=None,
                clip_plan_revision=1,
                clip_id="old",
                clip_type="normal",
                start=0,
                end=100,
                reason="other",
                note="判断",
            )
        )
        db.commit()
    response = api.post("/api/storage/cleanup", headers={"X-AutoClipper-Action": "storage-cleanup"})
    assert response.status_code == 200 and response.json()["removedJobs"] == 1
    with sessions() as db:
        assert db.get(Job, job_id) is None
        assert db.get(Video, "vid_expired") is None
        assert db.get(ClipRejection, "decision").note == "判断"
    assert api.get(f"/api/jobs/{job_id}/clip-plan/rejections").json()[0]["reason"] == "other"


def test_plan_write_failure_does_not_enqueue_or_record(client, monkeypatch):  # noqa: F811
    import app.api.clip_plan as api

    job_id, output = seed_plan(client)
    before = (output / "clip_plan.json").read_bytes()

    def fail(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(api, "write_clip_plan", fail)
    enqueue_override(lambda _: pytest.fail("must not enqueue"))
    with pytest.raises(OSError):
        client.post(f"/api/jobs/{job_id}/clip-plan/reselect", json=reselection_request())
    assert not read_rows(job_id)
    assert (output / "clip_plan.json").read_bytes() == before
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job.status == "awaiting_clip_review"
        assert "_rejectedRanges" not in job.settings_json


def test_second_api_rejection_accumulates_history_and_keeps_original_reason_and_note(client):  # noqa: F811
    job_id, output = seed_plan(client, duration=100)
    enqueue_override(lambda _: None)

    def sessions():
        return next(app.dependency_overrides[get_db]())

    for note in ["first", "second"]:
        response = client.post(
            f"/api/jobs/{job_id}/clip-plan/reselect",
            json=reselection_request(
                keptClipIds=["normal1", "short0"],
                excludePreviousSelection=False,
                rejections=[{"clipId": "normal0", "reason": "missing_context", "note": note}],
            ),
        )
        assert response.status_code == 202, response.text
        with pytest.raises(FileNotFoundError):
            run_clip_plan_reselection(job_id, session_factory=sessions, paths=app.dependency_overrides[get_storage_paths]())
    rows = read_rows(job_id)
    assert len(rows) == 2
    assert {row.note for row in rows} == {"first", "second"}
    assert all(row.reason == "missing_context" for row in rows)
    with sessions() as db:
        settings = db.get(Job, job_id).settings_json
        assert user_rejection_reason(0, 110, "normal", settings) == "rejected_by_user_missing_context_repeated"


def test_second_nearly_identical_context_range_also_escalates():
    settings = {"_rejectedRanges": [judgment("missing_context"), judgment("missing_context", start=95, end=205)]}
    assert user_rejection_reason(90, 210, "normal", settings) == "rejected_by_user_missing_context_repeated"


def test_unspecified_manual_range_keeps_existing_behavior_but_explicit_no_content_is_enforced():
    from app.candidates.manual_ranges import MANUAL_SELECTION_REASON

    candidate = Candidate(
        id="manual", type="normal", start=100, end=200, duration=100, transcript_text="説明", selection_reason=MANUAL_SELECTION_REASON
    )
    for reason in ["other", "unspecified", "no_content"]:
        selected, _ = pipeline._filter_user_rejections(
            CandidateSelection(normalClips=[candidate]), [candidate], {"_rejectedRanges": [judgment(reason)]}
        )
        assert bool(selected.normal_clips) == (reason != "no_content")


def test_codex_candidate_pool_records_reason_even_when_previous_exclusions_are_on():
    from app.candidates.codex_initial_selection import CodexInitialSelectionResult
    from app.jobs.clip_plan_runner import _codex_selection_with_diverse_refined_shorts

    candidates = [
        Candidate(id="normal", type="normal", start=100, end=200, duration=100, transcript_text="説明です。", topic_key="topic"),
        Candidate(id="short", type="short", start=150, end=200, duration=50, transcript_text="説明です。"),
    ]
    selection = CandidateSelection(normalClips=[candidates[0]], shorts=[candidates[1]], requestedNormalCount=1, requestedShortCount=1)
    result, pool, _ = _codex_selection_with_diverse_refined_shorts(
        CodexInitialSelectionResult(selection=selection, candidates=candidates, summary={}),
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        timeline_duration=300,
        settings={"_rejectedRanges": [judgment("no_content")], "excludePreviousSelection": True, "_usedSourceRanges": [(100, 200)]},
    )
    assert not result.normal_clips and not result.shorts and not pool
    assert {row.candidate_id: row.reasons for row in result.rejected_candidates} == {
        "normal": ["rejected_by_user_no_content"],
        "short": ["rejected_by_user_no_content"],
    }


def test_500_character_note_is_kept_with_unspecified_reason(client):  # noqa: F811
    job_id, _ = seed_plan(client)
    enqueue_override(lambda _: None)
    note = "補" * 500
    response = client.post(
        f"/api/jobs/{job_id}/clip-plan/reselect",
        json=reselection_request(rejections=[{"clipId": "normal0", "reason": "unspecified", "note": note}]),
    )
    assert response.status_code == 202, response.text
    row = next(row for row in read_rows(job_id) if row.clip_id == "normal0")
    assert row.note == note and row.reason == "unspecified"


def test_exact_half_of_fractional_short_interval_is_rejected():
    settings = {"_rejectedRanges": [judgment("no_content", kind="short", start=0.1, end=0.3)]}
    assert user_rejection_reason(0.2, 0.3, "short", settings) == "rejected_by_user_no_content"
    assert user_rejection_reason(0.20001, 0.3, "short", settings) is None
