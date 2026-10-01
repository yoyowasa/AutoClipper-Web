from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
import io
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.character_assets as asset_processing
import app.db as db_module
from app.character_asset_rules import CHARACTER_ASSET_MAX_BYTES
from app.config import Settings
from app.db import Base, get_db
from app.main import app
from app.models import AppPreference, CharacterAsset, Job, Video, utc_now
from app.storage.lifecycle import cleanup_expired_storage
from app.storage.paths import get_storage_paths
from test_api_routes import client as client


@contextmanager
def _session():
    yield from app.dependency_overrides[get_db]()


def _image(*, size=(400, 300), transparent=True, format="PNG") -> bytes:
    image = Image.new("RGBA" if transparent else "RGB", size, (180, 100, 80, 90) if transparent else (180, 100, 80))
    stream = io.BytesIO()
    image.save(stream, format=format)
    return stream.getvalue()


@pytest.fixture()
def assets_client(client):  # noqa: F811
    response = client.put("/api/preferences/character-presets", json={
        "presets": [{"name": "素材用キャラ", "settings": {}}], "selectedName": "素材用キャラ",
    })
    assert response.status_code == 200, response.text
    preset_id = response.json()["presets"][0]["id"]
    return client, preset_id, app.dependency_overrides[get_storage_paths]()


def _upload(context, *, emotion="joy", data=None):
    api, preset_id, _paths = context
    return api.post(f"/api/character-presets/{preset_id}/assets", data={"emotion": emotion},
                    files={"file": ("original.png", _image() if data is None else data, "image/png")})


