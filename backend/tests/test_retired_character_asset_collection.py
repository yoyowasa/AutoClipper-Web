"""Retired collection does not block old data or remove manually registered assets."""

import json

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

import app.db as db_module
from app.api.character_presets import CharacterSettings
from app.config import Settings
from app.db import get_db
from app.jobs import queue
from app.main import app
from app.models import AppPreference
from app.schemas import JobSettings
from app.storage.lifecycle import cleanup_expired_storage
from test_api_routes import client as client
from test_character_assets import assets_client as assets_client, _session, _upload


@pytest.mark.parametrize("key", ["autoHarvestCharacterAssets", "auto_harvest_character_assets"])
@pytest.mark.parametrize("enabled", [True, False])
def test_old_character_and_job_settings_discard_retired_switch(key, enabled):
    original = {key: enabled, "audienceFamiliarity": "unknown"}
    for model in (CharacterSettings, JobSettings):
        settings = model.model_validate(original)
        saved = settings.model_dump(by_alias=True)
        assert key not in saved
        assert saved["audienceFamiliarity"] == "unknown"
    assert original == {key: enabled, "audienceFamiliarity": "unknown"}
    # Only the retired key is discarded; unknown character settings remain invalid.
    with pytest.raises(ValueError):
        CharacterSettings.model_validate({"accidentalSetting": True})


def test_old_preset_get_does_not_rewrite_and_put_discards_switch(assets_client):  # noqa: F811
    api, preset_id, _paths = assets_client
    original = {"presets": [{"id": preset_id, "name": "旧設定", "settings": {
        "autoHarvestCharacterAssets": True, "audienceFamiliarity": "unknown",
    }}], "selectedName": "旧設定"}
    with _session() as db:
        db.get(AppPreference, "character_presets").value_json = original
        db.commit()
    loaded = api.get("/api/preferences/character-presets")
    assert loaded.status_code == 200
    assert "autoHarvestCharacterAssets" not in loaded.json()["presets"][0]["settings"]
    with _session() as db:
        assert db.get(AppPreference, "character_presets").value_json == original
    saved = api.put("/api/preferences/character-presets", json=original)
    assert saved.status_code == 200
    assert saved.json()["presets"][0]["id"] == preset_id
    with _session() as db:
        assert "autoHarvestCharacterAssets" not in db.get(AppPreference, "character_presets").value_json["presets"][0]["settings"]


def _legacy_rows(db):
    # Existing tables remain outside ORM metadata; there is no drop/migration.
    for name in ("character_asset_harvests", "character_asset_candidates"):
        db.execute(text(f"CREATE TABLE {name} (id TEXT PRIMARY KEY, state TEXT)"))
        db.execute(text(f"INSERT INTO {name} VALUES ('old', 'pending')"))
    db.commit()


def _assert_legacy_rows(db):
    for name in ("character_asset_harvests", "character_asset_candidates"):
        assert db.execute(text(f"SELECT * FROM {name}")).all() == [("old", "pending")]


def test_init_db_leaves_existing_collection_tables_and_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    with Session(engine) as db:
        _legacy_rows(db)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "settings", Settings(_env_file=None, storage_root=str(tmp_path / "storage")))
    db_module.init_db()
    assert {"character_assets", "character_asset_harvests", "character_asset_candidates"} <= set(inspect(engine).get_table_names())
    with Session(engine) as db:
        _assert_legacy_rows(db)


def test_cleanup_and_preset_deletion_preserve_legacy_candidates(assets_client):  # noqa: F811
    api, preset_id, paths = assets_client
    asset = _upload(assets_client).json()
    manual_png = paths.character_asset(preset_id, "joy", asset["id"])
    candidate = paths.root / "character_asset_candidates" / preset_id / "old-video" / "old.png"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"saved candidate")
    with _session() as db:
        _legacy_rows(db)
        result = cleanup_expired_storage(db, paths, terminal_retention_days=0, orphan_retention_hours=0)
        assert not result.errors
        _assert_legacy_rows(db)
    assert manual_png.exists() and candidate.read_bytes() == b"saved candidate"
    counts = api.get(f"/api/character-presets/{preset_id}/asset-counts")
    assert counts.status_code == 200 and counts.json() == {"assets": 1}
    assert api.request("DELETE", f"/api/character-presets/{preset_id}", json={"assets": 0}).status_code == 409
    assert manual_png.exists()
    assert api.request("DELETE", f"/api/character-presets/{preset_id}", json={"assets": 1}).status_code == 204
    assert not manual_png.exists()
    assert candidate.read_bytes() == b"saved candidate"
    with _session() as db:
        _assert_legacy_rows(db)


def test_removed_collection_routes_and_queue_entrypoints_are_absent():
    paths = app.openapi()["paths"]
    assert not any("asset-candidates" in path or "harvest" in path for path in paths)
    assert "/api/character-presets/{preset_id}/assets" in paths
    assert "/api/exports/{export_id}/thumbnail/candidates" in paths
    assert not hasattr(queue, "enqueue_character_asset_harvest")
    assert not hasattr(queue, "get_enqueue_character_asset_harvest")


def test_old_job_snapshot_get_ignores_switch_without_rewriting(assets_client):  # noqa: F811
    api, _preset_id, _paths = assets_client
    video = api.post("/api/videos/upload", files={"file": ("old.mp4", b"video", "video/mp4")}).json()
    created = api.post("/api/jobs", json={"videoId": video["videoId"], "settings": {"autoHarvestCharacterAssets": True}})
    assert created.status_code == 201
    job_id = created.json()["jobId"]
    from app.models import Job

    with next(app.dependency_overrides[get_db]()) as db:
        row = db.get(Job, job_id)
        assert "autoHarvestCharacterAssets" not in row.settings_json
        row.settings_json = {**row.settings_json, "autoHarvestCharacterAssets": True}
        original = json.loads(json.dumps(row.settings_json))
        db.commit()
    response = api.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert "autoHarvestCharacterAssets" not in json.dumps(response.json())
    with _session() as db:
        assert db.get(Job, job_id).settings_json == original
