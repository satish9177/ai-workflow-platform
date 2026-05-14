# Orchestration Design

This document is the core design reference for the workflow engine.

The engine is intentionally **linear-with-groups**, not a DAG runtime.

```text
top-level workflow
  step 0
  step 1
  container step
    scoped child executions
  step 2
```

Container steps may fan out, iterate, or route, but control always returns to the parent sequence.

## Why Not a DAG Engine

The platform needs practical automation, human approvals, observability, integrations, and resumability. It does not yet need arbitrary dependency graphs, replay histories, distributed timers, or graph scheduling.

Avoiding a DAG runtime keeps the system:

- easier to reason about
- easier to debug from PostgreSQL state
- cheaper to operate
- safer to evolve incrementally
- compatible with a future workflow studio without requiring graph semantics today

## Core Persistence

```text
workflow_runs
  step_results
  step_executions
  branch_executions
  approvals
```

- `workflow_runs` stores run lifecycle and context.
- `step_results` stores logical outputs used for resume.
- `step_executions` stores timeline lifecycle and observability.
- `branch_executions` coordinates fan-out/fan-in.
- `approvals` stores human decision state.

## Step Results vs Step Executions

`StepResult` is the logical resume record:

- one output per logical step key
- used to skip completed steps on resume
- stores input/output/error

`StepExecution` is the timeline record:

- visible execution lifecycle
- started/completed timestamps
- attempt metadata
- parent hierarchy
- branch and foreach metadata
- sanitized previews
- structured errors

Both exist because correctness and observability answer different questions.

## Dotted Step Keys

Step identity is namespace-based:

```text
top-level:       summarize
parallel:        notify_group.slack
foreach:         approve_each.2.approve
switch branch:   route.urgent
switch child:    route.urgent.send_alert
```

Dotted keys prevent collisions when child IDs repeat across branches or iterations.

## Linear Execution

For each top-level step:

1. validate `id` and `type`
2. skip if `StepResult.status == completed`
3. create/update `StepExecution` as `running`
4. dispatch step
5. persist `StepResult`
6. finish `StepExecution`
7. write output into run context

On failure, the step and run are marked failed. On approval, the run is paused.

## Parallel Group

`parallel_group` is a fan-out/fan-in container.

```text
parallel_group notify_group
  branch notify_group.email
  branch notify_group.slack
fan-in
  notify_group output
continue parent workflow
```

Execution:

1. create `BranchExecution(branch_type="parallel_group")`
2. enqueue one ARQ job per child branch
3. each branch executes one child subtree
4. branch terminal state increments DB counters
5. merge is claimed idempotently
6. merged output is written under the group step key
7. parent workflow resumes

Merged output shape:

```json
{
  "branches": {
    "email": {"...": "..."},
    "slack": {"...": "..."}
  }
}
```

## Foreach

`foreach` resolves a list once and runs one child step per item.

```text
foreach approve_each items=[A,B,C]
  approve_each.0.approve
  approve_each.1.approve
  approve_each.2.approve
fan-in
  results[]
continue parent workflow
```

Execution:

1. resolve `items`
2. persist resolved items on `branch_executions.foreach_items`
3. enqueue up to `concurrency_limit`
4. each iteration receives:
   - `foreach.item`
   - `foreach.index`
   - configured `item_variable`
   - configured `index_variable`
5. terminal iteration state rebuilds counters from persisted `StepExecution` rows
6. queued iterations are dispatched as capacity opens
7. merge aggregates results

Merged output shape:

```json
{
  "results": [],
  "completed_count": 3,
  "failed_count": 0
}
```

V2 supports foreach depth 1 only.

## Switch

`switch` is a scoped inline container, not a graph edge system.

```text
route_by_priority
  urgent     selected
    send_alert
  normal     skipped
  default    skipped
continue parent workflow
```

Execution:

