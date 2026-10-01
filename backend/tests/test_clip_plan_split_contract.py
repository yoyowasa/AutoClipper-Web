import json
from pathlib import Path

from rq.utils import import_attribute

from app.jobs import clip_plan_runner, runner
from app.main import app


def test_openapi_paths_and_methods_match_before_clip_plan_split() -> None:
    fixture = Path(__file__).parent / "fixtures" / "openapi_routes_before_task167.json"
    before = json.loads(fixture.read_text(encoding="utf-8"))
    after = {path: sorted(methods) for path, methods in app.openapi()["paths"].items()}
    # Explicit additions after the split; the original routes remain identical.
    assert after == {
        **before,
        "/api/jobs/{job_id}/clip-plan/rejections": ["get"],
        "/api/character-presets/{preset_id}/assets": ["get", "post"],
        "/api/character-presets/{preset_id}/assets/{asset_id}": ["delete"],
        "/api/character-assets/{asset_id}/image": ["get"],
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
