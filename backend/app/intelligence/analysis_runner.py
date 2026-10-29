from datetime import timedelta
from uuid import uuid4

from rq.timeouts import JobTimeoutException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.intelligence.analysis_bridge import ANALYSIS_TIMEOUT_SECONDS, ChannelAnalysisGenerator, cleanup_analysis_files
from app.intelligence.analysis_errors import AnalysisError, MESSAGES
from app.intelligence.analysis_budget import compression_limitation
from app.intelligence.analysis_input import build_analysis_input
from app.intelligence.production_aggregation import save_production_aggregates
from app.intelligence.analysis_validation import ReviewValidationError, validate_review
from app.intelligence.common import now
from app.intelligence.models import AnalysisRun, AnalysisValidationDiagnostics, Channel, SyncRun
from app.intelligence.sync import mark_sync_failed, run_youtube_sync
from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionError
from app.storage.paths import get_storage_paths


def analysis_job_timeout(config) -> int:
    return ANALYSIS_TIMEOUT_SECONDS + config.youtube_sync_budget_seconds + 60


def needs_sync(mode: str, last_sync, stamp) -> bool:
    return mode == "always" or (mode == "auto" and (last_sync is None or stamp - last_sync >= timedelta(hours=24)))


def mark_analysis_failed(db: Session, id: str, code: str) -> None:
    db.execute(update(AnalysisRun).where(AnalysisRun.id == id, AnalysisRun.status.in_(["queued", "running"]))
               .values(status="failed", error_code=code, finished_at=now(), active_channel_id=None))
    db.commit()


def record_rq_analysis_failure(db: Session, job) -> None:
    if getattr(job, "func_name", None) == "app.intelligence.analysis_runner.run_channel_analysis" and job.args:
        mark_analysis_failed(db, str(job.args[0]), "WORKER_INTERRUPTED")


def run_channel_analysis(id: str, *, session_factory=SessionLocal, paths=None, config=None, generator_factory=ChannelAnalysisGenerator):
    storage, settings = paths or get_storage_paths(), config or get_settings()
    with session_factory() as db:
        claim = db.execute(update(AnalysisRun).where(AnalysisRun.id == id, AnalysisRun.status == "queued")
                           .values(status="running", started_at=now()))
        db.commit()
        if claim.rowcount != 1:
            return
        run = db.get(AnalysisRun, id)
        try:
            channel = db.get(Channel, run.channel_id)
            if needs_sync(run.sync_before, channel.last_sync_at, now()):
                sync = SyncRun(id="sync_" + uuid4().hex, channel_id=channel.id, active_channel_id=channel.id, queued_at=now())
                db.add(sync)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    raise AnalysisError("STATISTICS_BUSY") from None
                try:
                    run_youtube_sync(sync.id, session_factory=session_factory, paths=storage, config=settings)
                except Exception:
                    db.rollback()
                    mark_sync_failed(db, sync.id, "SYNC_FAILED")
                    raise AnalysisError("STATISTICS_FAILED") from None
            db.expire_all()
            run = db.get(AnalysisRun, id)
            context = build_analysis_input(db, storage, settings, run.channel_id, id, now())
            save_production_aggregates(db, run.channel_id, context.aggregates, now())
            run.sync_run_id = context.payload["batch"]["run_id"]
            run.input_snapshot, run.expires_at = context.payload, context.expires_at
            db.commit()

            def remember(request_id):
                run.request_id = request_id
                db.commit()

            generator = generator_factory(paths=storage, run_id=id, on_request=remember)
            result = generator.analyze(context)
            output = result.model_dump() if hasattr(result, "model_dump") else result
            diagnostics = {}
            validated = validate_review(output, context, diagnostics=diagnostics)
            db.expire_all()
            try:
                fresh = build_analysis_input(db, storage, settings, run.channel_id, id, now())
            except ValueError:
                raise AnalysisError("CODEX_STALE_EVIDENCE") from None
            if run.status != "running" or fresh.fingerprint != context.fingerprint or now() >= context.expires_at:
                raise AnalysisError("CODEX_STALE_EVIDENCE")
            # The saved result must disclose sampling/trimming even if Codex omits it.
            limitation = compression_limitation(context.payload)
            validated.limitations = ([limitation, *validated.limitations] if len(validated.limitations) < 10 else
                                     [limitation + "\n" + validated.limitations[0], *validated.limitations[1:]])
            diagnostics["inputCompression"] = {
                "scope": context.payload["input_scope"], "budget": context.payload["budget_omissions"],
                "deduplicatedReports": context.payload["deduplicated_reports"],
            }
            run.review = validated.model_dump(mode="json")
            run.validation = AnalysisValidationDiagnostics(report=diagnostics)
            run.status, run.finished_at, run.active_channel_id = "success", now(), None
            db.commit()
        except Exception as error:
            db.rollback()
            if isinstance(error, ReviewValidationError):
                db.get(AnalysisRun, id).validation = AnalysisValidationDiagnostics(report=error.report)
            if isinstance(error, AnalysisError):
                code = error.code
            elif isinstance(error, JobTimeoutException):
                code = "CODEX_TIMEOUT"
            elif isinstance(error, CodexTitleHookSuggestionError):
                code = ("CODEX_INVALID_OUTPUT" if error.code.endswith(("invalid", "mismatch")) else
                        "CODEX_TIMEOUT" if error.code.endswith("timeout") else
                        "CODEX_BRIDGE_UNAVAILABLE" if error.code.endswith("bridge_unavailable") else "CODEX_FAILED")
            elif isinstance(error, ValueError):
                code = str(error) if str(error) in MESSAGES else "CODEX_INVALID_OUTPUT"
            else:
                code = "CODEX_FAILED"
            mark_analysis_failed(db, id, code)
            raise AnalysisError(code) from None
        finally:
            request_id = db.get(AnalysisRun, id).request_id
            try:
                cleanup_analysis_files(storage, request_id)
            except OSError:
                pass  # The maintenance pass retries cleanup; never log raw content.
