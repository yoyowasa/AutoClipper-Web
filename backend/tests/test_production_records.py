import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import app.production_records as records
from app.db import Base, _create_engine
from app.downloads import export_download_name
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths


@pytest.fixture
def example(tmp_path: Path):
    paths = StoragePaths(tmp_path / "storage")
    engine = _create_engine(f"sqlite:///{tmp_path / 'records.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Video(id="vid_example", original_filename="private-original.mp4", stored_path="/private/source.mp4"))
        db.flush()
        job = Job(id="job_example", video_id="vid_example", status="completed", settings_json={
            "youtubeSourceTitle": "元配信", "youtubeSourceUrl": "https://www.youtube.com/watch?v=videoid&token=secret",
            "characterPresetName": "キャラ", "privateEmail": "private@example.test", "apiKey": "secret",
        })
        db.add(job)
        db.flush()
        output = paths.job_outputs(job.id)
        metadata = {
            "start": 100, "end": 175, "body_duration": 75, "hook_scene_start": 101, "hook_scene_end": 104,
            "overlay_title": "画面タイトル", "hook_text": "フック", "thumbnail_kicker": "小見出し",
            "thumbnail_line1": "上", "thumbnail_line2": "下", "post_metadata_source": "codex",
            "title_candidates": [{"id": "one", "title": "候補", "intent": "factual", "reason": "候補の説明",
                                  "transcript": "PRIVATE TRANSCRIPT", "path": "/private/candidate"}],
            "selected_title_id": "one", "recommended_title_id": "one", "thumbnail_subject_source": "asset",
            "thumbnail_character_asset_id": "asset_example", "thumbnail_emotion": "joy",
            "video_path": "/private/render.mp4", "transcript_text": "PRIVATE TRANSCRIPT", "apiKey": "secret",
        }
        path = output / "short.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        selected = {"id": "cand_example", "reason": "見どころ", "topic_key": "topic", "opening_score": 12,
                    "final_score": 80, "transcript_text": "PRIVATE TRANSCRIPT"}
        (output / "selected_clips.json").write_text(json.dumps({"normalClips": [], "shorts": [selected]}), encoding="utf-8")
        adjustment = {"proposalId": "proposal_1", "reason": "parent_ratio_adjusted", "originalParentStart": 100,
                      "originalParentEnd": 190, "originalRatio": 1.2, "adjustedParentStart": 81.25,
                      "adjustedParentEnd": 193.75, "adjustedRatio": 1.5, "sourceLimited": False}
        (output / "codex_initial_selection_summary.json").write_text(
            json.dumps({"parentRangeAdjustments": [adjustment]}), encoding="utf-8")
        export = ExportItem(id="exp_example", job_id=job.id, video_id=job.video_id, candidate_id="cand_example", type="short",
                            title='題材:なぜ？/実験*', duration=78, score=80,
                            video_path=str(output / "short_01.mp4"), metadata_path=str(path))
        db.add(export)
        db.commit()
        yield db, job, export, paths
    engine.dispose()


