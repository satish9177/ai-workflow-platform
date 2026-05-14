# Foreach Fan-In Stuck Running

## Symptom

External side effects completed, but some foreach iteration `StepExecution` rows remained `running`. The parent foreach container never reached terminal completion.

## Reproduction Shape

Use a foreach with bounded concurrency and multiple iterations. Let earlier iterations complete and dispatch later queued iterations. Intermittently, the last iteration would not participate in terminal accounting.

## Root Cause

The bounded scheduler path could dispatch the next iteration while terminal counter reconciliation and queued/running status transitions were not consistently tied together. A job could be assumed running without guaranteed terminal accounting.

## Execution Timeline

```text
iteration 0 completes
counter sync sees completed=1
next iteration is queued/dispatched
iteration side effect succeeds
terminal reconciliation path is skipped or races
parent sees running/queued gap forever
```

## Why Retries Exposed It

ARQ retries can re-enter execution after side effects or partial persistence. If terminal accounting is increment-only or path-dependent, retries expose missing idempotency.

## DB Invariant Added

Foreach fan-in now rebuilds counters from persisted `StepExecution` statuses instead of trusting only increment paths.

## Code-Level Fix Summary

- Reconcile foreach counters from database state.
- Ensure terminal iteration paths call fan-in evaluation.
- Ensure queued iteration recovery can redispatch when active approvals resolve.

## Regression Tests Added

Tests cover bounded concurrency, recoverable queued redispatch, and parent merge after resumed approvals.

## Lessons Learned

Fan-in should derive truth from durable terminal rows. Counters are cached coordination state, not the only source of truth.
