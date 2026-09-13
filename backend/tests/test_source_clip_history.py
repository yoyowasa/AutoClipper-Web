import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import build_audio_features
from app.candidates.codex_initial_selection import build_codex_initial_selection_request, CodexInitialSelectionResult
from app.candidates.manual_ranges import MANUAL_SELECTION_REASON
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.candidates.used_ranges import USED_RANGES_SETTING, overlaps_used
from app.db import Base, _create_engine
from app.jobs import runner
from app.models import ExportItem, Job, SourceClipUsage, Video
from app.source_clip_history import (
    SourceTimelineChanged, backfill_completed_history, record_completed_exports,
    selection_history_settings, source_key,
)
from app.storage.lifecycle import cleanup_expired_storage
from app.storage.paths import StoragePaths


@pytest.fixture
def context(tmp_path):
    engine = _create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure()
    with Session(engine) as db:
        yield db, paths
    engine.dispose()


def add_export(db, paths, *, job_id="old", status="completed", clip_type="normal", start=30, end=90):
    old = datetime.utcnow() - timedelta(days=30)
    video = Video(id=f"v_{job_id}", original_filename="配信 [s481oYpPtKg].mp4",
                  stored_path=str(paths.uploads / f"{job_id}.mp4"), duration=300, created_at=old)
    job = Job(id=job_id, video=video, status=status, settings_json={}, created_at=old, updated_at=old)
    metadata = paths.job_outputs(job.id) / f"{clip_type}.json"
    metadata.write_text(json.dumps({"start": start, "end": end}), encoding="utf-8")
    export = ExportItem(id=f"e_{job_id}", job=job, video=video, type=clip_type, title="test",
                        duration=end-start, score=90, video_path=str(metadata.with_suffix(".mp4")),
                        metadata_path=str(metadata))
    db.add_all([video, job, export])
    db.commit()
    return video, job


def new_upload(db, *, duration=300, settings=None, filename="改名済み [s481oYpPtKg].webm"):
    video = Video(id="v_new", original_filename=filename, stored_path="new-encoding.webm", duration=duration)
    job = Job(id="new", video=video, status="queued", settings_json=settings or {})
    db.add_all([video, job])
    db.commit()
    return video, job


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=s481oYpPtKg&t=20",
    "https://youtu.be/s481oYpPtKg",
    "https://www.youtube.com/live/s481oYpPtKg",
])
def test_identity_survives_redownload_and_can_use_source_url(url):
    video = Video(original_filename="different.mp4", stored_path="anything")
    assert source_key(video, {"youtubeSourceUrl": url}) == "youtube:s481oYpPtKg"
    video.original_filename = "same title [V3y0WVcTb2E].mkv"
    assert source_key(video, {"youtubeSourceUrl": url}) == "youtube:V3y0WVcTb2E"


def test_identity_never_matches_title_alone_or_untrusted_url():
    video = Video(original_filename="same title.mp4", stored_path="old.mp4")
    assert source_key(video, {"youtubeSourceUrl": "https://example.com/watch?v=s481oYpPtKg"}) is None
    video.stored_path = "/app/storage/uploads/.blobs/" + "a" * 64 + ".mp4"
    assert source_key(video, {}) == "sha256:" + "a" * 64


def test_redownload_backfills_old_exports_and_keeps_original_time(context):
    db, paths = context
    add_export(db, paths)
    add_export(db, paths, job_id="short", clip_type="short", start=85, end=110)
    video, job = new_upload(db)
    settings, summary = selection_history_settings(db, job, video, paths)
    assert settings[USED_RANGES_SETTING] == [(30, 110)]
    assert summary["historyCount"] == 2
    assert backfill_completed_history(db, paths) == 0
    assert len(db.scalars(select(SourceClipUsage)).all()) == 2


@pytest.mark.parametrize("status", ["failed", "awaiting_clip_review", "awaiting_subtitle_review", "rendering_normal"])
def test_unfinished_or_failed_exports_do_not_reserve_scenes(context, status):
    db, paths = context
    add_export(db, paths, status=status)
    assert backfill_completed_history(db, paths) == 0


def test_completed_transition_records_history_atomically_and_idempotently(context):
    db, paths = context
    _, job = add_export(db, paths, status="packaging_zip", clip_type="short")
    runner._set_status(db, job, "completed")
    assert len(db.scalars(select(SourceClipUsage)).all()) == 1
    assert record_completed_exports(db, job, paths) == 0
    # A revised export adds its used range without erasing a previously used one.
    (paths.job_outputs(job.id) / "short.json").write_text('{"start":25,"end":95}', encoding="utf-8")
    assert record_completed_exports(db, job, paths) == 1
    db.rollback()
    assert len(db.scalars(select(SourceClipUsage)).all()) == 1


