# AI Workflow Platform

An internal AI workflow automation MVP for building, running, and monitoring workflows that combine LLM prompts, tool calls, human approvals, cron triggers, and webhooks.

The project is intentionally simple: one FastAPI backend, one React frontend, PostgreSQL for durable state, Redis/ARQ for background execution, and Docker Compose for local and production-style deployment.

## Architecture Summary

- **Frontend**: Vite + React dashboard for runs, workflows, approvals, and login.
- **Backend API**: FastAPI routes for auth, workflows, runs, approvals, integrations, and webhooks.
- **Database**: PostgreSQL stores users, workflows, runs, step results, approvals, integrations, and conversation memory.
- **Worker**: ARQ executes and resumes workflow runs from Redis jobs.
- **Scheduler**: APScheduler polls active cron workflows once per minute and enqueues due runs.
- **Engine**: deterministic executor processes workflow steps, persists step results, pauses for approvals, and resumes from completed steps.
- **Ingress**: Nginx production config proxies `/api/` and `/webhooks/` to the API.

## Tech Stack

- Backend: FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic Settings
- Queue: Redis, ARQ
- Scheduler: APScheduler, croniter
- Auth: JWT via python-jose, passlib bcrypt
- Tools: HTTP, SMTP, WhatsApp, OpenAI LLM step
- Frontend: Vite, React 18, TypeScript, TailwindCSS, TanStack Query, React Router, Axios
- Deployment: Docker Compose, Nginx

## Local Development Setup

Prerequisites:

- Python 3.12
- Node.js + npm
- Docker Desktop
- PostgreSQL and Redis via Docker Compose, or local equivalents

Backend setup:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
```

Frontend setup:

```bash
cd frontend
npm install
copy .env.example .env
```

## Docker Setup

Start the local stack:

```bash
docker compose up
```

Run migrations against the Docker API service:

```bash
docker compose run --rm api alembic upgrade head
```

## Running Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Running Worker

```bash
cd backend
arq app.queue.settings.WorkerSettings
```

## Running Frontend

```bash
cd frontend
npm run dev
```

The dashboard defaults to `http://localhost:5173` and calls `VITE_API_URL` or `http://localhost:8000`.

## Running Tests

Backend:

```bash
cd backend
pytest tests/ -v --cov=app
```

Frontend build check:

```bash
cd frontend
npm run build
```

## Environment Variables

Backend variables are documented in `backend/.env.example`.

Key values:

- `DATABASE_URL`: async PostgreSQL URL
- `REDIS_URL`: Redis URL for ARQ
- `SECRET_KEY`: JWT signing secret
- `ENCRYPTION_KEY`: 32-byte hex key used for Fernet credential encryption
- `OPENAI_API_KEY`: optional in development, required for real LLM steps
- `CORS_ORIGINS`: comma-separated frontend origins
- `APP_BASE_URL`: base URL used for approval links

Frontend variables are documented in `frontend/.env.example`.

## Production Deployment Overview

Production-style deployment uses:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Services:

- `nginx`: public HTTP/HTTPS entrypoint
- `api`: FastAPI app
- `worker`: ARQ worker
- `db`: PostgreSQL
- `redis`: Redis with append-only persistence

Run migrations before serving traffic:

```bash
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

## Screenshots

Placeholder screenshots to add later:

- Runs dashboard
- Run detail page
- Workflow list
- Pending approvals

## Example Workflow JSON

```json
{
  "name": "HTTP check with approval",
  "description": "Fetch a URL, evaluate the result, then ask for human approval.",
  "trigger_type": "manual",
  "trigger_config": {},
  "steps": [
    {
      "id": "fetch_status",
      "type": "tool",
      "tool": "http_request",
      "action": "execute",
      "params": {
        "method": "GET",
        "url": "https://example.com"
      }
    },
    {
      "id": "is_success",
      "type": "condition",
      "condition": "fetch_status.data|length > 0",
      "if_true": "approve",
      "if_false": null
    },
    {
      "id": "approve",
      "type": "approval",
      "approver_email": "developer@example.com"
    }
  ]
}
```
