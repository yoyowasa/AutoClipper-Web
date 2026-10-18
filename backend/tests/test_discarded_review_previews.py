import json
from pathlib import Path

import pytest

from app.jobs.clip_plan import load_clip_plan
from app.jobs.subtitle_review import subtitle_review_preview_path
from app.models import Job
from app.storage.discarded_review_previews import (
    cleanup_discarded_preview_files, discarded_preview_cleanup_path, maintain_discarded_review_previews,
    pending_discarded_previews,
)
from test_api_routes import client as client
from test_return_to_clip_plan import approved


def previews(data):
    flat = subtitle_review_preview_path(data.output, "normal0")
    flat.parent.mkdir(exist_ok=True)
    flat.write_bytes(b"clip plan preview")
    old = flat.with_suffix("") / "live" / "old.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old review preview")
    return flat, old


def test_return_never_renames_preview_directories(client, monkeypatch):
    data = approved(client)
    flat, old = previews(data)
    original = Path.replace
    renamed = []

    def replace(path, target):
        assert not path.is_dir(), "Windows refuses renaming directories with open MP4s"
        renamed.append(path)
        return original(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    assert client.post(data.endpoint).status_code == 200
    assert renamed and all(path.suffix == ".json" for path in renamed)
    assert flat.exists() and not old.exists()


def test_locked_preview_does_not_block_return_and_maintenance_preserves_new_generation(client, monkeypatch, caplog):
    data = approved(client)
    flat, old = previews(data)
    original = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == old:
            raise PermissionError("do not expose exception details")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", unlink)
        response = client.post(data.endpoint)
        assert response.status_code == 200, response.text
        assert old.exists() and flat.exists()
        assert pending_discarded_previews(data.output) == [old.relative_to(data.output).as_posix()]
        maintain_discarded_review_previews(data.paths)
        assert old.exists()
    assert [record.getMessage() for record in caplog.records if record.name.endswith("discarded_review_previews")] == [str(old)] * 2
    with data.factory() as db:
        assert db.get(Job, data.id).status == "awaiting_clip_review"
    returned = load_clip_plan(data.output / "clip_plan.json")
    assert returned.subtitle_review_generation
    assert client.post(f"/api/jobs/{data.id}/clip-plan/approve").status_code == 200
    new = old.with_name("new-generation.mp4")
    new.write_bytes(b"keep new generation")
    maintain_discarded_review_previews(data.paths)
    assert not old.exists() and not discarded_preview_cleanup_path(data.output).exists()
    assert new.read_bytes() == b"keep new generation" and flat.exists()


@pytest.mark.parametrize("has_pending", [False, True])
def test_failed_commit_restores_manifest_json_and_leaves_previews(client, monkeypatch, has_pending):
    from sqlalchemy.orm import Session

    data = approved(client)
    flat, old = previews(data)
    manifest = discarded_preview_cleanup_path(data.output)
    payload = b'["subtitle_review_previews/past/old.mp4"]\n'
    if has_pending:
        manifest.write_bytes(payload)
    before = (data.output / "subtitle_review.json").read_bytes()
    monkeypatch.setattr(Session, "commit", lambda *args: (_ for _ in ()).throw(RuntimeError("private detail")))
    response = client.post(data.endpoint)
    assert response.status_code == 409 and "private detail" not in response.text
    assert (data.output / "subtitle_review.json").read_bytes() == before
    assert flat.exists() and old.exists()
    assert manifest.read_bytes() == payload if has_pending else not manifest.exists()


@pytest.mark.parametrize("relative", ["../outside.mp4", "subtitle_review_previews/../../outside.mp4", "/outside.mp4",
    "subtitle_review_previews/clip-plan.mp4"])
def test_maintenance_refuses_manifest_paths_outside_review_previews(tmp_path, relative):
    output = tmp_path / "job"
    output.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")
    discarded_preview_cleanup_path(output).write_text(json.dumps([relative]), encoding="utf-8")
    with pytest.raises(ValueError):
        cleanup_discarded_preview_files(output)
    assert outside.read_bytes() == b"keep"


def test_unreadable_review_returns_japanese_conflict_without_exception_details(client):
    data = approved(client)
    (data.output / "subtitle_review.json").write_text('{"private-input":', encoding="utf-8")
    response = client.post(data.endpoint)
    assert response.status_code == 409
    assert "保存データを読み込めません" in response.json()["detail"]
    assert "private-input" not in response.text


def test_post_commit_cleanup_exception_does_not_undo_success(client, monkeypatch):
    from app.jobs import return_to_clip_plan as operation

    data = approved(client)
    flat, old = previews(data)
    monkeypatch.setattr(operation, "cleanup_discarded_preview_files",
        lambda *args: (_ for _ in ()).throw(RuntimeError("private detail")))
    response = client.post(data.endpoint)
    assert response.status_code == 200 and "private detail" not in response.text
    assert old.exists()
    maintain_discarded_review_previews(data.paths)
    assert not old.exists() and flat.exists()
