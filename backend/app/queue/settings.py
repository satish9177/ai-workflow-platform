from arq.connections import RedisSettings

from app.config import settings
from app.queue.jobs import execute_foreach_iteration_job, execute_parallel_branch_job, execute_workflow, resume_workflow
from app.llm.registry import register_configured_providers

async def startup(ctx):
    register_configured_providers(settings)


class WorkerSettings:
    functions = [execute_workflow, resume_workflow, execute_parallel_branch_job, execute_foreach_iteration_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    retry_jobs = True
    max_tries = 3
    on_startup = startup
