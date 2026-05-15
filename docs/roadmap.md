# Roadmap and Boundaries

This roadmap documents what exists, what is intentionally unsupported, and where future work may go. It is not a commitment to build every listed direction.

## Completed V1 Foundations

- FastAPI backend.
- Async SQLAlchemy + PostgreSQL.
- Redis + ARQ workers.
- Alembic migrations.
- JWT auth.
- Workflow CRUD.
- Manual run execution.
- LLM step.
- Tool step.
- Approval pause/resume.
- Cron triggers.
- Webhook triggers.
- React internal dashboard.
- Docker Compose deployment.
- JSON-first Workflow Studio V1.

## Completed V2 Orchestration Features

- Execution timeline with `step_executions`.
- Payload previews with sanitization.
- `parallel_group`.
- `foreach` with persisted item lists and bounded concurrency.
- `switch` inline branching.
- Approval inside parallel and foreach.
- Approval timeouts.
- Partial pause state.
- Retry/backoff for LLM/tool steps.
- Provider error classification.
- DB-backed invariants for duplicate prevention.
- Multiple integration instances.
- SMTP, Slack, Discord, HTTP integrations.

## Completed V2 UI Features

- Workflow Studio V1 for full JSON workflow editing.
- Structure preview for nested workflow documents.
- Validation panel for JSON/root/step checks.
- Step snippets for LLM, tools, approvals, parallel groups, foreach, and switch.
- Save/run flow from the Studio.

## Current System Boundaries

The engine is linear-with-groups. It is not a general graph runtime.

Supported containers:

- `parallel_group`
- `foreach`
- `switch`

Unsupported:

- arbitrary DAG edges
- dynamic graph mutation
- nested foreach beyond V2 limits
- event-sourced replay
- distributed locks as primary correctness mechanism
- provider fallback chains
- branch-level timers beyond approval timeouts

## Intentionally Deferred

- Full visual workflow builder.
- DAG authoring.
- Object storage for large payload history.
- WebSocket live updates.
- Workflow replay from event log.
- SLA/escalation reminders.
- OAuth integrations for Gmail/Notion/Sheets.
- Provider cost analytics.
- Multi-tenant RBAC.
- Horizontal scheduler coordination.

## Possible Future Directions

### Workflow Studio

Build a UI that understands linear-with-groups semantics:

- step cards
- container hierarchy
- switch branches
- foreach settings
- approval configuration
- integration selection

Avoid pretending the system is a free-form DAG.

### Observability

Possible improvements:

- richer timeline filtering
- payload inspector with redaction controls
- retry history
- branch/iteration grouping in UI
- operational dashboards

### Scalability

Possible improvements:

- PgBouncer or managed pooler
- worker autoscaling
- scheduler leader election if multiple API replicas need active polling
- archived payload storage

### Integrations

Possible additions:

- Gmail OAuth
- SendGrid/Mailgun providers
- Notion
- Google Sheets
- GitHub webhooks presets

Each should fit the integration abstraction: workflow `tool` is separate from provider `integration_type`.

## Non-Goals Unless Requirements Change

- Rebuilding Temporal.
- Rebuilding Airflow.
- Arbitrary dependency graph scheduling.
- Distributed replay engine.
- Actor runtime.
- Kubernetes-native orchestration.
- Planner agents that rewrite workflows at runtime.

The design should evolve when product requirements demand it, not because a more complex architecture is available.