def test_contract_and_download_name_projection(example):
    db, job, export, paths = example
    records.record_completed_productions(db, job, paths)
    payload = json.loads(paths.production_record(export.id).read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == payload["revision"] == 1
    assert payload["recordId"] == export.id and payload["jobId"] == job.id
    assert payload["publicationTitle"] == export_download_name(export).stem == "題材：なぜ？／実験＊"
    assert payload["bodyDurationSeconds"] == 75 and payload["completedDurationSeconds"] == 78
    assert (payload["hookSceneStart"], payload["hookSceneEnd"]) == (1, 4)
    assert payload["source"] == {"title": "元配信", "url": "https://www.youtube.com/watch?v=videoid", "start": 100, "end": 175}
    assert payload["selection"]["reason"] == "見どころ" and payload["selection"]["topicKey"] == "topic"
    assert payload["selection"]["parentRangeAdjustments"][0]["originalRatio"] == 1.2
    assert payload["titleCandidates"]["intent"] == "factual"
    assert payload["titleCandidates"]["selectedId"] == payload["titleCandidates"]["recommendedId"] == "one"
    assert payload["thumbnail"]["source"] == "character_asset" and payload["thumbnail"]["assetId"] == "asset_example"
    serialized = json.dumps(payload)
    for excluded in ("/private", "PRIVATE TRANSCRIPT", "private@example", "secret", "apiKey", "transcript"):
        assert excluded not in serialized
    assert not list(paths.production_records.glob("*.tmp"))


def test_rerender_increments_revision_preserves_creation_time(example):
    _db, job, export, paths = example
    path = records.write_production_record(job, export, paths)
    before = json.loads(path.read_text(encoding="utf-8"))
    export.title = "更新タイトル"
    records.write_production_record(job, export, paths)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["revision"] == 2 and after["createdAt"] == before["createdAt"]
    assert after["updatedAt"] > before["updatedAt"] and after["publicationTitle"] == export.title


def test_legacy_missing_fields_and_container_paths(example):
    _db, job, export, paths = example
    export.metadata_path = "/app/storage/outputs/job_example/short.json"
    job.settings_json = {}
    record = records.build_production_record(job, export, paths)
    assert record.bodyDurationSeconds == 75
    assert record.source.title is None and record.characterPresetName is None
    export.metadata_path = None
    export.title = ""
    record = records.build_production_record(job, export, paths)
    assert record.publicationTitle == "short_01"
    assert record.hookSceneStart is None and record.thumbnail.source == "unknown"


def test_record_failure_is_warning_only(example, monkeypatch, caplog):
    db, job, _export, paths = example

    def fail(*_args, **_kwargs):
        raise OSError("secret must not be logged")

    monkeypatch.setattr(records, "write_json_atomic", fail)
    records.record_completed_productions(db, job, paths)
    db.refresh(job)
    assert job.status == "completed"
    assert "Production record failed" in caplog.text and "OSError" in caplog.text
    assert "secret must not be logged" not in caplog.text


def test_backfill_dry_run_protection_and_force(example):
    db, job, export, paths = example
    before = {p: p.read_bytes() for p in paths.root.rglob("*") if p.is_file()}
    assert records.backfill_production_records(db, paths)["eligible"] == 1
    assert not paths.production_records.exists()
    assert before == {p: p.read_bytes() for p in paths.root.rglob("*") if p.is_file()}
    assert records.backfill_production_records(db, paths, execute=True)["written"] == 1
    path = paths.production_record(export.id)
    original = path.read_bytes()
    export.title = "changed"
    db.commit()
    assert records.backfill_production_records(db, paths, execute=True)["skipped"] == 1
    assert path.read_bytes() == original
    dry_force = records.backfill_production_records(db, paths, force=True)
    assert dry_force["eligible"] == 1 and path.read_bytes() == original
    assert records.backfill_production_records(db, paths, execute=True, force=True)["written"] == 1
    assert json.loads(path.read_bytes())["revision"] == 2
    job.status = "failed"
    db.commit()
    assert records.backfill_production_records(db, paths, force=True)["eligible"] == 0


def test_backfill_cli_defaults_to_dry_run(example, monkeypatch, capsys):
    import app.maintenance as maintenance

    db, _job, _export, paths = example
    monkeypatch.setattr(maintenance, "SessionLocal", lambda: Session(db.bind))
    monkeypatch.setattr(maintenance, "get_settings", lambda: type("Settings", (), {"storage_root": str(paths.root)})())
    assert maintenance.main(["backfill-production-records"]) == 0
    assert json.loads(capsys.readouterr().out)["eligible"] == 1
    assert not paths.production_records.exists()


@pytest.mark.parametrize("export_time", [
    datetime(2026, 10, 1, 12, 34, 56, 123456),
    datetime(2026, 10, 1, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=9))),
    datetime(2099, 1, 1, tzinfo=UTC),
])
@pytest.mark.parametrize("force", [False, True])
def test_backfill_uses_export_time_including_force(example, export_time, force):
    db, job, export, paths = example
    if force:
        # Reproduce task-198's execution-time createdAt on an existing record.
        records.write_production_record(job, export, paths)
        previous = json.loads(paths.production_record(export.id).read_text(encoding="utf-8"))
    export.created_at = export_time
    # Keep the aware timestamp in memory; SQLite intentionally stores timestamps without a timezone.
    db.flush()
    expected = export_time.replace(tzinfo=UTC) if export_time.tzinfo is None else export_time.astimezone(UTC)
    before = {p: p.read_bytes() for p in paths.root.rglob("*") if p.is_file()}
    assert records.backfill_production_records(db, paths, force=force)["eligible"] == 1
    assert before == {p: p.read_bytes() for p in paths.root.rglob("*") if p.is_file()}
    report = records.backfill_production_records(db, paths, execute=True, force=force)
    assert report["errors"] == [] and report["written"] == 1
    payload = json.loads(paths.production_record(export.id).read_text(encoding="utf-8"))
    assert payload["createdAt"] == expected.isoformat().replace("+00:00", "Z")
    assert payload["choiceHistory"][-1]["stage"] == "observed"
    assert "appliedAt" not in payload["choiceHistory"][-1] or payload["choiceHistory"][-1]["appliedAt"] is None
    assert datetime.fromisoformat(payload["updatedAt"]) >= expected
    assert payload["revision"] == (previous["revision"] + 1 if force else 1)


def test_normal_record_creation_still_uses_current_time(example):
    _db, job, export, paths = example
    export.created_at = datetime(2020, 1, 1)
    before = datetime.now(UTC)
    payload = json.loads(records.write_production_record(job, export, paths).read_text(encoding="utf-8"))
    assert before <= datetime.fromisoformat(payload["createdAt"]) <= datetime.now(UTC)


@pytest.mark.parametrize("identifier", ["../export", "C:/private", "a/b", "a\\b"])
def test_record_path_rejects_traversal(tmp_path, identifier):
    with pytest.raises(ValueError):
        StoragePaths(tmp_path).production_record(identifier)
