import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.candidates.merge_boundaries import Candidate
from app.db import get_db
from app.jobs.queue import get_enqueue_clip_plan_reselection, get_enqueue_retry_job
from app.legacy_settings import RETIRED_API_SETTING_KEYS
from app.main import app
from app.models import Job
from app.schemas import JobSettings
from test_api_routes import client as client
from test_clip_plan_type_conversion import seed_plan


def _legacy_settings() -> dict[str, object]:
    # Even obsolete values invalid under the old schema are inert when read.
    return {key: "retired-value" for key in RETIRED_API_SETTING_KEYS}


def test_settings_drop_retired_keys_and_preserve_internal_history() -> None:
    payload = {
        **_legacy_settings(), "mode": "high_quality",
        "_previousProposedRanges": [[10, 340]], "keptClipIds": ["normal0"],
    }
    settings = JobSettings.model_validate(payload).model_dump(by_alias=True, mode="json")
    assert not RETIRED_API_SETTING_KEYS.intersection(settings)
    assert settings["mode"] == "high_quality"
    assert settings["_previousProposedRanges"] == [[10, 340]]
    assert settings["keptClipIds"] == ["normal0"]
    assert payload["useOpenAIScoring"] == "retired-value"  # The saved input is not mutated.


@pytest.mark.parametrize("action", ["reselect", "retry"])
def test_legacy_settings_survive_get_reselection_and_retry(
    client: TestClient, action: str,  # noqa: F811
) -> None:
    job_id, _ = seed_plan(client)
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.settings_json = {**job.settings_json, **_legacy_settings()}
        db.commit()
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/clip-plan").status_code == 200
    queued: list[tuple[object, ...]] = []
    if action == "reselect":
        app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: lambda *args: queued.append(args)
        response = client.post(f"/api/jobs/{job_id}/clip-plan/reselect", json={
            "normalClipSelectionPreset": "auto", "shortClipSelectionPreset": "auto",
            "normalClipGuidance": "", "shortClipGuidance": "",
            "excludeIntroOutro": True, "excludePromotionalContent": False,
            "selectionPolicy": "fill_requested",
        })
    else:
        with next(app.dependency_overrides[get_db]()) as db:
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error_code = "no_usable_selection"
            db.commit()
        app.dependency_overrides[get_enqueue_retry_job] = lambda: lambda *args: queued.append(args)
        response = client.post(f"/api/jobs/{job_id}/retry")
    assert response.status_code == 202, response.text
    assert len(queued) == 1
    next_job_id = response.json()["jobId"]
    assert client.get(f"/api/jobs/{next_job_id}").status_code == 200
    with next(app.dependency_overrides[get_db]()) as db:
        saved = db.get(Job, next_job_id).settings_json
        assert not RETIRED_API_SETTING_KEYS.intersection(saved)


def test_historical_candidate_scores_still_round_trip() -> None:
    candidate = Candidate.model_validate({
        "id": "old", "type": "normal", "start": 0, "end": 330, "duration": 330,
        "ai_score": 85, "used_ai_score": True, "openai_scored": True,
        "openai_score_source": "preselection_pool", "title": "保存済みタイトル",
        "title_source": "openai", "transcript_text": "保存済み字幕",
    })
    restored = Candidate.model_validate_json(candidate.model_dump_json())
    assert restored.ai_score == 85
    assert restored.openai_score_source == "preselection_pool"
    assert restored.title_source == "openai"
    assert restored.title == "保存済みタイトル"


def test_app_has_no_paid_api_implementation_or_sdk_dependency() -> None:
    backend = Path(__file__).resolve().parents[1]
    for source in (backend / "app").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "openai", source
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] != "openai" for alias in node.names), source
    dependencies = (backend / "pyproject.toml").read_text(encoding="utf-8")
    assert '"openai>=' not in dependencies
    for file in ("scoring/openai_score.py", "audio/openai_transcript_correction.py"):
        assert not (backend / "app" / file).exists()
