from arq.connections import RedisSettings

from app.config import settings
from app.queue.jobs import execute_workflow, resume_workflow


class WorkerSettings:
    functions = [execute_workflow, resume_workflow]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    retry_jobs = True
    max_tries = 3
