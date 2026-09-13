from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, _create_engine
from app.models import Job


def test_sqlite_engine_enforces_foreign_keys(tmp_path: Path) -> None:
    engine = _create_engine(f"sqlite:///{tmp_path / 'foreign-keys.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            session.add(
                Job(
                    id="job_missing_video",
                    video_id="vid_missing",
                    status="queued",
                    progress=5,
                    current_step="Queued",
                    settings_json={},
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        engine.dispose()
