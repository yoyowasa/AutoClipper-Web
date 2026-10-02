"""Configure test storage before collection and reject runtime database access."""

from collections.abc import Iterator
from pathlib import Path
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import event
from sqlalchemy.dialects.sqlite.base import SQLiteDialect
from sqlalchemy.engine import Engine


RUNTIME_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"
SESSION_STORAGE = pytest.StashKey[Path]()


def assert_test_database(database: str | None) -> None:
    if not database or database == ":memory:":
        return
    if database.startswith("file:"):
        database = unquote(urlsplit(database).path)
    path = Path(database).resolve()
    if path.is_relative_to(RUNTIME_STORAGE_ROOT.resolve()):
        pytest.fail("Test database points into repository runtime storage", pytrace=False)


def assert_test_engine(engine: Engine) -> None:
    if engine.url.get_backend_name() == "sqlite":
        assert_test_database(engine.url.database)


def _guard_connect(dialect: Any, connection_record: Any, args: list[Any], kwargs: dict[str, Any]) -> None:
    # Check before sqlite3.connect can create a file, including engines made inside a test.
    if args:
        assert_test_database(str(args[0]))


def _guard_statement(connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
    # Also guard pooled connections which were opened before a test changed its engine.
    assert_test_engine(connection.engine)


def pytest_sessionstart(session: pytest.Session) -> None:
    if "app.db" in sys.modules or "app.main" in sys.modules:
        raise pytest.UsageError("Application imported before test database isolation")
    storage = session.config._tmp_path_factory.mktemp("app-session")
    session.config.stash[SESSION_STORAGE] = storage
    environment = pytest.MonkeyPatch()
    environment.setenv("DATABASE_URL", "sqlite:///" + (storage / "autoclipper.db").as_posix())
    environment.setenv("STORAGE_ROOT", str(storage))
    session.config.add_cleanup(environment.undo)

    from app.config import get_settings

    get_settings.cache_clear()
    session.config.add_cleanup(get_settings.cache_clear)
    event.listen(SQLiteDialect, "do_connect", _guard_connect)
    event.listen(Engine, "before_cursor_execute", _guard_statement)
    session.config.add_cleanup(lambda: event.remove(SQLiteDialect, "do_connect", _guard_connect))
    session.config.add_cleanup(lambda: event.remove(Engine, "before_cursor_execute", _guard_statement))


@pytest.fixture(scope="session")
def isolated_app_storage(pytestconfig: pytest.Config) -> Path:
    return pytestconfig.stash[SESSION_STORAGE]


@pytest.fixture(autouse=True)
def protect_runtime_database() -> Iterator[None]:
    import app.db as db

    assert_test_engine(db.engine)
    assert_test_engine(db.SessionLocal.kw["bind"])
    yield
