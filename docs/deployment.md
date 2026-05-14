# Deployment

Production-style deployment uses Docker Compose. This is still a single-service backend architecture: API and worker share the same codebase and database.

## Services

- `nginx`: public reverse proxy.
- `api`: FastAPI application.
- `worker`: ARQ worker.
- `db`: PostgreSQL 16.
- `redis`: Redis 7 with append-only persistence.

## Start Production Stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Run migrations before serving traffic:

```bash
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

## Startup Flow

1. PostgreSQL starts.
2. Redis starts.
3. Migrations apply.
4. API starts, registers routers, configures LLM providers, starts APScheduler jobs.
5. Worker starts and registers ARQ functions.
6. Nginx proxies API and webhook traffic.

## Scheduler Behavior

APScheduler runs inside the API process:

- cron workflow polling every minute
- approval timeout polling every 10 seconds

Scheduler behavior is database-driven. A restart does not lose cron workflow definitions or pending approval timeout intent.

## Worker Behavior

ARQ workers execute:

- workflow runs
- approval resumes
- parallel branches
- foreach iterations

Workers should be deployed with enough database pool capacity. Keep `DB_POOL_SIZE` above `ARQ_MAX_JOBS` with headroom.

## Environment Variables

The production compose file reads `backend/.env`.

Important values:

- `ENVIRONMENT=production`
- `DATABASE_URL=postgresql+asyncpg://...`
- `REDIS_URL=redis://redis:6379/0`
- `SECRET_KEY`: strong random value.
- `ENCRYPTION_KEY`: configured credential encryption key.
- `POSTGRES_PASSWORD`: set in shell or deployment environment.
- `APP_BASE_URL`: public base URL for approval links.
- `CORS_ORIGINS`: allowed frontend origins.
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`: database pool sizing.
- `ARQ_MAX_JOBS`: worker concurrency.

## Nginx

`nginx/default.conf` proxies:

- `/api/` to `api:8000`
- `/webhooks/` to `api:8000`

Other routes serve the frontend SPA.

## Migrations

Alembic migrations are required for fresh databases and upgrades. Do not rely on SQLAlchemy `create_all` outside tests.

Check current head:

```bash
docker compose run --rm api alembic heads
```

Apply:

```bash
docker compose run --rm api alembic upgrade head
```

## Backups

The Makefile includes:

```bash
make backup
```

This writes `backup.sql` using `pg_dump`.

## Operational Notes

- Redis is queueing infrastructure, not correctness storage.
- PostgreSQL is the durable source of truth.
- Approval timeout and cron polling are eventually processed by scheduler ticks.
- If workers are down, runs remain pending/running/paused in PostgreSQL and can be inspected through timeline endpoints.
