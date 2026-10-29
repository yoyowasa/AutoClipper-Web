import json
from pathlib import Path

from rq.utils import import_attribute

from app.jobs import clip_plan_runner, runner
from app.main import app


def test_openapi_paths_and_methods_match_before_clip_plan_split() -> None:
    fixture = Path(__file__).parent / "fixtures" / "openapi_routes_before_task167.json"
    before = json.loads(fixture.read_text(encoding="utf-8"))
    after = {path: sorted(methods) for path, methods in app.openapi()["paths"].items()}
    # Explicit additions after the split; task-195 retires the harvest/candidate routes.
    assert after == {
        **before,
        "/api/intelligence/channels/{channel_id}/choice-policies": ["get"],
        "/api/intelligence/channels/{channel_id}/choice-policies/{policy_id}/rollback": ["post"],
        "/api/jobs/{job_id}/clip-plan/rejections": ["get"],
        "/api/character-presets/{preset_id}/assets": ["get", "post"],
        "/api/character-presets/{preset_id}/assets/{asset_id}": ["delete"],
        "/api/character-assets/{asset_id}/image": ["get"],
        "/api/character-presets/{preset_id}/asset-counts": ["get"],
        "/api/character-presets/{preset_id}": ["delete"],
        "/api/exports/{export_id}/thumbnail/assets": ["get"],
        "/api/exports/{export_id}/thumbnail/candidates": ["get"],
        "/api/exports/{export_id}/thumbnail/candidates/prepare": ["post"],
        "/api/exports/{export_id}/thumbnail/candidates/{candidate_id}/image": ["get"],
        "/api/exports/{export_id}/posting-set": ["get"],
        "/api/exports/{export_id}/posting-text": ["get"],
        "/api/exports/{export_id}/posting-set.zip": ["get"],
        "/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/gaps/{gap_id}": ["patch"],
        "/api/jobs/{job_id}/subtitle-review/return-to-clip-plan": ["post"],
        "/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/unconfirm": ["post"],
        "/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/framing/reset": ["post"],
        "/api/intelligence/channels": ["get"],
        "/api/intelligence/channels/{channel_id}/production-aggregates": ["get"],
        "/api/intelligence/oauth/start": ["post"],
        "/api/intelligence/oauth/callback": ["get"],
        "/api/intelligence/channels/{channel_id}/sync": ["post"],
        "/api/intelligence/production-links": ["get"],
        "/api/intelligence/production-links/{record_family_id}": ["put"],
        "/api/intelligence/production-links/reconcile": ["post"],
        "/api/intelligence/channels/{channel_id}/analysis": ["get", "post"],
        "/api/intelligence/channels/{channel_id}/dashboard": ["get"],
        "/api/intelligence/channels/{channel_id}/analysis/{analysis_id}/evidence-videos": ["get"],
        "/api/intelligence/channels/{channel_id}/analysis/{analysis_id}/proposals/{proposal_id}/adopt": ["post"],
        "/api/intelligence/channels/{channel_id}/trials": ["get"],
        "/api/intelligence/channels/{channel_id}/trials/{trial_id}": ["delete", "put"],
    }


def test_rq_can_import_clip_plan_jobs_using_legacy_runner_paths() -> None:
    for name in (
        "run_clip_plan_reselection",
        "run_clip_plan_boundary_update",
        "run_clip_plan_hook_scene_update",
    ):
        relocated = getattr(clip_plan_runner, name)
        assert getattr(runner, name) is relocated
        assert import_attribute(f"app.jobs.runner.{name}") is relocated
        assert relocated.__module__ == "app.jobs.clip_plan_runner"