def test_transparent_registration_list_image_and_delete(assets_client, monkeypatch):
    api, preset_id, paths = assets_client
    def unexpected_mask(*_args, **_kwargs):
        raise AssertionError("Already transparent images must not be matted")
    monkeypatch.setattr(asset_processing.anime_subject, "anime_character_mask", unexpected_mask)
    uploaded = _upload(assets_client)
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    assert asset["hasAlpha"] is True
    assert asset["slot"] == 1
    assert asset["faceBox"] is None
    assert asset["warnings"] == ["顔を検出できません（配置を手で調整してください）"]
    path = paths.character_asset(preset_id, "joy", asset["id"])
    assert list(path.parent.iterdir()) == [path]
    with _session() as db:
        saved = db.get(CharacterAsset, asset["id"])
        assert saved.file_path == path.relative_to(paths.root).as_posix()
        assert saved.width == 400 and saved.height == 300
    response = api.get(asset["imageUrl"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.format == "PNG" and image.size == (400, 300)
        assert image.getchannel("A").getextrema() == (90, 90)
        assert not image.info
    listed = api.get(f"/api/character-presets/{preset_id}/assets").json()
    assert listed["minSidePixels"] == 300 and listed["maxPerEmotion"] == 5
    assert listed["emotions"] == {"joy": [asset], "anger": [], "sorrow": [], "fun": []}
    assert api.delete(f"/api/character-presets/{preset_id}/assets/{asset['id']}").status_code == 204
    assert not path.exists()
    assert api.get(asset["imageUrl"]).status_code == 404
    assert api.get(f"/api/character-presets/{preset_id}/assets").json()["emotions"]["joy"] == []


def test_background_registration_without_model_and_stored_warnings(assets_client):
    api, preset_id, paths = assets_client
    uploaded = _upload(assets_client, data=_image(transparent=False))
    assert uploaded.status_code == 201
    asset = uploaded.json()
    assert asset["hasAlpha"] is False
    assert "背景付き（切り抜きモデル未導入）" in asset["warnings"]
    with Image.open(paths.character_asset(preset_id, "joy", asset["id"])) as image:
        assert image.getchannel("A").getextrema() == (255, 255)
    paths.models.mkdir()
    (paths.models / "isnet-anime.onnx").write_bytes(b"later-installed")
    # Reading must not run detection/matting again or change the original notice.
    assert api.get(f"/api/character-presets/{preset_id}/assets").json()["emotions"]["joy"][0] == asset


def test_detection_on_test_image_stores_normalized_top_left_face_box(assets_client, monkeypatch):
    class Detector:
        def detectMultiScale(self, gray, **_kwargs):
            assert gray.shape == (300, 400)
            return np.array([[40, 30, 80, 90]])
    monkeypatch.setattr(asset_processing.anime_subject, "_anime_cascade", lambda: Detector())
    asset = _upload(assets_client).json()
    assert asset["faceBox"] == {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}
    assert asset["warnings"] == []
    with _session() as db:
        assert db.get(CharacterAsset, asset["id"]).face_box == asset["faceBox"]


@pytest.mark.parametrize("detect_face", [True, False])
def test_opaque_image_uses_existing_anime_mask_once(assets_client, monkeypatch, detect_face):
    _api, preset_id, paths = assets_client
    prediction = np.zeros((1, 1, 1024, 1024), dtype="float32")
    prediction[0, 0, 100:1000, 350:650] = 1
    calls = []
    class MatteSession:
        def get_inputs(self):
            return [type("Input", (), {"name": "image"})()]
        def run(self, _outputs, _inputs):
            calls.append(1)
            return [prediction]
    monkeypatch.setattr(asset_processing.anime_subject, "_matte_session", lambda _path: MatteSession())
    monkeypatch.setattr(asset_processing.anime_subject, "detect_anime_face",
                        lambda _image: (0.5, 0.3, 0.2, 0.2) if detect_face else None)
    paths.models.mkdir()
    (paths.models / "isnet-anime.onnx").write_bytes(b"test-model")
    uploaded = _upload(assets_client, data=_image(transparent=False))
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    assert asset["hasAlpha"] is True and calls == [1]
    with Image.open(paths.character_asset(preset_id, "joy", asset["id"])) as image:
        assert image.getpixel((200, 90))[3] > 200
        assert image.getpixel((20, 90))[3] == 0


def test_five_per_emotion_sixth_rejected_and_deleted_slot_reused(assets_client):
    api, preset_id, paths = assets_client
    assets = [_upload(assets_client).json() for _ in range(5)]
    assert [asset["slot"] for asset in assets] == [1, 2, 3, 4, 5]
    assert _upload(assets_client).status_code == 422
    assert len(list(paths.character_assets.rglob("*.png"))) == 5
    assert _upload(assets_client, emotion="anger").status_code == 201
    assert api.delete(f"/api/character-presets/{preset_id}/assets/{assets[1]['id']}").status_code == 204
    assert _upload(assets_client).json()["slot"] == 2


def test_concurrent_registration_cannot_exceed_five(assets_client):
    for _ in range(4):
        assert _upload(assets_client).status_code == 201
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _upload(assets_client), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 422]
    assert len(list(assets_client[2].character_assets.rglob("*.png"))) == 5


@pytest.mark.parametrize("size,expected", [((299, 600), 422), ((600, 299), 422), ((300, 300), 201)])
def test_minimum_short_side_is_300_not_512(assets_client, size, expected):
    response = _upload(assets_client, data=_image(size=size))
    assert response.status_code == expected
    if expected == 422:
        assert "300px" in response.json()["detail"]
        assert not list(assets_client[2].character_assets.rglob("*.png"))


@pytest.mark.parametrize("format", ["JPEG", "WEBP"])
def test_supported_images_are_saved_only_as_png(assets_client, format):
    response = _upload(assets_client, data=_image(transparent=False, format=format))
    assert response.status_code == 201
    path = assets_client[2].character_asset(assets_client[1], "joy", response.json()["id"])
    with Image.open(path) as image:
        assert image.format == "PNG"
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("data", [b"broken", _image(format="GIF"), b"x" * (CHARACTER_ASSET_MAX_BYTES + 1)],
                         ids=["corrupt", "gif", "over-20mb"])
def test_invalid_formats_and_oversize_are_rejected_without_saved_files(assets_client, data):
    assert _upload(assets_client, data=data).status_code == 422
    assert not list(assets_client[2].character_assets.rglob("*.png"))


def test_unknown_preset_emotion_and_wrong_owner_are_rejected(assets_client):
    api, preset_id, _paths = assets_client
    assert _upload(assets_client, emotion="other").status_code == 422
    assert api.get("/api/character-presets/missing/assets").status_code == 404
    assert _upload((api, "missing", _paths)).status_code == 404
    asset = _upload(assets_client).json()
    assert api.delete(f"/api/character-presets/other/assets/{asset['id']}").status_code == 404
    assert api.get(asset["imageUrl"]).status_code == 200
    with pytest.raises(ValueError):
        _paths.character_asset(preset_id, "../outputs", asset["id"])


def test_old_preset_reading_and_overwriting_preserve_asset_ids_without_rewriting_get(assets_client):
    api, _preset_id, _paths = assets_client
    legacy = {"presets": [{"name": "旧設定", "settings": {}}], "selectedName": "旧設定"}
    with _session() as db:
        db.get(AppPreference, "character_presets").value_json = legacy
        db.commit()
    first = api.get("/api/preferences/character-presets").json()
    second = api.get("/api/preferences/character-presets").json()
    assert first == second
    preset_id = first["presets"][0]["id"]
    with _session() as db:
        assert db.get(AppPreference, "character_presets").value_json == legacy
    asset = _upload((api, preset_id, _paths)).json()
    assert api.put("/api/preferences/character-presets", json=legacy).json()["presets"][0]["id"] == preset_id
    assert api.get(f"/api/character-presets/{preset_id}/assets").json()["emotions"]["joy"] == [asset]
    assert api.put("/api/preferences/character-presets", json={"presets": [], "selectedName": ""}).status_code == 409
    assert api.request("DELETE", f"/api/character-presets/{preset_id}", json={"assets": 1, "candidates": 0}).status_code == 204
    assert api.get(asset["imageUrl"]).status_code == 404
    assert api.get(f"/api/character-presets/{preset_id}/assets").status_code == 404
    assert api.delete(f"/api/character-presets/{preset_id}/assets/{asset['id']}").status_code == 404


def test_init_db_adds_character_assets_to_existing_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name != "character_assets"])
    with Session(engine) as db:
        db.add(AppPreference(key="character_presets", value_json={"presets": []}))
        db.commit()
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "settings", Settings(_env_file=None, storage_root=str(tmp_path / "storage")))
    db_module.init_db()
    db_module.init_db()
    assert "character_assets" in inspect(engine).get_table_names()
    with Session(engine) as db:
        assert db.get(AppPreference, "character_presets").value_json == {"presets": []}
    engine.dispose()


