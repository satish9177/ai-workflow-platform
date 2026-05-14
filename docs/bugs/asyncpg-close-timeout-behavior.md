# Asyncpg Close Timeout Behavior

## Symptom

Under repeated rapid orchestration execution, logs occasionally showed:

```text
Timed out closing connection after 1
```

Workflow correctness was stable, but the low-level close warning could appear near worker cleanup.

## Reproduction Shape

Run many orchestration-heavy workflows quickly, especially foreach/approval cases that create many short async DB sessions and worker jobs.

## Root Cause

This was infrastructure cleanup pressure around async SQLAlchemy/asyncpg connection lifecycle, not a business step failure. Session close/rollback errors could risk masking the original business outcome if not handled carefully.

## Execution Timeline

```text
ARQ job executes business work
commit succeeds or business error is raised
session cleanup starts
asyncpg close times out
cleanup exception is raised during finalization
```

## Why Retries Exposed It

High retry/concurrency scenarios produce more session churn. Connection cleanup warnings become more visible under orchestration stress.

## DB Invariant Added

None. This was pool/session hardening rather than orchestration state correctness.

## Code-Level Fix Summary

- Added pool hardening:
  - `pool_pre_ping`
  - `pool_recycle`
  - configurable pool size/overflow/timeout
  - asyncpg command/connect timeout
  - PostgreSQL statement and idle transaction timeouts
- ARQ `_run_with_session` logs rollback/close failures as infrastructure warnings.
- Close-time failures do not mask original business errors.

## Regression Tests Added

Tests verify close failure after successful work is logged and does not fail the job, and close failure during business failure does not mask the original exception.

## Lessons Learned

Infrastructure cleanup errors must be visible but must not rewrite business state or obscure the actual workflow failure.
