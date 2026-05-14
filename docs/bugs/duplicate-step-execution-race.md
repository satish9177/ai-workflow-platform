# Duplicate StepExecution Race

## Symptom

Foreach approval iteration timeline rows duplicated:

```text
approval_loop.2.approve_item | foreach_index=2 | count=2
```

Common shape:

- one row `queued`
- another row `awaiting_approval`

## Reproduction Shape

Run foreach approval workflows repeatedly with bounded concurrency. Some runs created duplicate timeline rows for the same item.

## Root Cause

The queued reservation row and later running/awaiting row were not protected by a database uniqueness invariant. App-level reuse could still race.

## Execution Timeline

```text
scheduler reserves iteration row as queued
ARQ job starts
another retry/requeue path also starts
both try to transition/create StepExecution
one keeps queued row
one creates awaiting_approval row
timeline splits lifecycle across two rows
```

## Why Retries Exposed It

Foreach iteration jobs are independently retryable. A retry can overlap a queued/running transition if the previous attempt reached a side effect or pause boundary.

## DB Invariant Added

Partial unique index:

```text
step_executions(run_id, step_key, foreach_index)
WHERE foreach_index IS NOT NULL
```

## Code-Level Fix Summary

- Before adding the index, migration cleans duplicate foreach rows and keeps the most advanced lifecycle row.
- Creation catches `IntegrityError`, rolls back nested insert, reloads existing row, and continues using it.
- Queued -> running -> awaiting_approval is treated as one row lifecycle.

## Regression Tests Added

Tests simulate requeued/retried foreach approval iteration execution and assert only one row exists for the iteration identity.

## Lessons Learned

Timeline rows are not just logs. They participate in orchestration accounting, so their identity must be enforced.
