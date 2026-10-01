from datetime import timedelta
import io
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.character_assets import ProcessedCharacterAsset
import app.db as db_module
from app.db import Base
import app.jobs.character_asset_frames as frames
import app.jobs.character_asset_harvest as harvesting
from app.jobs.character_asset_harvest_state import enqueue_completed_job_harvest
from app.jobs.queue import get_enqueue_character_asset_harvest
from app.main import app
from app.models import AppPreference, CharacterAsset, CharacterAssetCandidate, CharacterAssetHarvest, Job, Video, utc_now
from app.scoring.character_asset_classify import (
    CLASSIFY_SCHEMA, CodexCharacterAssetClassifier, Classification, contact_sheet, validate_classification,
)
from app.config import Settings
from app.storage.lifecycle import cleanup_expired_storage
from app.storage.paths import StoragePaths, get_storage_paths
from test_character_assets import _image, _session, _upload, assets_client as assets_client  # noqa: F401
from test_api_routes import client as client


@pytest.fixture()
def context(assets_client, tmp_path_factory):  # noqa: F811
    api, preset_id, _original_paths = assets_client
    # Keep the realistic preset/video/UUID directory structure below Windows MAX_PATH.
    paths = StoragePaths(tmp_path_factory.getbasetemp() / ("h" + uuid4().hex[:8]))
    paths.ensure()
    app.dependency_overrides[get_storage_paths] = lambda: paths
    video_id = "vid_" + uuid4().hex
    source = paths.uploads / "source.mp4"
    source.write_bytes(b"source retained for tests")
    with _session() as db:
        db.add(Video(id=video_id, stored_path=str(source), original_filename="processed.mp4", duration=3600))
        db.flush()
        db.add(Job(id="job_" + uuid4().hex, video_id=video_id, status="completed",
                   settings_json={"characterPresetId": preset_id, "characterPresetName": "素材用キャラ"}))
        db.commit()
        engine = db.get_bind()
    def factory():
        return Session(engine)
    queued = []
    app.dependency_overrides[get_enqueue_character_asset_harvest] = lambda: queued.append
    return SimpleNamespace(api=api, preset=preset_id, paths=paths, video=video_id, factory=factory, queued=queued)


def start(context):
    response = context.api.post(f"/api/character-presets/{context.preset}/asset-harvests", json={"videoId": context.video})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def seed_candidate(context, *, second=1, status="pending", age=0):
    identifier = "candidate_" + uuid4().hex
    path = context.paths.character_candidate(context.preset, context.video, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_image())
    with context.factory() as db:
        db.add(CharacterAssetCandidate(
            id=identifier, preset_id=context.preset, video_id=context.video, source_second=second,
            file_path=path.relative_to(context.paths.root).as_posix(), face_box={"x": .3, "y": .2, "w": .3, "h": .2},
            width=400, height=300, has_alpha=True, status=status, created_at=utc_now() - timedelta(days=age),
        ))
        db.commit()
    return identifier, path


@pytest.mark.parametrize("face", [None, (.5, .3, .15, .119), (.5, .15, .2, .2), (.5, .6, .2, .2)])
def test_scan_rejects_small_face_top_or_chest_margin(monkeypatch, face):
    monkeypatch.setattr(frames, "detect_anime_face", lambda _image: face)
    noise = np.random.default_rng(1).integers(0, 256, (720, 960, 3), dtype=np.uint8)
    assert frames.evaluate_frame(Image.fromarray(noise), 0) is None


def test_scan_sharp_face_passes_and_blur_fails(monkeypatch):
    monkeypatch.setattr(frames, "detect_anime_face", lambda _image: (.5, .35, .2, .2))
    noise = np.random.default_rng(1).integers(0, 256, (720, 960, 3), dtype=np.uint8)
    sharp = frames.evaluate_frame(Image.fromarray(noise), 17)
    assert sharp is not None and sharp.second == 17 and sharp.score > 0
    assert frames.evaluate_frame(Image.fromarray(cv2.GaussianBlur(noise, (51, 51), 15)), 17) is None


def test_thinning_keeps_strongest_near_time_or_face_hash_and_top_48():
    face = (.5, .35, .2, .2)
    near = [frames.FrameCandidate(0, face, 1, 0), frames.FrameCandidate(10, face, 3, 2**64 - 1),
            frames.FrameCandidate(30, face, 2, 0)]
    assert [item.second for item in frames.thin_candidates(near)] == [10, 30]
    repeated = [frames.FrameCandidate(0, face, 1, 0), frames.FrameCandidate(100, face, 2, 3)]
    assert [item.second for item in frames.thin_candidates(repeated)] == [100]
    random = np.random.default_rng(4)
    pool = [frames.FrameCandidate(index * 11, face, index, int.from_bytes(random.bytes(8), "big")) for index in range(60)]
    selected = frames.thin_candidates(pool)
    assert len(selected) == 48
    assert [item.score for item in selected] == list(range(59, 11, -1))


