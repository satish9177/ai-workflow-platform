# Backend

The backend is a FastAPI application in `backend/app`.

## Main Modules

- `main.py`: app creation, middleware, router registration, scheduler lifespan
- `config.py`: environment-backed settings
- `database.py`: async SQLAlchemy engine and session dependency
- `models/`: SQLAlchemy 2.0 async-compatible models
- `routers/`: API endpoints
- `engine/`: workflow execution logic
- `tools/`: tool implementations and registry
- `queue/`: ARQ job functions and worker settings

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

## Logging

The backend uses `structlog`. Request logs include method, path, status code, duration, and `request_id`. Responses include `X-Request-ID`.

## Configuration

Settings are loaded from `.env`. See `backend/.env.example`.

Production requires a non-default `SECRET_KEY` and configured `ENCRYPTION_KEY`.
