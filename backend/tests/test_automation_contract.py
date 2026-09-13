import pytest

from app.jobs.automation import (
    automation_decision_input_hash,
    automation_manifest_path,
    build_automation_manifest,
    load_automation_manifest,
    write_automation_manifest,
)
from app.schemas import JobSettings


def test_automation_decision_input_hash_is_canonical_and_sensitive() -> None:
    first = automation_decision_input_hash(
        video_id="video_1",
        stored_path="videos/source.mp4",
        settings={"shortCount": 3, "normalClipCount": 2},
    )
    reordered = automation_decision_input_hash(
        video_id="video_1",
        stored_path="videos/source.mp4",
        settings={"normalClipCount": 2, "shortCount": 3},
    )
    changed = automation_decision_input_hash(
        video_id="video_1",
        stored_path="videos/source.mp4",
        settings={"normalClipCount": 2, "shortCount": 2},
    )

    assert first == reordered
    assert first != changed
    assert len(first) == 64


def test_shadow_manifest_round_trip_records_roles(tmp_path) -> None:
    settings = {
        "automationMode": "shadow",
        "initialSelectionProvider": "codex",
        "burnSubtitles": True,
        "requireClipPlanReview": True,
        "requireSubtitleReview": True,
    }
    document = build_automation_manifest(
        job_id="job_1",
        video_id="video_1",
        stored_path="videos/source.mp4",
        settings=settings,
    )
    output_path = write_automation_manifest(
        document,
        automation_manifest_path(tmp_path),
    )

    loaded = load_automation_manifest(output_path)

    assert loaded.requested_mode == "shadow"
    assert loaded.effective_mode == "shadow"
    assert loaded.fallback_reason is None
    assert loaded.roles.initial_selection == "codex"
    assert loaded.roles.clip_review == "manual"
    assert loaded.roles.subtitle_review == "manual"
    assert loaded.roles.final_quality_gate == "shadow_structural"


def test_guarded_manifest_connects_structural_quality_roles(tmp_path) -> None:
    settings = {
        "automationMode": "guarded",
        "initialSelectionProvider": "codex",
        "burnSubtitles": True,
        "requireClipPlanReview": True,
        "requireSubtitleReview": True,
    }
    output_path = write_automation_manifest(
        build_automation_manifest(
            job_id="job_1",
            video_id="video_1",
            stored_path="videos/source.mp4",
            settings=settings,
        ),
        automation_manifest_path(tmp_path),
    )

    loaded = load_automation_manifest(output_path)

    assert loaded.requested_mode == "guarded"
    assert loaded.effective_mode == "guarded"
    assert loaded.roles.clip_review == "guarded"
    assert loaded.roles.subtitle_review == "guarded"
    assert loaded.roles.final_quality_gate == "guarded_structural"


def test_auto_manifest_keeps_auto_only_with_all_fail_closed_stops(tmp_path) -> None:
    settings = {
        "automationMode": "auto",
        "initialSelectionProvider": "codex",
        "burnSubtitles": True,
        "requireClipPlanReview": True,
        "requireSubtitleReview": True,
    }

    output_path = write_automation_manifest(
        build_automation_manifest(
            job_id="job_1",
            video_id="video_1",
            stored_path="videos/source.mp4",
            settings=settings,
        ),
        automation_manifest_path(tmp_path),
    )
    loaded = load_automation_manifest(output_path)

    assert loaded.requested_mode == "auto"
    assert loaded.effective_mode == "auto"
    assert loaded.fallback_reason is None
    assert loaded.roles.initial_selection == "codex"
    assert loaded.roles.title_hook == "codex_auto"
    assert loaded.roles.clip_review == "auto_evidence"
    assert loaded.roles.subtitle_review == "auto_evidence"
    assert loaded.roles.final_quality_gate == "auto_evidence"


@pytest.mark.parametrize(
    ("clip_review", "subtitle_review"),
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_manual_mode_does_not_change_existing_review_flags(
    clip_review: bool,
    subtitle_review: bool,
) -> None:
    settings = JobSettings.model_validate(
        {
            "automationMode": "manual",
            "initialSelectionProvider": "codex",
            "requireClipPlanReview": clip_review,
            "requireSubtitleReview": subtitle_review,
        }
    )

    assert settings.automation_mode == "manual"
    assert settings.initial_selection_provider == "codex"
    assert settings.require_clip_plan_review is clip_review
    assert settings.require_subtitle_review is subtitle_review


def test_manual_workflow_forces_manual_automation_mode() -> None:
    settings = JobSettings.model_validate(
        {
            "workflowMode": "manual",
            "automationMode": "shadow",
            "normalClipCount": 0,
            "shortCount": 0,
            "burnSubtitles": False,
            "requireClipPlanReview": False,
            "requireSubtitleReview": False,
        }
    )

    assert settings.automation_mode == "manual"
