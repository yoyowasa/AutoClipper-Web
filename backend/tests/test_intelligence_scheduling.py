"""Clock-driven scheduling uses the existing channel claims and intelligence queue."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.intelligence.analysis_runner import mark_analysis_failed
from app.intelligence.job_claims import ChannelClaimError, claim_channel_run
from app.intelligence.models import AnalysisRun, Channel, ChannelConnection, SyncRun
from app.intelligence.scheduling import schedule_due_channels, schedule_slots
from app.intelligence.sync import mark_sync_failed
from test_api_routes import client as client
from test_intelligence import CHANNEL_ID, environment as environment
from test_channel_analysis import prepared as prepared, execute

MONDAY = datetime(2026, 10, 26, 3)


def setup_schedule(env):
    env.db.add(Channel(id=1, external_id=CHANNEL_ID))
    env.db.add(ChannelConnection(channel_id=1, status="connected"))
    env.db.commit()
    env.config = env.config.model_copy(update={"youtube_automation_enabled": True})


def test_slots_week_boundary_and_custom_hour(environment):
    config = environment.config
    assert schedule_slots(MONDAY, config) == (MONDAY, MONDAY)
    assert schedule_slots(MONDAY - timedelta(seconds=1), config) == (
        MONDAY - timedelta(days=1), MONDAY - timedelta(days=7))
    changed = config.model_copy(update={"youtube_auto_sync_hour_utc": 6, "youtube_auto_analysis_weekday": 2})
    day, week = schedule_slots(MONDAY, changed)
    assert day.hour == week.hour == 6 and week.weekday() == 2


def test_daily_sync_weekly_analysis_once_and_next_slot_retry(environment):
    e = environment
    setup_schedule(e)
    calls = []
    def tick(stamp):
        return schedule_due_channels(e.db, e.config, stamp,
            enqueue_sync=lambda id: calls.append(("sync", id)), enqueue_analysis=lambda id: calls.append(("analysis", id)))
    first = tick(MONDAY)
    assert len(first) == 1 and calls[0][0] == "analysis"
    analysis = e.db.get(AnalysisRun, first[0])
    assert analysis.sync_before == "always"
    assert tick(MONDAY + timedelta(minutes=1)) == []
    analysis.status, analysis.active_channel_id = "success", None
    e.db.add(SyncRun(id="sync_nested", channel_id=1, status="success", queued_at=MONDAY, active_channel_id=None))
    e.db.commit()
    assert tick(MONDAY + timedelta(minutes=2)) == []
    second = tick(MONDAY + timedelta(days=1))
    assert len(second) == 1 and calls[-1][0] == "sync"
    mark_sync_failed(e.db, second[0], "QUOTA_EXCEEDED")
    assert tick(MONDAY + timedelta(days=1, minutes=1)) == []
    third = tick(MONDAY + timedelta(days=2))
    assert len(third) == 1 and calls[-1][0] == "sync"
    mark_sync_failed(e.db, third[0], "RECONNECT_REQUIRED")
    weekly = tick(MONDAY + timedelta(days=7))
    assert len(weekly) == 1 and calls[-1][0] == "analysis"
    e.db.add(SyncRun(id="sync_weekly_nested", channel_id=1, status="success", queued_at=MONDAY + timedelta(days=7)))
    e.db.commit()
    mark_analysis_failed(e.db, weekly[0], "CODEX_FAILED")
    assert tick(MONDAY + timedelta(days=7, minutes=1)) == []


def test_queue_failure_is_recorded_once_and_connection_or_switch_disables(environment):
    e = environment
    setup_schedule(e)
    def broken(id):
        raise RuntimeError("provider body must never be recorded")
    ids = schedule_due_channels(e.db, e.config, MONDAY, enqueue_analysis=broken)
    run = e.db.get(AnalysisRun, ids[0])
    assert run.status == "failed" and run.error_code == "QUEUE_FAILED" and run.active_channel_id is None
    e.db.get(ChannelConnection, 1).status = "reconnect_required"
    e.db.commit()
    assert schedule_due_channels(e.db, e.config, MONDAY + timedelta(days=7), enqueue_analysis=broken) == []
    e.db.get(ChannelConnection, 1).status = "connected"
    e.db.commit()
    assert schedule_due_channels(e.db, e.config.model_copy(update={"youtube_automation_enabled": False}), MONDAY) == []


def test_manual_work_and_scheduled_work_share_claims(environment):
    e = environment
    setup_schedule(e)
    manual = claim_channel_run(e.db, 1, "sync", MONDAY)
    assert schedule_due_channels(e.db, e.config, MONDAY) == []
    with pytest.raises(ChannelClaimError, match="CHANNEL_BUSY"):
        claim_channel_run(e.db, 1, "analysis", MONDAY)
    assert e.db.get(SyncRun, manual.id).status == "queued"


def test_idle_worker_checks_clock_at_maintenance_interval():
    from app.intelligence.worker import IntelligenceWorker
    worker = object.__new__(IntelligenceWorker)
    worker.worker_ttl, worker.maintenance_interval = 420, 60
    assert worker.dequeue_timeout == 60


def test_maintenance_owns_automatic_scheduling(environment, monkeypatch):
    from app.intelligence.maintenance import maintain_youtube
    import app.intelligence.scheduling as scheduling
    e = environment
    setup_schedule(e)
    calls = []
    monkeypatch.setattr(scheduling, "enqueue_channel_analysis", calls.append)
    maintain_youtube(e.db, e.config, e.paths, [], clock=MONDAY)
    maintain_youtube(e.db, e.config, e.paths, [], clock=MONDAY + timedelta(minutes=1))
    assert len(calls) == 1 and e.db.get(AnalysisRun, calls[0]).status == "queued"


def test_two_scheduler_processes_cannot_claim_one_slot(environment, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'schedule.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    calls = []
    with factory() as db:
        db.add(Channel(id=1, external_id=CHANNEL_ID))
        db.add(ChannelConnection(channel_id=1, status="connected"))
        db.commit()
    config = environment.config.model_copy(update={"youtube_automation_enabled": True})
    def tick(_):
        with factory() as db:
            return schedule_due_channels(db, config, MONDAY, enqueue_analysis=calls.append)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(tick, range(2)))
        with factory() as db:
            assert len(list(db.scalars(select(AnalysisRun)))) == 1
        assert len(calls) == 1 and sum(len(result) for result in results) == 1
    finally:
        engine.dispose()


def test_scheduled_analysis_runs_existing_sync_then_codex_and_saves_failure(prepared, monkeypatch):
    import httpx
    import app.intelligence.analysis_runner as runner
    from app.intelligence.sync import run_youtube_sync
    from app.intelligence.youtube_client import YouTubeClient
    from test_channel_analysis import CLOCK
    from test_intelligence import transport
    e = prepared
    e.config = e.config.model_copy(update={"youtube_automation_enabled": True})
    calls = []
    ids = schedule_due_channels(e.db, e.config, CLOCK, enqueue_analysis=calls.append)
    assert ids == calls and len(ids) == 1
    monkeypatch.setattr(runner, "run_youtube_sync", lambda id, **kw: run_youtube_sync(
        id, **kw, client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport))))
    result = execute(e, ids[0])
    assert result.status == "success" and result.review["goals"]["window_days"] == 30
    assert len(list(e.db.scalars(select(SyncRun)))) == 2
    assert schedule_due_channels(e.db, e.config, CLOCK, enqueue_analysis=calls.append) == []
    # The same pipeline preserves the provider's safe error and never changes transport.
    future = CLOCK + timedelta(days=7)
    next_ids = schedule_due_channels(e.db, e.config, future, enqueue_analysis=calls.append)
    monkeypatch.setattr(runner, "now", lambda: future)
    monkeypatch.setattr(runner, "run_youtube_sync", lambda id, **kw: run_youtube_sync(id, **kw,
        client=YouTubeClient("synthetic", transport=httpx.MockTransport(lambda req: httpx.Response(403,
            json={"error": {"errors": [{"reason": "quotaExceeded"}]}})))))
    from app.intelligence.analysis_errors import AnalysisError
    with pytest.raises(AnalysisError):
        execute(e, next_ids[0])
    assert e.db.get(AnalysisRun, next_ids[0]).status == "failed"
    assert e.db.get(AnalysisRun, next_ids[0]).error_code == "STATISTICS_FAILED"
    failed_sync = e.db.scalar(select(SyncRun).where(SyncRun.status == "failed"))
    assert failed_sync.error_code == "QUOTA_EXCEEDED"
    assert len(schedule_due_channels(e.db, e.config, future + timedelta(days=7), enqueue_analysis=calls.append)) == 1


def test_sync_saves_evaluations_and_local_failure_keeps_downloaded_statistics(client, environment, monkeypatch):
    import httpx
    import app.intelligence.production_aggregation as aggregation
    from app.intelligence.models import ProductionAggregate, VideoDailyStat
    from app.intelligence.sync import run_youtube_sync
    from app.intelligence.youtube_client import YouTubeClient
    from test_intelligence import enqueue, transport
    e = environment
    id = enqueue(client, e)
    def execute_sync(id):
        run_youtube_sync(id, session_factory=e.factory, paths=e.paths, config=e.config,
            client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)))
        e.db.expire_all()
    execute_sync(id)
    saved = e.db.get(ProductionAggregate, 1).payload
    assert saved["choice_evaluations"]["window_days"] == 30
    assert saved["choice_evaluations"]["groups"] == []
    def failed(*args, **kwargs):
        raise ValueError("must not log provider output")
    monkeypatch.setattr(aggregation, "build_production_aggregates", failed)
    response = client.post("/api/intelligence/channels/1/sync")
    assert response.status_code == 202
    execute_sync(response.json()["id"])
    run = e.db.get(SyncRun, response.json()["id"])
    assert run.status == "partial" and run.error_code == "EVALUATION_FAILED"
    assert {"kind": "choice_evaluation", "reason": "EVALUATION_FAILED"} in run.missing_reports
    assert e.db.scalar(select(VideoDailyStat.id)) is not None
    assert e.db.get(ProductionAggregate, 1).payload == saved
