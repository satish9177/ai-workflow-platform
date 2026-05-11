# Deployment

Production-style deployment uses `docker-compose.prod.yml`.

## Start Production Stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Services:

- `nginx`: public reverse proxy
- `api`: FastAPI application
- `worker`: ARQ worker
- `db`: PostgreSQL 16
- `redis`: Redis 7 with append-only persistence

## Nginx

`nginx/default.conf` proxies:

- `/api/` to `api:8000`
- `/webhooks/` to `api:8000`

Other paths serve the frontend SPA from `/app/frontend/dist`.

## Environment Variables

The production compose file reads `backend/.env`.

Important production values:

- `ENVIRONMENT=production`
- `DATABASE_URL=postgresql+asyncpg://...`
- `REDIS_URL=redis://redis:6379/0`
- `SECRET_KEY`: strong random value
- `ENCRYPTION_KEY`: 32-byte hex value
- `POSTGRES_PASSWORD`: set in shell or deployment environment
- `APP_BASE_URL`: public API/base URL for approval links
- `CORS_ORIGINS`: allowed frontend origins

## Migrations

Run migrations before serving traffic:

```bash
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

## Startup Flow

1. PostgreSQL and Redis start.
2. Migrations are applied.
3. API starts and begins cron polling during lifespan startup.
4. Worker starts and listens for ARQ jobs.
5. Nginx proxies public API and webhook traffic.

## Backup

The Makefile includes:

```bash
make backup
```

This writes `backup.sql` using `pg_dump`.
