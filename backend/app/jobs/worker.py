import subprocess
import sys
import logging

from rq import Worker

from app.config import get_settings
from app.jobs.queue import get_redis_connection
from app.db import SessionLocal
from app.models import utc_now
from app.storage.character_asset_cleanup import expire_candidates
from app.storage.locking import storage_mutation_lock
from app.storage.paths import get_storage_paths


class CharacterAssetWorker(Worker):
    def run_maintenance_tasks(self) -> None:
        super().run_maintenance_tasks()
        # RQ maintenance also runs while idle; upload-time cleanup is optional.
        try:
            paths = get_storage_paths()
            with storage_mutation_lock(paths.root), SessionLocal() as db:
                expire_candidates(db, paths, utc_now())
        except Exception:
            logging.getLogger(__name__).warning("Expired character asset candidates could not be cleaned up")


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
