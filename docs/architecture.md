# Architecture

The platform is a compact workflow automation MVP. It keeps the architecture intentionally direct: FastAPI handles HTTP APIs, PostgreSQL stores workflow state, Redis/ARQ handles background jobs, and a React dashboard provides an internal operator UI.

## Workflow Engine

The engine loads a `Run` and its `Workflow`, then walks the workflow's JSON `steps` in order. Each step is executed by type and persisted to `step_results`. Completed steps are skipped when a run resumes, which makes approval resume behavior deterministic.

Supported execution outcomes:

- `completed`: all steps finished
- `failed`: a step or workflow lookup failed
- `paused`: an approval step is waiting for a human response
- `cancelled`: a user cancelled the run

## Runs

A run is a single execution of a workflow. Runs store trigger data, execution context, current step, timestamps, and error state. Step outputs are also copied into the run context so later steps can reference earlier results.

## Approvals

Approval steps create an `Approval` row, email an approval link when SMTP is configured, and pause the run. Approve/reject routes are public token routes. Approval resumes enqueue an ARQ job instead of executing inline.

## Resumable Execution

When an approval is accepted, `resume_run` marks the approval step completed and calls `execute_run` again. The executor skips completed step results and continues from the next pending step.

## ARQ Workers

Redis stores ARQ jobs. The worker exposes:

- `execute_workflow(ctx, run_id)`
- `resume_workflow(ctx, run_id, step_id)`

The API enqueues work and returns immediately.

## Cron Polling

The FastAPI lifespan starts an APScheduler job that polls active cron-triggered workflows every minute. Due workflows create pending runs and enqueue `execute_workflow`.

## Webhook Triggers

Webhook routes accept public POSTs at `/webhooks/{workflow_id}` with a token query parameter. A valid token creates a pending run and enqueues execution.

## Tool System

Tools implement a small `BaseTool` interface and are registered in `ToolRegistry`. Current tools include HTTP requests, SMTP email, and WhatsApp messaging. Integration credentials are encrypted before storage.

## Memory and Context

Conversation memory is stored in `conversation_turns`. LLM steps can build OpenAI-style message lists from saved history plus the new user prompt. Run context carries trigger data and step outputs during execution.

## PostgreSQL and Redis

PostgreSQL is used for durable workflow state, auditability, approvals, and result history. Redis is used only for queueing background jobs through ARQ.

## Explicit Non-Goals

The MVP intentionally avoids Temporal, Kubernetes, vector databases, sandboxed code execution, planner agents, and microservices. Those tools add operational weight before the core workflow model needs them.
