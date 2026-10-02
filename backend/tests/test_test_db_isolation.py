from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

import conftest as isolation
from app.config import get_settings
import app.db as db
from app.main import app


def test_settings_engine_and_sessions_use_session_storage(isolated_app_storage: Path) -> None:
    settings = get_settings()
    assert Path(settings.storage_root).resolve() == isolated_app_storage.resolve()
    assert settings.database_url == db.engine.url.render_as_string(hide_password=False)
    assert Path(db.engine.url.database).resolve() == isolated_app_storage / "autoclipper.db"
    with db.SessionLocal() as session:
        assert session.get_bind() is db.engine


@pytest.mark.parametrize("already_exists", [False, True])
def test_app_lifespan_leaves_runtime_database_untouched(tmp_path: Path, monkeypatch, already_exists: bool) -> None:
    runtime = tmp_path / "pretend-repository" / "storage"
    runtime.mkdir(parents=True)
    runtime_db = runtime / "autoclipper.db"
    if already_exists:
        runtime_db.write_bytes(b"existing runtime database must remain untouched")
    before = (runtime_db.stat().st_mtime_ns, runtime_db.read_bytes()) if already_exists else None
    monkeypatch.setattr(isolation, "RUNTIME_STORAGE_ROOT", runtime)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert "jobs" in inspect(db.engine).get_table_names()
    assert runtime_db.exists() == already_exists
    if already_exists:
        assert (runtime_db.stat().st_mtime_ns, runtime_db.read_bytes()) == before


@pytest.mark.parametrize("relative", ["autoclipper.db", "nested/another.db"])
def test_guard_blocks_runtime_connection_before_file_creation(tmp_path: Path, monkeypatch, relative: str) -> None:
    runtime = tmp_path / "pretend-repository" / "storage"
    monkeypatch.setattr(isolation, "RUNTIME_STORAGE_ROOT", runtime)
    database = runtime / relative
    database.parent.mkdir(parents=True)
    engine = create_engine("sqlite:///" + database.as_posix())
    try:
        with pytest.raises(pytest.fail.Exception, match="runtime storage"):
            with engine.connect():
                pass
        assert not database.exists()
    finally:
        engine.dispose()


def test_guard_blocks_lifespan_when_global_engine_is_redirected(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "pretend-repository" / "storage"
    runtime.mkdir(parents=True)
    monkeypatch.setattr(isolation, "RUNTIME_STORAGE_ROOT", runtime)
    runtime_db = runtime / "autoclipper.db"
    engine = create_engine("sqlite:///" + runtime_db.as_posix(), connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", engine)
    try:
        with pytest.raises(pytest.fail.Exception, match="runtime storage"):
            with TestClient(app):
                pass
        assert not runtime_db.exists()
    finally:
        engine.dispose()


def test_custom_test_engine_and_storage_remain_supported(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine("sqlite:///" + (tmp_path / "custom.db").as_posix())
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessions)
    try:
        isolation.assert_test_engine(engine)
        with sessions() as session:
            assert isinstance(session, Session)
            assert session.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()


def test_guard_blocks_already_pooled_runtime_connection(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "autoclipper.db"
    engine = create_engine("sqlite:///" + database.as_posix())
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
        before = (database.stat().st_mtime_ns, database.read_bytes())
        monkeypatch.setattr(isolation, "RUNTIME_STORAGE_ROOT", tmp_path)
        with pytest.raises(pytest.fail.Exception, match="runtime storage"):
            with engine.connect() as connection:
                connection.execute(text("CREATE TABLE must_not_exist (id INTEGER)"))
        assert (database.stat().st_mtime_ns, database.read_bytes()) == before
    finally:
        engine.dispose()


@pytest.mark.parametrize("uri", [False, True])
def test_guard_recognizes_relative_and_uri_runtime_paths(tmp_path: Path, monkeypatch, uri: bool) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(isolation, "RUNTIME_STORAGE_ROOT", tmp_path / "storage")
    database = "file:storage/autoclipper.db?mode=ro" if uri else "storage/autoclipper.db"
    with pytest.raises(pytest.fail.Exception, match="runtime storage"):
        isolation.assert_test_database(database)