def test_stream_does_not_hold_images_and_keeps_global_strongest(monkeypatch):
    monkeypatch.setattr(frames, "sequential_frames", lambda _video: ((i, Image.new("RGB", (1, 1))) for i in range(30)))
    monkeypatch.setattr(frames, "evaluate_frame", lambda _image, second: frames.FrameCandidate(second, (.5, .3, .2, .2), second, 0))
    assert [item.second for item in frames.scan_candidates(Path("video"))] == [29]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_real_sequential_ffmpeg_scan_and_original_resolution_bust_crop(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x960:rate=5",
                    "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", str(source)], check=True, timeout=30)
    scanned = list(frames.sequential_frames(source))
    assert [second for second, _image in scanned] == [0, 1, 2]
    assert all(image.size == (960, 720) for _second, image in scanned)
    face = (.5, .35, .2, .25)
    monkeypatch.setattr(frames, "detect_anime_face", lambda _image: face)
    paths = StoragePaths(tmp_path / "storage")
    processed = frames.extract_candidate(source, frames.FrameCandidate(1, face, 100, 0), tmp_path / "full.jpg", paths)
    assert processed.width == 594 and processed.height == 792
    assert processed.face_box["h"] == pytest.approx(240 / 792)
    assert "背景付き（切り抜きモデル未導入）" in processed.warnings
    with Image.open(io.BytesIO(processed.png)) as image:
        assert image.format == "PNG" and image.width / image.height == .75


@pytest.mark.parametrize("size", [(300, 400), (200, 250)])
def test_crop_quality_uses_shared_300px_rule(size):
    image = Image.new("RGB", size)
    if size[0] == 200:
        with pytest.raises(ValueError, match="300"):
            frames.crop_bust(image, (.5, .35, .15, .25))
    else:
        # 300px source width does not make an undersized bust crop acceptable.
        with pytest.raises(ValueError, match="300"):
            frames.crop_bust(image, (.5, .35, .15, .25))


def classified_payload(count=1, reference=False):
    return {"candidates": [{"candidateId": i, "emotion": "joy", "usable": True, "issues": [],
                            "score": .8, "same_character": True if reference else None} for i in range(count)]}


@pytest.mark.parametrize("field,value", [("emotion", "happy"), ("score", 1.1), ("usable", "true"), ("issues", ["wrong"])])
def test_codex_classification_rejects_invalid_values(field, value):
    payload = classified_payload()
    payload["candidates"][0][field] = value
    with pytest.raises(ValueError):
        validate_classification(payload, count=1, has_reference=False)


def test_classification_requires_exact_ids_and_reference():
    payload = classified_payload(8, True)
    assert len(validate_classification(payload, count=8, has_reference=True).candidates) == 8
    with pytest.raises(ValueError):
        validate_classification(payload, count=8, has_reference=False)
    payload["candidates"][7]["candidateId"] = 0
    with pytest.raises(ValueError):
        validate_classification(payload, count=8, has_reference=True)


@pytest.mark.parametrize("reference", [False, True])
def test_classifier_sends_sheet_and_optional_reference_and_contract_matches(tmp_path, monkeypatch, reference):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import launcher.codex_bridge as bridge

    image = tmp_path / "frame.png"
    image.write_bytes(_image())
    sheet = contact_sheet([image] * 8, tmp_path / "sheet.jpg")
    generator = CodexCharacterAssetClassifier(storage_root=tmp_path, job_id="job", clip_id="assets")
    def generate(payload, images):
        assert payload == {"candidateCount": 8, "hasReference": reference}
        assert images == [sheet] + ([image] if reference else [])
        return Classification.model_validate(classified_payload(8, reference))
    monkeypatch.setattr(generator, "generate", generate)
    assert len(generator.classify(sheet, count=8, reference=image if reference else None).candidates) == 8
    assert "character_asset_classify" in bridge.ALLOWED_REQUEST_TASKS
    assert bridge._response_schema_sha256(CLASSIFY_SCHEMA) == bridge.EXPECTED_RESPONSE_SCHEMA_SHA256[generator.task]
    request = bridge.validate_request({
        "schemaVersion": 1, "task": generator.task, "requestId": "test", "prompt": "classify",
        "threadScope": "job:assets",
        "responseSchema": CLASSIFY_SCHEMA, "images": ["sheet.jpg"] + (["frame.png"] if reference else []),
    }, tmp_path)
    assert request.task == generator.task and len(request.image_paths) == 1 + int(reference)
    with pytest.raises(ValueError):
        generator.classify(sheet, count=9, reference=None)
    with pytest.raises(ValueError):
        contact_sheet([image] * 9, sheet)


