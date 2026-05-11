# API Overview

Base API prefix: `/api/v1`

## Auth

- `POST /api/v1/auth/register`: create user
- `POST /api/v1/auth/login`: issue access token
- `GET /api/v1/auth/me`: current user

## Workflows

- `GET /api/v1/workflows/`: list workflows
- `POST /api/v1/workflows/`: create workflow
- `GET /api/v1/workflows/{id}`: get workflow
- `PUT /api/v1/workflows/{id}`: update workflow
- `DELETE /api/v1/workflows/{id}`: delete workflow
- `POST /api/v1/workflows/{id}/run`: enqueue manual run
- `POST /api/v1/workflows/{id}/toggle`: toggle active state

## Runs

- `GET /api/v1/runs/`: list runs
- `GET /api/v1/runs/{id}`: run detail with step results
- `POST /api/v1/runs/{id}/cancel`: cancel active run
- `POST /api/v1/runs/{id}/retry`: retry failed run

## Approvals

- `GET /api/v1/approvals/pending`: pending approvals
- `GET /api/v1/approvals/{token}`: public approval detail
- `POST /api/v1/approvals/{token}/approve`: approve and enqueue resume
- `POST /api/v1/approvals/{token}/reject`: reject and fail run

## Integrations

- `GET /api/v1/integrations/`: registered tool integration status
- `PUT /api/v1/integrations/{name}`: upsert encrypted credentials
- `DELETE /api/v1/integrations/{name}`: delete integration
- `POST /api/v1/integrations/{name}/test`: test stored credentials

## Webhooks

- `POST /webhooks/{workflow_id}?token=...`: trigger webhook workflow

## Health

- `GET /health`: service health check
