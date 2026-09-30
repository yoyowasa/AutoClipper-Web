from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.jobs as jobs_api
from app.db import get_db
from app.jobs.queue import (
    get_enqueue_clip_plan_boundary_update,
    get_enqueue_clip_plan_hook_scene_update,
    get_enqueue_clip_plan_reselection,
)
from app.main import app
from app.models import Job
from test_api_routes import client as client
from test_clip_plan_type_conversion import seed_plan


@pytest.mark.parametrize("action", ["boundary", "hook-scene", "reselect", "type"])
def test_clip_plan_action_claim_rejects_second_request_before_writing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, action: str  # noqa: F811
) -> None:
    job_id, output = seed_plan(client)
    if action == "boundary":
        method = client.patch
        url = f"/api/jobs/{job_id}/clip-plan/clips/normal0/boundary"
        payload = {"start": 1, "end": 29}
        dependency = get_enqueue_clip_plan_boundary_update
    elif action == "hook-scene":
        method = client.patch
        url = f"/api/jobs/{job_id}/clip-plan/clips/short0/hook-scene"
        payload = {"start": 43, "end": 45}
        dependency = get_enqueue_clip_plan_hook_scene_update
    elif action == "reselect":
        method = client.post
        url = f"/api/jobs/{job_id}/clip-plan/reselect"
        payload = {
            "normalClipSelectionPreset": "auto",
            "shortClipSelectionPreset": "auto",
            "normalClipGuidance": "",
            "shortClipGuidance": "",
            "excludeIntroOutro": True,
            "excludePromotionalContent": False,
            "selectionPolicy": "fill_requested",
        }
        dependency = get_enqueue_clip_plan_reselection
    else:
        method = client.patch
        url = f"/api/jobs/{job_id}/clip-plan/clips/normal0/type"
        payload = {"type": "short"}
        dependency = None

    queued: list[tuple[object, ...]] = []
    if dependency is not None:
        app.dependency_overrides[dependency] = lambda: lambda *args: queued.append(args)
    claimed = Event()
    release = Event()
    original_claim = jobs_api._claim_job_status

    def pause_after_claim(*args, **kwargs) -> None:
        original_claim(*args, **kwargs)
        if not claimed.is_set():
            claimed.set()
            assert release.wait(10)

    monkeypatch.setattr(jobs_api, "_claim_job_status", pause_after_claim)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(method, url, json=payload)
            assert claimed.wait(10)
            assert client.get(f"/api/jobs/{job_id}/clip-plan").json()["state"] == "awaiting_review"
            second = method(url, json=payload)
            assert second.status_code == 409, second.text
            assert queued == []
            release.set()
            first_response = first.result(timeout=10)
    finally:
        release.set()

    assert first_response.status_code == (200 if action == "type" else 202), first_response.text
    assert len(queued) == (0 if action == "type" else 1)
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == (
        "awaiting_clip_review" if action == "type" else
        "reselecting_clips" if action == "reselect" else "preparing_clip_review"
    )
    assert (output / "clip_plan.json").is_file()


def test_claim_rejects_a_job_loaded_before_another_request_claimed_it(
    client: TestClient,  # noqa: F811
) -> None:
    job_id, _ = seed_plan(client)
    with next(app.dependency_overrides[get_db]()) as first_db:
        with next(app.dependency_overrides[get_db]()) as second_db:
            first_job = first_db.get(Job, job_id)
            second_job = second_db.get(Job, job_id)
            assert first_job is not None and second_job is not None
            assert first_job.status == second_job.status == "awaiting_clip_review"
            jobs_api._claim_job_status(
                first_db, first_job, expected="awaiting_clip_review",
                new_status="preparing_clip_review", current_step="processing",
            )
            with pytest.raises(HTTPException) as error:
                jobs_api._claim_job_status(
                    second_db, second_job, expected="awaiting_clip_review",
                    new_status="preparing_clip_review", current_step="processing",
                )
            assert error.value.status_code == 409
            assert error.value.detail == "job state changed; reload"