def test_http_only_enqueues_once_and_lists_processed_video(context, monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Video processing must not run in HTTP")
    monkeypatch.setattr(harvesting, "scan_candidates", unexpected)
    identifier = start(context)
    assert start(context) == identifier
    assert context.queued == [identifier]
    sources = context.api.get(f"/api/character-presets/{context.preset}/harvest-videos").json()
    assert sources == [{"id": context.video, "filename": "processed.mp4", "duration": 3600}]
    with context.factory() as db:
        db.scalar(select(Job)).status = "failed"
        db.commit()
    assert context.api.post(f"/api/character-presets/{context.preset}/asset-harvests", json={"videoId": context.video}).status_code == 422


def test_zero_candidates_is_completed_with_reason(context, monkeypatch):
    identifier = start(context)
    monkeypatch.setattr(harvesting, "scan_candidates", lambda _source: [])
    harvesting.run_character_asset_harvest(identifier, session_factory=context.factory, paths=context.paths)
    result = context.api.get(f"/api/character-presets/{context.preset}/asset-candidates").json()
    assert result["candidates"] == []
    assert result["harvests"][0]["state"] == "completed"
    assert result["harvests"][0]["candidateCount"] == 0
    assert "キャラが大きく映る場面がありませんでした" in result["harvests"][0]["message"]


@pytest.mark.parametrize("reference,fail", [(False, False), (True, False), (False, True)])
def test_worker_batches_by_8_saves_fallback_and_rescan_does_not_duplicate(context, monkeypatch, reference, fail):
    if reference:
        _upload((context.api, context.preset, context.paths))
    monkeypatch.setattr(harvesting, "scan_candidates", lambda _source: [
        frames.FrameCandidate(i, (.5, .35, .2, .2), 100, i) for i in range(18)
    ])
    monkeypatch.setattr(harvesting, "extract_candidate", lambda *_args: ProcessedCharacterAsset(
        _image(), 400, 300, {"x": .3, "y": .2, "w": .3, "h": .2}, True, [],
    ))
    batches = []
    class Classifier:
        def classify(self, sheet, *, count, reference):
            batches.append((count, reference is not None))
            assert sheet.is_file()
            if fail:
                raise RuntimeError("Codex unavailable")
            return validate_classification(classified_payload(count, reference is not None), count=count,
                                           has_reference=reference is not None)
    identifier = start(context)
    harvesting.run_character_asset_harvest(identifier, session_factory=context.factory, paths=context.paths, classifier=Classifier())
    assert batches == [(8, reference), (8, reference), (2, reference)]
    result = context.api.get(f"/api/character-presets/{context.preset}/asset-candidates").json()
    assert len(result["candidates"]) == 18
    assert all(row["suggestedEmotion"] == (None if fail else "joy") for row in result["candidates"])
    assert all(row["usable"] == (None if fail else True) for row in result["candidates"])
    if fail:
        assert "表情を選んで採用" in result["harvests"][0]["message"]
    identifier = start(context)
    harvesting.run_character_asset_harvest(identifier, session_factory=context.factory, paths=context.paths, classifier=Classifier())
    assert len(batches) == 3
    with context.factory() as db:
        assert len(list(db.scalars(select(CharacterAssetCandidate)))) == 18
    assert len(list(context.paths.character_asset_candidates.rglob("*.png"))) == 18


def test_adopt_reassign_replace_reject_and_image(context):
    identifier, path = seed_candidate(context)
    base = f"/api/character-presets/{context.preset}/asset-candidates/{identifier}"
    assert context.api.get(f"/api/character-asset-candidates/{identifier}/image").content == path.read_bytes()
    assert context.api.post(base + "/reject").status_code == 204
    adopted = context.api.post(base + "/adopt", json={"emotion": "sorrow"})
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["emotion"] == "sorrow" and adopted.json()["slot"] == 1
    assert context.api.get(adopted.json()["imageUrl"]).content == path.read_bytes()
    assert context.api.post(base + "/adopt", json={"emotion": "joy"}).status_code == 409
    assert context.api.post(base + "/reject").status_code == 409
    for _i in range(4):
        assert _upload((context.api, context.preset, context.paths), emotion="sorrow").status_code == 201
    replacement, _path = seed_candidate(context, second=2)
    url = f"/api/character-presets/{context.preset}/asset-candidates/{replacement}/adopt"
    assert context.api.post(url, json={"emotion": "sorrow"}).status_code == 422
    old_id = adopted.json()["id"]
    result = context.api.post(url, json={"emotion": "sorrow", "replaceSlot": 1})
    assert result.status_code == 200 and result.json()["slot"] == 1
    assert context.api.get(f"/api/character-assets/{old_id}/image").status_code == 404
    with context.factory() as db:
        assert db.get(CharacterAssetCandidate, replacement).status == "adopted"
        assert len(list(db.scalars(select(CharacterAsset)))) == 5


def test_candidate_retention_and_permanent_adopted_asset(context):
    identifier, old = seed_candidate(context, age=31)
    adopted = context.api.post(
        f"/api/character-presets/{context.preset}/asset-candidates/{identifier}/adopt", json={"emotion": "fun"},
    ).json()
    rejected_id, rejected = seed_candidate(context, second=2, status="rejected", age=31)
    _pending_id, pending = seed_candidate(context, second=3, age=30)
    fresh_id, fresh = seed_candidate(context, second=4, age=29)
    now = utc_now()
    with context.factory() as db:
        result = cleanup_expired_storage(db, context.paths, terminal_retention_days=365, orphan_retention_hours=24, now=now)
        assert not result.errors
        assert db.get(CharacterAssetCandidate, rejected_id) is None
        assert db.get(CharacterAssetCandidate, fresh_id) is not None
    assert not old.exists() and not rejected.exists() and not pending.exists() and fresh.is_file()
    assert context.api.get(adopted["imageUrl"]).status_code == 200


def test_preset_delete_confirms_current_count_cascades_and_preserves_other_preset(context):
    _identifier, candidate = seed_candidate(context)
    asset = _upload((context.api, context.preset, context.paths)).json()
    start(context)
    document = context.api.get("/api/preferences/character-presets").json()
    document["presets"].append({"name": "別のキャラ", "settings": {}})
    second = context.api.put("/api/preferences/character-presets", json=document).json()["presets"][1]["id"]
    other = _upload((context.api, second, context.paths)).json()
    endpoint = f"/api/character-presets/{context.preset}"
    assert context.api.request("DELETE", endpoint, json={"assets": 0, "candidates": 0}).status_code == 409
    assert candidate.is_file()
    assert context.api.request("DELETE", endpoint, json={"assets": 1, "candidates": 1}).status_code == 204
    assert not candidate.exists()
    assert context.api.get(asset["imageUrl"]).status_code == 404
    assert context.api.get(other["imageUrl"]).status_code == 200
    with context.factory() as db:
        assert list(db.scalars(select(CharacterAssetCandidate))) == []
        assert list(db.scalars(select(CharacterAssetHarvest))) == []


@pytest.mark.parametrize("job_enabled,preset_enabled,expected", [(True, True, 1), (False, True, 0), (True, False, 0)])
def test_completed_job_auto_harvest_setting_on_off(context, monkeypatch, job_enabled, preset_enabled, expected):
    import app.jobs.queue as queue
    monkeypatch.setattr(queue, "enqueue_character_asset_harvest", context.queued.append)
    with context.factory() as db:
        document = get_presets(db).model_dump(by_alias=True, mode="json")
        document["presets"][0]["settings"]["autoHarvestCharacterAssets"] = preset_enabled
        db.get(AppPreference, "character_presets").value_json = document
        job = db.scalar(select(Job))
        job.settings_json = {**job.settings_json, "autoHarvestCharacterAssets": job_enabled}
        db.commit()
        enqueue_completed_job_harvest(db, job, context.paths)
        assert job.status == "completed"
    assert len(context.queued) == expected


def test_queue_failure_is_visible_without_failing_completed_export(context, monkeypatch):
    import app.jobs.queue as queue
    def fail(_identifier):
        raise RuntimeError("queue unavailable")
    monkeypatch.setattr(queue, "enqueue_character_asset_harvest", fail)
    with context.factory() as db:
        job = db.scalar(select(Job))
        enqueue_completed_job_harvest(db, job, context.paths)
        assert db.get(Job, job.id).status == "completed"
        assert db.scalar(select(CharacterAssetHarvest)).state == "failed"


def test_cleanup_protects_source_video_and_temp_of_running_harvest(context):
    identifier = start(context)
    with context.factory() as db:
        old = utc_now() - timedelta(days=100)
        job = db.scalar(select(Job))
        job.updated_at = old
        db.get(Video, context.video).created_at = old
        db.get(CharacterAssetHarvest, identifier).state = "running"
        db.commit()
        source = Path(db.get(Video, context.video).stored_path)
        cleanup_expired_storage(db, context.paths, terminal_retention_days=30, orphan_retention_hours=24)
        assert db.get(Video, context.video) is not None
    assert source.is_file()


def test_init_db_adds_candidate_and_harvest_tables_to_existing_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables
                                            if table.name not in {"character_asset_candidates", "character_asset_harvests"}])
    with Session(engine) as db:
        db.add(AppPreference(key="character_presets", value_json={"presets": []}))
        db.commit()
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "settings", Settings(_env_file=None, storage_root=str(tmp_path / "storage")))
    db_module.init_db()
    db_module.init_db()
    assert {"character_asset_candidates", "character_asset_harvests"} <= set(inspect(engine).get_table_names())
    with Session(engine) as db:
        assert db.get(AppPreference, "character_presets").value_json == {"presets": []}
    engine.dispose()


