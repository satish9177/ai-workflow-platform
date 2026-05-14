# Testing and Debugging

This project has two kinds of tests:

- normal API/unit tests
- orchestration lifecycle tests that intentionally exercise retries, approvals, fan-in, and race-prone paths

## Local Setup

Backend:

```bash
cd backend
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
pytest tests/ -v
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

## Docker Test Pattern

When using Docker, run tests against the test database:

```bash
docker compose run --rm api pytest tests/ -v
```

If the local environment cannot resolve Python directly, run tests inside the API container.

## API and Worker Startup

API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Worker:

```bash
arq app.queue.settings.WorkerSettings
```

Migrations:

```bash
alembic upgrade head
```

## Orchestration Test Strategy

Good orchestration tests assert persisted state, not just returned responses.

Check:

- `workflow_runs.status`
- `workflow_runs.context`
- `step_results.status/output/error`
- `step_executions.status/error_details/output_preview`
- `branch_executions.completed_branches/failed_branches/merge_triggered`
- `approvals.status/responded_at/timed_out_at`

## Manual Workflow Testing

1. Create workflow through API or UI.
2. Trigger run.
3. Watch `/api/v1/runs/{run_id}/timeline`.
4. If approval pauses, inspect `/api/v1/approvals/pending`.
5. Approve/reject.
6. Confirm timeline terminal state.

## Approval Testing

Useful assertions:

```sql
SELECT id, run_id, step_id, status, expires_at, timeout_action, timed_out_at
FROM approvals
ORDER BY created_at DESC;
```

Expected states:

- pending approval: `approvals.status='pending'`, `step_executions.status='awaiting_approval'`
- manual approval: approval `approved`, step `completed`
- manual rejection: approval `rejected`, step `failed`
- timeout approve: approval `approved`, step `auto_approved`
- timeout reject: approval `rejected`, step `auto_rejected`

## Timeout Testing

Avoid sleeping in tests. Create an approval with timeout config, then set `expires_at` in the past and call the timeout handler or scheduler poll.

Check idempotency by calling the handler twice.

## Foreach Testing

Test more items than `concurrency_limit`.

Useful SQL:

```sql
SELECT step_key, foreach_index, status, COUNT(*)
FROM step_executions
WHERE run_id = '<run_id>'
GROUP BY step_key, foreach_index, status
ORDER BY step_key, foreach_index;
```

Duplicate detection:

```sql
SELECT step_key, foreach_index, COUNT(*)
FROM step_executions
WHERE run_id = '<run_id>'
GROUP BY step_key, foreach_index
HAVING COUNT(*) > 1;
```

There should be at most one row per `run_id + step_key + foreach_index`.

## Parallel Group Testing

Assert:

- branch jobs are enqueued
- sibling branches continue when one branch pauses
- fan-in waits until terminal states
- failed branch causes parent group failure
- merge output is deterministic

## Switch Testing

Assert:

- switch row exists
- selected branch container row exists
- skipped branch container rows exist
- skipped branch child rows do not exist
- selected child rows use dotted keys
- branch selection is persisted and reused on re-execution

Useful SQL:

```sql
SELECT step_key, parent_step_id, status, output_preview
FROM step_executions
WHERE run_id = '<run_id>'
ORDER BY step_index, created_at;
```

## Race-Condition Stress Testing

Repeat workflows with:

- foreach + approvals
- concurrency limits below item count
- approval approve/reject in quick succession
- worker restarts between queued and running iterations

Look for:

- duplicate approvals
- duplicate foreach step executions
- parent branches stuck `running`
- runs stuck `partially_paused` after all approvals resolve
- merge not triggered despite terminal children

## Timeline Interpretation

Use `step_executions` for lifecycle and `step_results` for logical output.

If a run is stuck:

1. Check run status and current step.
2. Check non-terminal step executions.
3. Check branch execution counters.
4. Check pending approvals.
5. Check ARQ worker logs.

Useful stuck-run query:

```sql
SELECT step_key, step_type, status, parent_step_id, branch_execution_id, foreach_index, error_details
FROM step_executions
WHERE run_id = '<run_id>'
ORDER BY step_index, created_at;
```

Branch counters:

```sql
SELECT step_key, branch_type, status, total_branches, completed_branches,
       failed_branches, cancelled_branches, merge_triggered
FROM branch_executions
WHERE run_id = '<run_id>';
```

## Worker Logging Guidance

Important log names:

- `arq.execute_workflow.started/succeeded/failed`
- `arq.resume_workflow.started/succeeded/failed`
- `arq.execute_parallel_branch.*`
- `arq.execute_foreach_iteration.*`
- `foreach.started/completed/failed`
- `parallel_group.started/completed/failed`
- `switch.started/branch_selected/completed/failed`
- `approval.timeout.*`
- `integration.resolve.*`

If cleanup warnings appear, distinguish infrastructure warnings from business failures.

## Test Boundaries

Do not use real external APIs in tests. Mock:

- OpenAI/Anthropic/Gemini
- SMTP
- Slack/Discord webhook HTTP calls
- WhatsApp/Meta API

Workflow engine tests should be deterministic and database-backed.
