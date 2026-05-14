# Backend

The backend is a FastAPI application in `backend/app`. It is async-first: HTTP routes, SQLAlchemy sessions, workflow execution, and ARQ workers all use async patterns.

## Main Modules

- `main.py`: FastAPI app creation, middleware, router registration, APScheduler lifespan jobs.
- `config.py`: environment-backed settings and production validation.
- `database.py`: async SQLAlchemy engine/session factory and pool lifecycle logging.
- `models/`: SQLAlchemy models for users, workflows, runs, step results, step executions, branch executions, approvals, integrations, memory.
- `routers/`: API endpoints.
- `engine/`: orchestration executor, approval timeouts, step implementations.
- `tools/`: tool registry and integrations.
- `llm/`: provider abstraction and adapters.
- `queue/`: ARQ job functions and worker settings.

## Execution Entry Points

API routes enqueue work through Redis/ARQ. Workers call:

- `execute_run(run_id, db)`
- `resume_run(run_id, step_id, db)`
- `execute_parallel_branch(branch_execution_id, run_id, group_step_key, branch_index, db)`
- `execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db)`

The API does not execute long-running workflows inline.

## Database Models That Matter for Orchestration

- `Workflow`: persisted workflow JSON and trigger config.
- `Run`: run lifecycle, trigger data, context, status, error.
- `StepResult`: logical output/resume record per step key.
- `StepExecution`: timeline record with status, attempts, previews, parent hierarchy.
- `BranchExecution`: fan-out/fan-in record for `parallel_group` and `foreach`.
- `Approval`: human approval tokens, pending/resolved state, timeout metadata.

## Sessions and Pooling

`database.py` configures:

- `pool_pre_ping=True`
- `pool_recycle`
- configurable pool size, overflow, timeout
- asyncpg command/connect timeout
- PostgreSQL statement and idle-in-transaction timeouts

ARQ jobs use `_run_with_session` to ensure rollback/close behavior is logged without masking business exceptions.

## Scheduler Jobs

The FastAPI lifespan starts APScheduler jobs:

- cron trigger poll every minute
- approval timeout poll every 10 seconds

Scheduler jobs discover durable database state. They do not own correctness by themselves; if the process restarts, the next poll scans pending due work again.

## Logging

The backend uses `structlog`.

Important log families:

- `request.completed`
- `run.started`, `run.completed`, `run.failed`
- `step.started`, `step.completed`, `step.failed`
- `parallel_group.*`
- `foreach.*`
- `switch.*`
- `approval.timeout.*`
- `integration.resolve.*`
- `arq.*`
- `db.connection.*`

Never log credentials, API keys, tokens, webhook URLs, or full request bodies.

## Local Commands

Install:

```bash
cd backend
pip install -e ".[dev]"
```

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run worker:

```bash
arq app.queue.settings.WorkerSettings
```

Run migrations:

```bash
alembic upgrade head
```

Run tests:

```bash
pytest tests/ -v --cov=app
```

## Configuration

Settings are loaded from `.env`. See `backend/.env.example`.

Production must set:

- non-default `SECRET_KEY`
- `ENCRYPTION_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_BASE_URL`
- appropriate `CORS_ORIGINS`

Pool and ARQ settings should be reviewed together. `DB_POOL_SIZE` should have headroom above `ARQ_MAX_JOBS`.
