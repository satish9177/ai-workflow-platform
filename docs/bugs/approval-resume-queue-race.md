# Approval Resume Queue Race

## Symptom

Foreach approvals resolved successfully, but queued later iterations stayed queued and the parent foreach remained running.

Observed shape:

- `concurrency_limit=2`
- iterations 0 and 1 approved
- iteration 2 remained queued
- parent foreach never merged

## Reproduction Shape

Use foreach approval with more items than concurrency limit. Resolve active approvals. Occasionally the next queued iteration would not start.

## Root Cause

Approval resume completion did not always re-enter the same scheduling path as normal terminal iteration completion. The scheduler saw active/queued counts inconsistently after approval resolution.

## Execution Timeline

```text
iteration 0 awaiting approval
iteration 1 awaiting approval
iteration 2 queued
approval 0 resolves
approval 1 resolves
counters update
queued iteration is not redispatched
fan-in waits forever
```

## Why Retries Exposed It

Approval resume is not the same ARQ job as initial iteration execution. If resume bypasses normal iteration terminal reconciliation, bounded scheduling capacity is not released consistently.

## DB Invariant Added

No new table was needed for this specific bug. The fix relies on existing persisted statuses and the unique foreach step execution identity.

## Code-Level Fix Summary

- Approval resume inside foreach calls normal foreach counter sync.
- It evaluates merge readiness.
- If not ready, it dispatches next queued/fresh iterations according to concurrency capacity.
- It can redispatch recoverable queued iterations when approvals are no longer blocking.

## Regression Tests Added

Tests verify approval resume redispatches a queued third iteration and parent foreach completes.

## Lessons Learned

Every terminal path must run the same fan-in and capacity-release logic, including approval resolution paths.