1. render `on`
2. treat result as string branch key
3. choose matching branch, default branch, or no branch
4. persist selected branch metadata before child execution
5. create branch container timeline rows
6. execute selected branch sequentially inline
7. write selected branch metadata to context
8. finish switch and continue parent workflow

Switch output preview:

```json
{
  "evaluated_value": "urgent",
  "selected_branch": "urgent",
  "matched": true,
  "used_default": false
}
```

The persisted selection is important. If a worker crashes after selection but before child completion, retry reuses the stored selected branch instead of re-rendering `on`.

## Approval

Approval is a pause primitive.

Linear approval:

```text
running -> paused -> resume_workflow -> running/completed
```

Branch/iteration approval:

```text
branch running -> awaiting_approval
run partially_paused
sibling branches continue
approval resolved
branch terminal
fan-in re-evaluates
```

Approval rows are idempotent by `run_id + step_id` while pending. This prevents duplicate approval cards when ARQ retries or concurrent branch paths re-enter approval creation.

## Approval Timeouts

Approval steps may define:

```json
{
  "timeout_seconds": 300,
  "timeout_action": "reject"
}
```

Timeout behavior is scheduler-driven:

1. approval row stores `timeout_action`
2. `expires_at` becomes the timeout due time
3. APScheduler polls due pending approvals
4. handler locks pending approval row
5. timeout only applies if still pending
6. approve/reject timeout reuses existing resume/reject paths

Timeout states appear in timeline as `auto_approved` or `auto_rejected`.

## Partial Pauses

`partially_paused` means at least one branch/iteration is waiting for approval while the overall orchestration has not reached terminal state.

Important rules:

- paused approval is non-terminal
- sibling branches/iterations can continue
- parent fan-in waits until all branches/iterations are terminal
- approving a nested approval resumes only that branch/iteration path

## Retry and Idempotency

Step retry applies to LLM and tool steps.

The engine protects retries with durable state:

- completed `StepResult` rows are skipped
- foreach items are persisted once
- switch branch selection is persisted once
- pending approvals are unique
- foreach `StepExecution` identity is unique for `run_id + step_key + foreach_index`

Provider errors classify retryability. Non-retryable provider failures fail immediately even if retry config exists.

## Fan-In Coordination

Fan-in is DB-backed. The merge operation is claimed with an atomic update against `branch_executions.merge_triggered`.

This means duplicate branch completions or ARQ retries can attempt merge safely; only one merge wins.

## Context Semantics

Run context is shared JSON.

Child steps can read ancestor context. Parallel and foreach sibling outputs should not be assumed available during sibling execution. Container merge outputs are deterministic and become available only after fan-in.

Switch branches do not isolate context in V2. The selected branch writes normal step outputs into shared context.

## Timeline Model

Timeline is a lifecycle projection, not replay history.

Important fields:

- `step_key`: dotted execution identity
- `parent_step_id`: hierarchy for switch branch/child rows
- `branch_execution_id`: parallel/foreach ownership
- `foreach_index`, `foreach_item`
- `branch_key`
- `status`
- `attempt_number`, `max_attempts`
- `input_preview`, `output_preview`
- `error_details`

Statuses include:

- `pending`
- `queued`
- `running`
- `awaiting_approval`
- `partially_paused`
- `completed`
- `failed`
- `cancelled`
- `skipped`
- `auto_approved`
- `auto_rejected`

## Worker Flow

```text
API request
  create run / update approval
  enqueue ARQ job

ARQ worker
  open AsyncSession
  execute/resume/branch/iteration
  commit state transitions
  close session
```

Close/rollback errors are logged as infrastructure warnings and should not mask business errors.

## Design Boundary

The engine deliberately does not support:

- arbitrary dependency edges
- multiple matching switch branches
- dynamic runtime branch creation
- nested foreach beyond depth 1
- distributed replay
- event-sourced history
- branch-level retry policies
- branch-level timeouts

Those boundaries are part of keeping the V2 engine maintainable.
