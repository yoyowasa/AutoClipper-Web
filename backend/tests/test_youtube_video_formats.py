from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.intelligence.ingest import ingest_video, save_report
from app.intelligence.models import SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.video_formats import content_format, repair_video_formats
from test_api_routes import client as client
from test_intelligence import environment as environment, VIDEO_ID
from test_channel_analysis import prepared as prepared, CLOCK


@pytest.mark.parametrize("value,expected", [("shorts", "shorts"), ("SHORTS", "shorts"),
    ("videoOnDemand", "long"), ("VIDEO_ON_DEMAND", "long"), (" Video-on-demand ", "long"),
    ("LIVE_STREAM", "live"), ("liveStream", "live"), ("live_stream", "live"),
    ("STORY", "unknown"), ("UNSPECIFIED", "unknown"), ("LIVE", "unknown"), (None, "unknown"), (0, "unknown")])
def test_content_format_variants(value, expected):
    assert content_format(value) == expected


@pytest.mark.parametrize("kind", ["video_format", "first7"])
@pytest.mark.parametrize("value,expected", [("shorts", "shorts"), ("videoOnDemand", "long"), ("liveStream", "live")])
def test_report_actual_values_set_format(prepared, kind, value, expected):
    run = prepared.db.scalar(select(SyncRun))
    save_report(prepared.db, run, prepared.config, kind, CLOCK.date(), CLOCK.date(),
        [{"video": VIDEO_ID, "creatorContentType": value, "views": 1}], CLOCK, VIDEO_ID)
    prepared.db.flush()
    video = prepared.db.get(YouTubeVideo, VIDEO_ID)
    assert (video.format, video.format_source) == (expected, "youtube_analytics")
    # Refreshing public metadata / a missing report must not erase the classification.
    ingest_video(prepared.db, 1, {"id": VIDEO_ID, "snippet": {"title": "test", "publishedAt": "2026-09-01T00:00:00Z"},
        "contentDetails": {"duration": "PT1M"}}, CLOCK)
    save_report(prepared.db, run, prepared.config, kind, CLOCK.date(), CLOCK.date(), [], CLOCK, VIDEO_ID)
    assert video.format == expected


@pytest.mark.parametrize("dimension_only", [False, True])
def test_repair_dry_run_execute_and_idempotent(prepared, dimension_only):
    video = prepared.db.get(YouTubeVideo, VIDEO_ID)
    video.format, video.format_source = "unknown", "unknown"
    for row in prepared.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind.in_(["video_format", "first7"]))):
        row.dimensions = {} if dimension_only else {"creatorContentType": "shorts"}
        row.dimension_key = f":{VIDEO_ID}:shorts"
    prepared.db.commit()
    report = repair_video_formats(prepared.db, clock=CLOCK)
    assert report["changed"] == 1 and report["after"]["shorts"] == 1
    prepared.db.expire_all()
    assert prepared.db.get(YouTubeVideo, VIDEO_ID).format == "unknown"
    repair_video_formats(prepared.db, execute=True, clock=CLOCK)
    prepared.db.expire_all()
    assert prepared.db.get(YouTubeVideo, VIDEO_ID).format == "shorts"
    assert repair_video_formats(prepared.db, execute=True, clock=CLOCK)["changed"] == 0


@pytest.mark.parametrize("problem", ["expired_metadata", "expired_reports", "conflicting"])
def test_repair_does_not_guess_ambiguous_or_expired(prepared, problem):
    video = prepared.db.get(YouTubeVideo, VIDEO_ID)
    video.format = "unknown"
    rows = prepared.db.scalars(select(VideoDailyStat).where(VideoDailyStat.kind.in_(["video_format", "first7"]))).all()
    if problem == "expired_metadata":
        video.metadata_updated_at = CLOCK - timedelta(days=30)
    elif problem == "expired_reports":
        for row in rows:
            row.expires_at = CLOCK
    else:
        rows[0].dimensions = {"creatorContentType": "videoOnDemand"}
    prepared.db.commit()
    assert repair_video_formats(prepared.db, execute=True, clock=CLOCK)["changed"] == 0


def test_new_diagnostics_table_created_for_existing_database(tmp_path, monkeypatch):
    import app.db as db_module
    from app.db import Base, _create_engine
    engine = _create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    tables = [table for name, table in Base.metadata.tables.items() if name != "channel_analysis_validation"]
    Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "settings", SimpleNamespace(storage_root=str(tmp_path / "storage")))
    db_module.init_db()
    from sqlalchemy import inspect
    assert "channel_analysis_validation" in inspect(engine).get_table_names()
    engine.dispose()


def test_cli_defaults_to_dry_run_and_execute_is_explicit(prepared, monkeypatch, capsys):
    import app.maintenance as maintenance
    video = prepared.db.get(YouTubeVideo, VIDEO_ID)
    video.format, video.format_source = "unknown", "unknown"
    prepared.db.commit()
    monkeypatch.setattr(maintenance, "SessionLocal", prepared.factory)
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(storage_root=str(prepared.paths.root)))
    import app.intelligence.video_formats as formats
    monkeypatch.setattr(formats, "now", lambda: CLOCK)
    assert maintenance.main(["repair-youtube-video-formats"]) == 0
    prepared.db.expire_all()
    assert prepared.db.get(YouTubeVideo, VIDEO_ID).format == "unknown"
    assert '"dry_run": true' in capsys.readouterr().out
    assert maintenance.main(["repair-youtube-video-formats", "--execute"]) == 0
    prepared.db.expire_all()
    assert prepared.db.get(YouTubeVideo, VIDEO_ID).format == "shorts"


def test_repair_ignores_null_report_placeholders(prepared):
    video = prepared.db.get(YouTubeVideo, VIDEO_ID)
    video.format = "unknown"
    row = prepared.db.scalar(select(VideoDailyStat).where(VideoDailyStat.kind == "first7"))
    row.dimensions, row.dimension_key = {}, f":{VIDEO_ID}:"
    prepared.db.commit()
    assert repair_video_formats(prepared.db, execute=True, clock=CLOCK)["changed"] == 1
