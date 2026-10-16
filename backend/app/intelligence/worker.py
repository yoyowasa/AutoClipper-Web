"""CPU worker for YouTube sync/analysis; never consumes the media queue."""

import logging

from rq import Worker

from app.config import get_settings
from app.db import SessionLocal
from app.intelligence.maintenance import maintain_youtube
from app.jobs.queue import get_redis_connection
from app.jobs.worker import CharacterAssetWorker
from app.storage.paths import get_storage_paths


class IntelligenceWorker(CharacterAssetWorker):
    # Inherit RQ failure recording, including the surviving-parent SIGKILL path.
    def run_maintenance_tasks(self) -> None:
        # RQ registry maintenance is per queue. Application maintenance is split:
        # media orphan checks belong to the media worker; YouTube expiry and
        # sync/analysis orphan checks belong only to this worker.
        Worker.run_maintenance_tasks(self)
        try:
            with SessionLocal() as db:
                maintain_youtube(db, get_settings(), get_storage_paths(), self.queues)
        except Exception:
            logging.getLogger(__name__).warning("YouTube maintenance could not be completed")


def main() -> None:
    settings = get_settings()
    worker = IntelligenceWorker([settings.rq_intelligence_queue_name], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
