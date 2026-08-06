import subprocess
import sys

from rq import Worker

from app.config import get_settings
from app.jobs.queue import get_redis_connection


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
    worker = Worker([settings.rq_queue_name], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