def test_cleanup_keeps_history_even_for_exports_created_before_feature(context):
    db, paths = context
    _, job = add_export(db, paths)
    result = cleanup_expired_storage(db, paths, terminal_retention_days=7, orphan_retention_hours=24)
    assert result.errors == ()
    assert result.removed_jobs == 1
    assert db.get(Job, job.id) is None
    assert not (paths.outputs / job.id).exists()
    assert len(db.scalars(select(SourceClipUsage)).all()) == 1
    video, new_job = new_upload(db)
    settings, _ = selection_history_settings(db, new_job, video, paths)
    assert settings[USED_RANGES_SETTING] == [(30, 90)]


@pytest.mark.parametrize("settings", [{"reeditOf": "old"}, {"workflowMode": "manual"}])
def test_reedit_and_explicit_manual_workflow_are_not_blocked(context, settings):
    db, paths = context
    add_export(db, paths)
    video, job = new_upload(db, duration=200, settings=settings)
    effective, summary = selection_history_settings(db, job, video, paths)
    assert USED_RANGES_SETTING not in effective
    assert summary["skippedReason"] == "manual_or_existing_clip_reedit"


def test_same_job_retry_is_not_excluded_and_different_video_is_not_excluded(context):
    db, paths = context
    video, job = add_export(db, paths)
    settings, _ = selection_history_settings(db, job, video, paths)
    assert settings[USED_RANGES_SETTING] == []
    other, new_job = new_upload(db, filename="same title [V3y0WVcTb2E].mp4")
    settings, _ = selection_history_settings(db, new_job, other, paths)
    assert settings[USED_RANGES_SETTING] == []


def test_timeline_length_change_stops_automatic_exclusion(context):
    db, paths = context
    add_export(db, paths)
    video, job = new_upload(db, duration=250)
    with pytest.raises(SourceTimelineChanged):
        selection_history_settings(db, job, video, paths)


def candidate(name, start, end, clip_type="short", **updates):
    return Candidate(id=name, type=clip_type, start=start, end=end, duration=end-start,
                     transcript_text=f"{name}についての説明です。", final_score=95, ai_score=95,
                     should_use=True, topic_key=name, **updates)


@pytest.mark.parametrize("provider", ["codex", "legacy"])
def test_both_selection_paths_exclude_used_ranges_after_boundary_refinement(monkeypatch, provider):
    candidates = [candidate("expands", 20, 50), candidate("new", 130, 160), candidate("used", 0, 30)]
    settings = {USED_RANGES_SETTING: [(0, 20)], "normalClipCount": 0, "shortCount": 2,
                "shortMinDuration": 20, "shortMaxDuration": 75, "selectionPolicy": "fill_requested",
                "minFinalScore": 0, "rejectIncompleteSentence": False}

    def refine(items, **kwargs):
        return [item.model_copy(update={"start": 19, "duration": 31}) if item.id == "expands" else item for item in items]

    monkeypatch.setattr(runner, "refine_selected_candidates", refine)
    kwargs = dict(transcript_segments=[], silence_segments=[], scene_segments=[], settings=settings, timeline_duration=300)
    if provider == "codex":
        result = CodexInitialSelectionResult(
            selection=CandidateSelection(shorts=candidates[:2], requestedShortCount=2), candidates=candidates, summary={})
        selection, _, _ = runner._codex_selection_with_diverse_refined_shorts(result, **kwargs)
    else:
        selection, _, _ = runner._automatic_selection_with_diverse_refined_shorts(
            candidates, audio_features=build_audio_features(duration=300, silence_segments=[], volume_peak=0.5), **kwargs)
    assert [item.id for item in selection.shorts] == ["new"]
    assert selection.unfilled_requested_counts["short"] == 1


def test_any_overlap_is_removed_for_normal_and_short_but_manual_is_preserved():
    settings = {USED_RANGES_SETTING: [(30, 90)]}
    candidates = [candidate("normal", 0, 200, "normal"), candidate("short", 89, 110),
                  candidate("touch", 90, 120), candidate("manual", 35, 65, selection_reason=MANUAL_SELECTION_REASON)]
    assert [c.id for c in runner._unused_candidates(candidates, settings)] == ["touch", "manual"]
    assert not overlaps_used(0, 30, [(30, 90)])


def test_codex_input_omits_used_transcript_without_shifting_timestamps():
    transcript = [TranscriptSegment(start=i, end=i+10, text=f"{i}の説明です。") for i in (0, 10, 20, 90, 100, 110)]
    request = build_codex_initial_selection_request(
        job_id="new", transcript_segments=transcript, heatmap_segments=[], video_duration=300,
        settings={USED_RANGES_SETTING: [(10, 100)]},
    )
    assert [(item.start, item.end) for item in request.transcript] == [(0, 10), (100, 110), (110, 120)]
    assert "過去に使用した場面" in request.constraints.normal.guidance
    assert "過去に使用した場面" in request.constraints.short.guidance