def test_worker_maintenance_expires_candidates_without_uploads(context, monkeypatch):
    from app.jobs import worker

    _identifier, old = seed_candidate(context, age=31)
    _fresh, fresh = seed_candidate(context, second=2, age=29)
    permanent = _upload((context.api, context.preset, context.paths)).json()
    calls = []
    monkeypatch.setattr(worker.Worker, "run_maintenance_tasks", lambda self: calls.append("rq"))
    monkeypatch.setattr(worker, "SessionLocal", context.factory)
    monkeypatch.setattr(worker, "get_storage_paths", lambda: context.paths)
    instance = object.__new__(worker.CharacterAssetWorker)
    instance.run_maintenance_tasks()
    assert calls == ["rq"]
    assert not old.exists() and fresh.is_file()
    assert context.api.get(permanent["imageUrl"]).status_code == 200


@pytest.mark.parametrize("operation", ["adopt", "delete_preset"])
def test_file_and_database_rollback_on_commit_failure(context, monkeypatch, operation):
    identifier, candidate_path = seed_candidate(context)
    asset = _upload((context.api, context.preset, context.paths)).json()
    original = candidate_path.read_bytes()
    def fail(_self):
        raise RuntimeError("commit failed")
    monkeypatch.setattr(Session, "commit", fail)
    with pytest.raises(RuntimeError, match="commit failed"):
        if operation == "adopt":
            context.api.post(f"/api/character-presets/{context.preset}/asset-candidates/{identifier}/adopt",
                             json={"emotion": "joy", "replaceSlot": 1})
        else:
            context.api.request("DELETE", f"/api/character-presets/{context.preset}", json={"assets": 1, "candidates": 1})
    assert candidate_path.read_bytes() == original
    assert context.api.get(asset["imageUrl"]).status_code == 200
    with context.factory() as db:
        assert db.get(CharacterAssetCandidate, identifier).status == "pending"
        assert db.get(CharacterAsset, asset["id"]) is not None
        assert len(list(db.scalars(select(CharacterAsset)))) == 1
        assert any(item.id == context.preset for item in get_presets(db).presets)
    assert not list(context.paths.root.rglob("*.deleted"))