def test_assets_survive_storage_cleanup_and_whole_storage_backup(assets_client, tmp_path):
    _api, preset_id, paths = assets_client
    asset = _upload(assets_client).json()
    png = paths.character_asset(preset_id, "joy", asset["id"])
    original_bytes = png.read_bytes()
    with _session() as db:
        old = utc_now() - timedelta(days=30)
        db.add(Video(id="expired", original_filename="old.mp4", stored_path="uploads/expired.mp4", created_at=old))
        db.add(Job(id="expired", video_id="expired", status="failed", updated_at=old))
        db.commit()
        paths.job_outputs("expired").joinpath("old.mp4").write_bytes(b"video")
        result = cleanup_expired_storage(db, paths, terminal_retention_days=1, orphan_retention_hours=1)
        assert result.removed_jobs == 1 and result.removed_videos == 1 and not result.errors
        assert db.get(CharacterAsset, asset["id"]) is not None
    assert png.read_bytes() == original_bytes
    backup = tmp_path / "storage-copy"
    shutil.copytree(paths.root, backup)
    assert (backup / png.relative_to(paths.root)).read_bytes() == original_bytes
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("./storage:/app/storage") == 2
    gpu = (root / "docker-compose.gpu.yml").read_text(encoding="utf-8")
    assert ":/app/storage" not in gpu  # Extra model-cache mounts do not replace the storage bind mount.


def test_database_rejects_duplicate_slot(assets_client):
    asset = _upload(assets_client).json()
    with _session() as db:
        saved = db.get(CharacterAsset, asset["id"])
        assert len(list(db.scalars(select(CharacterAsset)))) == 1
        assert json.loads(json.dumps(saved.face_box)) == asset["faceBox"]
        db.add(CharacterAsset(
            id="asset_" + "f" * 32, preset_id=saved.preset_id, emotion=saved.emotion, slot=saved.slot,
            file_path="unused.png", width=400, height=300, has_alpha=True,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_registration_commit_failure_removes_only_new_image(assets_client, monkeypatch):
    def fail_commit(_db):
        raise RuntimeError("test commit failure")
    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="test commit failure"):
        _upload(assets_client)
    assert not list(assets_client[2].character_assets.rglob("*.png"))
    assert not list(assets_client[2].character_assets.rglob("*.tmp"))
    with _session() as db:
        assert not list(db.scalars(select(CharacterAsset)))


def test_deletion_commit_failure_restores_image_and_row(assets_client, monkeypatch):
    api, preset_id, paths = assets_client
    asset = _upload(assets_client).json()
    path = paths.character_asset(preset_id, "joy", asset["id"])
    original = path.read_bytes()
    def fail_commit(_db):
        raise RuntimeError("test commit failure")
    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="test commit failure"):
        api.delete(f"/api/character-presets/{preset_id}/assets/{asset['id']}")
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]
    with _session() as db:
        assert db.get(CharacterAsset, asset["id"]) is not None
