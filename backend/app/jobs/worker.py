import subprocess
import sys
import logging

from rq import Worker
from rq.job import Job as RQJob, JobStatus

from app.jobs.worker_failures import mark_rq_failure, reconcile_orphaned_jobs

from app.config import get_settings
from app.jobs.queue import get_redis_connection
from app.db import SessionLocal


class CharacterAssetWorker(Worker):
    def handle_job_failure(self, job: RQJob, queue, started_job_registry=None, exc_string="") -> None:
        # RQ invokes this both in the child (ordinary exceptions/timeouts) and
        # in the surviving parent (SIGKILL/abnormal child exit). Failure
        # callbacks alone are not executed on the latter path in RQ 2.12.
        super().handle_job_failure(job, queue, started_job_registry, exc_string)
        try:
            # RQ may have scheduled a retry rather than a terminal failure.
            if job.get_status(refresh=True) in {JobStatus.FAILED, JobStatus.STOPPED}:
                with SessionLocal() as db:
                    mark_rq_failure(db, job, exc_string)
        except Exception:
            logging.getLogger(__name__).warning("Application job failure could not be recorded; maintenance will reconcile it")

    def run_maintenance_tasks(self) -> None:
        super().run_maintenance_tasks()
        try:
            with SessionLocal() as db:
                failed = reconcile_orphaned_jobs(db, self.queues)
                if failed:
                    logging.getLogger(__name__).warning("Marked orphaned application jobs failed: %s", ", ".join(failed))
        except Exception:
            logging.getLogger(__name__).warning("Orphan job reconciliation skipped: RQ or database state could not be checked")


def main() -> None:
    settings = get_settings()
    if settings.autoclipper_runtime_profile == "gpu":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.audio.gpu_preflight",
                "--device",
                "cuda",
                "--compute-type",
                "float16",
            ],
            check=True,
        )
    worker = CharacterAssetWorker([settings.rq_queue_name], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