def test_harvest_enqueue_uses_rq_valid_id_importable_task_and_failure_callback(monkeypatch):
    from redis import Redis
    from rq.job import Job as RQJob
    import app.jobs.queue as queue

    scheduled = []
    class RecordingQueue:
        def enqueue(self, function, *args, **kwargs):
            scheduled.append(RQJob.create(
                function, args=args, connection=Redis(), id=kwargs["job_id"],
                timeout=kwargs["job_timeout"], on_failure=kwargs["on_failure"],
            ))
    monkeypatch.setattr(queue, "get_queue", RecordingQueue)
    queue.enqueue_character_asset_harvest("harvest_" + "a" * 32)
    assert scheduled[0].func is harvesting.run_character_asset_harvest
    assert scheduled[0].failure_callback is harvesting.harvest_failure_callback
    assert scheduled[0].timeout == 14400
    assert scheduled[0].args == ("harvest_" + "a" * 32,)


def test_old_rq_failure_callback_does_not_fail_a_new_harvest_attempt(context, monkeypatch):
    old = start(context)
    with context.factory() as db:
        db.get(CharacterAssetHarvest, old).state = "failed"
        db.commit()
    new = start(context)
    assert old != new
    monkeypatch.setattr(harvesting, "SessionLocal", context.factory)
    harvesting.harvest_failure_callback(SimpleNamespace(args=(old,)), None, RuntimeError, None, None)
    with context.factory() as db:
        assert db.get(CharacterAssetHarvest, new).state == "queued"
