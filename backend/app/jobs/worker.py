from rq import Worker

from app.config import get_settings
from app.jobs.queue import get_redis_connection


def main() -> None:
    settings = get_settings()
    worker = Worker([settings.rq_queue_name], connection=get_redis_connection())
    worker.work()


if __name__ == "__main__":
    main()
