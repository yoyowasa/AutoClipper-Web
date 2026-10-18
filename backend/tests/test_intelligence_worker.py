from contextlib import nullcontext
from datetime import timedelta
import logging
from pathlib import Path

import pytest
from rq import Worker
from rq.job import JobStatus
import yaml

from app.config import Settings
from app.intelligence import queue as intelligence_queue, worker as intelligence_worker
from app.intelligence.models import AnalysisRun, SyncRun
from app.jobs import queue as media_queue, worker as media_worker
from test_worker_failures import factory as factory, rq_job, queue_with, seed


@pytest.mark.parametrize("custom", [False, True])
def test_sync_and_analysis_use_only_intelligence_queue_and_media_routes_stay_separate(monkeypatch, custom):
    config = Settings(_env_file=None, rq_queue_name="media-custom" if custom else "autoclipper",
                      rq_intelligence_queue_name="analytics-custom" if custom else "autoclipper-intelligence")
    calls = []
    connection = object()

    class CaptureQueue:
        def __init__(self, name, *, connection):
            self.name = name
            assert connection is not None

        def fetch_job(self, id):
            return None

        def get_job_ids(self):
            return []

        def enqueue(self, function, *args, **kwargs):
            calls.append((self.name, function.__name__, args, kwargs))

    for module in (intelligence_queue, media_queue):
        monkeypatch.setattr(module, "get_settings", lambda: config)
        monkeypatch.setattr(module, "Queue", CaptureQueue)
    monkeypatch.setattr(media_queue, "get_redis_connection", lambda: connection)
    monkeypatch.setattr(media_queue, "job_media_timeout", lambda *args, **kwargs: 3600)
    intelligence_queue.enqueue_youtube_sync("sync_test")
    intelligence_queue.enqueue_channel_analysis("analysis_test")
    media_queue.enqueue_autoclipper_job("job_test")
    media_queue.enqueue_subtitle_review_preview("job_test", "clip_test", "hash")
    media_queue.enqueue_thumbnail_copy("export_test", "request_test")
    media_queue.enqueue_subtitle_review_render("job_test", 1)
    media_queue.enqueue_title_hook_suggestions("job_test", "clip_test", "hash")
    assert [entry[0] for entry in calls] == [config.rq_intelligence_queue_name] * 2 + [config.rq_queue_name] * 5
    assert [entry[1] for entry in calls] == ["run_youtube_sync", "run_channel_analysis", "run_autoclipper_job",
        "run_subtitle_review_preview", "run_thumbnail_copy_generation", "run_subtitle_review_render",
        "run_title_hook_suggestion_generation"]
    assert calls[0][3]["job_timeout"] == 150 and calls[1][3]["job_timeout"] == 1140


@pytest.mark.parametrize("name", ["", " ", "autoclipper"])
def test_configuration_rejects_missing_or_shared_queue(name):
    with pytest.raises(ValueError):
        Settings(_env_file=None, rq_intelligence_queue_name=name)


def test_worker_entrypoints_listen_to_one_queue_each_and_only_media_checks_gpu(monkeypatch):
    config = Settings(_env_file=None, rq_queue_name="media-custom", rq_intelligence_queue_name="analytics-custom",
                      autoclipper_runtime_profile="gpu")
    calls = []

    class CaptureWorker:
        def __init__(self, queues, **kwargs):
            calls.append(queues)

        def work(self):
            pass

    for module, cls in ((media_worker, "CharacterAssetWorker"), (intelligence_worker, "IntelligenceWorker")):
        monkeypatch.setattr(module, "get_settings", lambda: config)
        monkeypatch.setattr(module, "get_redis_connection", lambda: object())
        monkeypatch.setattr(module, cls, CaptureWorker)
    preflights = []
    monkeypatch.setattr(media_worker.subprocess, "run", lambda *args, **kwargs: preflights.append(args))
    intelligence_worker.main()
    assert preflights == []
    media_worker.main()
    assert len(preflights) == 1
    assert calls == [["analytics-custom"], ["media-custom"]]


