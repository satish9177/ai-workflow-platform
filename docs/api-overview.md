# API Overview

Base API prefix: `/api/v1`.

Most endpoints require JWT auth. Public endpoints are approval token routes and webhook trigger routes.

## Auth

- `POST /api/v1/auth/register`: create user.
- `POST /api/v1/auth/login`: issue access token.
- `GET /api/v1/auth/me`: current user.

## Workflows

- `GET /api/v1/workflows/`: list workflows.
- `POST /api/v1/workflows/`: create workflow.
- `GET /api/v1/workflows/{id}`: get workflow.
- `PUT /api/v1/workflows/{id}`: update workflow.
- `DELETE /api/v1/workflows/{id}`: delete workflow.
- `POST /api/v1/workflows/{id}/run`: create pending run and enqueue execution.
- `POST /api/v1/workflows/{id}/toggle`: flip active state.

Workflow updates validate step shape for `llm`, `tool`, `approval`, `condition`, `parallel_group`, `foreach`, and `switch`.

## Runs

- `GET /api/v1/runs/`: list runs.
- `GET /api/v1/runs/{id}`: run detail with logical step results.
- `GET /api/v1/runs/{run_id}/timeline`: execution timeline with step executions and branch executions.
- `POST /api/v1/runs/{id}/cancel`: cancel active run.
- `POST /api/v1/runs/{id}/retry`: retry failed run.

Use the timeline endpoint for debugging orchestration behavior. Use the run detail endpoint for compact logical outputs.

## Approvals

- `GET /api/v1/approvals/pending`: pending unexpired approvals for the dashboard.
- `GET /api/v1/approvals/{token}`: public approval detail.
- `POST /api/v1/approvals/{token}/approve`: approve and enqueue/resume execution.
- `POST /api/v1/approvals/{token}/reject`: reject and fail the linear step or branch/iteration.

Approval timeout processing is scheduler-driven, not exposed as a public API.

## Integrations

Current V2 integration API supports multiple instances:

- `GET /api/v1/integrations`: list integrations and placeholders.
- `GET /api/v1/integrations?type=slack`: list enabled integrations by type.
- `POST /api/v1/integrations`: create integration instance.
- `GET /api/v1/integrations/{id}`: get integration metadata.
- `PATCH /api/v1/integrations/{id}`: update display name, credentials, config.
- `DELETE /api/v1/integrations/{id}`: delete if no workflow references it.
- `POST /api/v1/integrations/{id}/test`: test credentials and update status.

Legacy-compatible routes may still upsert/test by type for older UI flows, but new code should prefer instance IDs.

Credentials are never returned decrypted.

## LLM Providers

- `GET /api/v1/llm/providers`: list registered provider IDs and display names.
- `GET /api/v1/llm/providers/{provider_id}/models`: list supported model names.

These are read-only registry endpoints.

## Webhooks

- `POST /api/v1/webhooks/{webhook_id}`: V2 webhook trigger.
- `POST /webhooks/{webhook_id}`: public compatibility prefix.

Webhook runs store sanitized request data in `run.trigger_data`:

- `body`
- `headers`
- `query_params`

If workflow trigger config includes `secret`, callers must provide `X-Webhook-Secret`.

## Health

- `GET /health`: service health check.

Responses include `X-Request-ID`. If the caller sends `X-Request-ID`, it is reused.
