# Architecture

This platform is a lightweight AI workflow orchestration system. It intentionally stays below the complexity line of Temporal, Airflow, event sourcing, actor systems, or a general DAG runtime.

The central model is **linear-with-groups**:

```text
workflow run
  step A
  parallel_group / foreach / switch container
    scoped child step executions
  step D
```

Top-level workflows remain ordered lists. Some steps are containers that execute scoped child steps, then return control to the parent sequence.

## System Components

- **FastAPI API**: authentication, workflow CRUD, runs, approvals, webhooks, integrations, LLM provider metadata.
- **PostgreSQL**: durable source of truth for workflows, runs, step results, step executions, branch executions, approvals, integrations, and memory.
- **Redis + ARQ**: background job queue for workflow execution, approval resume, parallel branches, and foreach iterations.
- **APScheduler**: lightweight in-process polling for cron triggers and approval timeouts.
- **React dashboard**: internal operator UI for workflows, runs, timelines, approvals, integrations, providers, and templates.

## Durable Execution State

The engine persists several layers of state:

- `workflow_runs`: run-level lifecycle, trigger data, context, current step, and error state.
- `step_results`: logical step outputs used for resume and context reconstruction.
- `step_executions`: timeline-oriented lifecycle records for every visible step/container/branch.
- `branch_executions`: fan-out/fan-in coordination for `parallel_group` and `foreach`.
- `approvals`: human approval tokens, pending/resolved state, timeout metadata.

`step_results` answer “has this logical step completed?” while `step_executions` answer “what happened and when?”.

## Orchestration Model

The executor processes top-level steps in order. For normal steps it dispatches directly. For containers:

- `parallel_group`: creates a `branch_execution`, enqueues one branch job per child step, waits for all branches to reach terminal state, merges deterministic branch output.
- `foreach`: resolves items once, persists them on `branch_executions.foreach_items`, enqueues bounded iteration jobs, waits for all iterations to reach terminal state, aggregates results.
- `switch`: renders a branch key, persists selected branch metadata, creates skipped/selected branch timeline rows, executes exactly one selected branch inline, and continues.

Container steps do not create child workflow runs. All child execution remains under the same `workflow_runs.id`.

## Namespacing

Nested execution uses dotted step keys:

```text
parallel_group: notify_group.email
foreach:        approve_each.2.approve
switch:         route_by_priority.urgent.send_alert
```

This namespacing is a core invariant. It prevents collisions between repeated child IDs and makes timeline debugging readable.

## Context Model

The run context is shared and JSON-based. Later steps can read:

- `trigger_data`
- prior step outputs by step ID
- `output_as` aliases
- foreach variables: `foreach.item`, `foreach.index`
- switch metadata: `switch_id.__branch__`, `switch_id.__evaluated__`

V2 does not isolate switch branch context. Parallel and foreach children read ancestor context, but sibling outputs are merged only through deterministic container outputs.

## Approval Lifecycle

Approval steps create an `approvals` row and pause execution:

- linear approval: run status becomes `paused`
- branch/iteration approval: run and branch can become `partially_paused`

Approve/reject routes update approval state and reuse existing resume/fail paths. Approval timeouts are handled by APScheduler polling pending approvals with configured timeout metadata. Timeout approve behaves like approval; timeout reject behaves like rejection.

## Observability

The timeline API is built from `step_executions` and `branch_executions`.

Timeline records include:

- step hierarchy via `parent_step_id`
- dotted `step_key`
- branch/foreach metadata
- lifecycle status
- attempts
- provider/model/tool metadata
- sanitized input/output previews
- structured error details

This is intentionally not event sourcing. It is compact lifecycle observability for debugging current V2 orchestration.

## Workers and Jobs

ARQ workers expose:

- `execute_workflow`
- `resume_workflow`
- `execute_parallel_branch_job`
- `execute_foreach_iteration_job`

The API enqueues work and returns quickly. Worker jobs open async SQLAlchemy sessions, preserve business exceptions, and log rollback/close infrastructure warnings without masking original execution failures.

## DB-Backed Invariants

Important invariants are enforced in the database where app-level checks proved race-prone:

- one pending approval per `run_id + step_id`
- one foreach `StepExecution` per `run_id + step_key + foreach_index`
- durable `foreach_items` so retries do not re-resolve item lists
- durable switch branch selection so retries do not re-evaluate routing

These constraints are part of the orchestration design, not incidental schema details.

## Why PostgreSQL and Redis

PostgreSQL stores all correctness-critical state. Redis only queues ARQ jobs. If Redis loses a job, persisted run/branch/step state remains inspectable and recoverable by targeted requeue/retry paths.

## Explicit Non-Goals

The current system intentionally does not implement:

- arbitrary DAG execution
- dynamic graph rewrites
- distributed workflow replay
- event sourcing
- Temporal-style timers
- provider fallback chains
- object storage for large payloads
- Kubernetes-native orchestration

Those may be revisited only when the product need justifies their operational cost.