def test_application_maintenance_has_a_single_owner_per_domain(monkeypatch):
    calls = []
    monkeypatch.setattr(Worker, "run_maintenance_tasks", lambda self: calls.append(("rq", self.queues)))
    monkeypatch.setattr(media_worker, "SessionLocal", lambda: nullcontext("db"))
    monkeypatch.setattr(intelligence_worker, "SessionLocal", lambda: nullcontext("db"))
    monkeypatch.setattr(media_worker, "reconcile_orphaned_jobs", lambda db, queues: calls.append(("media", queues)))
    monkeypatch.setattr(media_worker, "get_storage_paths", lambda: "media-paths")
    monkeypatch.setattr(media_worker, "maintain_discarded_review_previews", lambda paths: calls.append(("previews", paths)))
    monkeypatch.setattr(intelligence_worker, "get_settings", lambda: "config")
    monkeypatch.setattr(intelligence_worker, "get_storage_paths", lambda: "paths")
    monkeypatch.setattr(intelligence_worker, "maintain_youtube", lambda db, cfg, paths, queues: calls.append(("youtube", queues)))
    media = object.__new__(media_worker.CharacterAssetWorker)
    intelligence = object.__new__(intelligence_worker.IntelligenceWorker)
    media.queues, intelligence.queues = ["media"], ["intelligence"]
    media.run_maintenance_tasks()
    intelligence.run_maintenance_tasks()
    assert calls == [("rq", ["media"]), ("media", ["media"]), ("previews", "media-paths"),
                     ("rq", ["intelligence"]), ("youtube", ["intelligence"])]


@pytest.mark.parametrize("kind", ["sync", "analysis"])
@pytest.mark.parametrize("message", ["JobTimeoutException", "Work-horse terminated unexpectedly (signal 9)", "ValueError"])
def test_intelligence_worker_inherits_failure_recording_and_leaves_media_job_unchanged(factory, monkeypatch, kind, message):
    from app.intelligence.models import Channel
    from app.intelligence.common import now
    from app.models import Job

    seed(factory, state="completed")
    stamp = now()
    with factory() as db:
        db.add(Channel(id=1, external_id="UC" + "a" * 22))
        db.flush()
        model = SyncRun if kind == "sync" else AnalysisRun
        values = {"expires_at": stamp + timedelta(days=30)} if kind == "analysis" else {}
        db.add(model(id=kind + "_test", channel_id=1, active_channel_id=1, status="running", **values))
        db.commit()
    monkeypatch.setattr(Worker, "handle_job_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(media_worker, "SessionLocal", factory)
    worker = object.__new__(intelligence_worker.IntelligenceWorker)
    worker.log = logging.getLogger("test_intelligence_worker")
    worker.name = "intelligence-test"
    function = "app.intelligence.sync.run_youtube_sync" if kind == "sync" else "app.intelligence.analysis_runner.run_channel_analysis"
    task = rq_job(function=function, identifier=kind + "_test", status=JobStatus.FAILED)
    worker.handle_job_failure(task, queue_with(), exc_string=message)
    with factory() as db:
        run = db.get(model, kind + "_test")
        assert run.status == "failed" and run.error_code == "WORKER_INTERRUPTED" and run.active_channel_id is None
        assert db.get(Job, "job_test").status == "completed"


def test_compose_intelligence_worker_has_cpu_image_storage_and_no_gpu_override():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    gpu = yaml.safe_load((root / "docker-compose.gpu.yml").read_text(encoding="utf-8"))
    service = compose["services"]["intelligence-worker"]
    assert service["build"]["dockerfile"] == "Dockerfile"
    assert service["command"] == ["python", "-m", "app.intelligence.worker"]
    assert service["environment"]["AUTOCLIPPER_RUNTIME_PROFILE"] == "cpu"
    assert service["volumes"] == compose["services"]["worker"]["volumes"]
    assert service["environment"] == compose["services"]["worker"]["environment"]
    assert "deploy" not in service and "devices" not in service
    assert "intelligence-worker" not in gpu["services"]
