# AI Workflow Automation Platform

An internal AI workflow orchestration platform for building, running, and debugging workflows that combine LLM prompts, tool calls, human approvals, cron triggers, webhooks, integrations, and V2 orchestration containers.

The architecture is intentionally pragmatic: one FastAPI backend, one React frontend, PostgreSQL for durable orchestration state, Redis/ARQ for background jobs, APScheduler for lightweight polling, and Docker Compose for local and production-style deployment.

## Architecture Summary

- **Execution model**: linear-with-groups, not a general DAG runtime.
- **Backend API**: FastAPI routes for auth, workflows, runs, approvals, integrations, LLM providers, and webhooks.
- **Workflow engine**: deterministic executor with `parallel_group`, `foreach`, `switch`, approvals, retries, and resumable execution.
- **Database**: PostgreSQL stores workflows, runs, step results, step executions, branch executions, approvals, integrations, and memory.
- **Worker**: ARQ executes runs, resumes approvals, and processes parallel/foreach child jobs.
- **Scheduler**: APScheduler polls cron workflows and pending approval timeouts.
- **Frontend**: React dashboard for runs, timelines, workflows, approvals, integrations, providers, and templates.

## Tech Stack

- Backend: FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic Settings
- Queue: Redis, ARQ
- Scheduler: APScheduler, croniter
- Auth: JWT via python-jose, passlib bcrypt
- LLM: provider abstraction for OpenAI, Anthropic, Gemini, and mock tests
- Tools: HTTP, Slack, Discord, SMTP email, WhatsApp
- Frontend: Vite, React 18, TypeScript, TailwindCSS, TanStack Query, React Router, Axios
- Deployment: Docker Compose, Nginx

## Key Documentation

- [Architecture](docs/architecture.md)
- [Orchestration Design](docs/orchestration.md)
- [Workflows](docs/workflows.md)
- [Backend](docs/backend.md)
- [Frontend](docs/frontend.md)
- [API Overview](docs/api-overview.md)
- [Deployment](docs/deployment.md)
- [Testing and Debugging](docs/testing.md)
- [Roadmap](docs/roadmap.md)
- [Architecture Decisions](docs/decisions/)
- [Bug and Race-Condition Notes](docs/bugs/)

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

Run migrations:

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
- `ENCRYPTION_KEY`: credential encryption key
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`: provider API keys
- `CORS_ORIGINS`: comma-separated frontend origins
- `APP_BASE_URL`: base URL used for approval links
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `ARQ_MAX_JOBS`: database/worker sizing

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
- Run timeline
- Workflow detail/editor
- Integrations
- Pending approvals

## Example V2 Workflow JSON

```json
{
  "name": "Webhook triage with routing",
  "trigger_type": "webhook",
  "trigger_config": {
    "secret": "replace-with-random-secret"
  },
  "steps": [
    {
      "id": "triage",
      "type": "llm",
      "provider": "gemini",
      "model": "gemini-2.5-flash",
      "prompt": "Classify as urgent or normal: {{ trigger_data.body.message }}",
      "output_as": "triage_result"
    },
    {
      "id": "route_by_priority",
      "type": "switch",
      "on": "{{ triage_result.response }}",
      "on_no_match": "skip",
      "branches": {
        "urgent": [
          {
            "id": "approval",
            "type": "approval",
            "approver_email": "manager@example.com",
            "message": "Approve urgent Slack alert?",
            "timeout_seconds": 300,
            "timeout_action": "reject"
          },
          {
            "id": "send_alert",
            "type": "tool",
            "tool": "slack",
            "action": "send_message",
            "params": {
              "text": "{{ trigger_data.body.message }}"
            }
          }
        ],
        "normal": [
          {
            "id": "send_email",
            "type": "tool",
            "tool": "email",
            "action": "send_email",
            "params": {
              "to": "ops@example.com",
              "subject": "Normal workflow item",
              "body": "{{ trigger_data.body.message }}"
            }
          }
        ]
      }
    }
  ]
}
```
