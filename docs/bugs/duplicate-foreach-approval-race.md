# Duplicate Foreach Approval Race

## Symptom

Pending approvals sometimes showed duplicate approval cards for the same foreach item, especially with repeated child step IDs such as `approval_loop.2.approve_item`.

## Reproduction Shape

Run a foreach approval workflow with ARQ retries or rapid repeated execution. The same iteration could attempt approval creation more than once.

## Root Cause

Approval identity was not protected strongly enough at the database level. App-level lookup could race:

```text
job A checks pending approval: none
job B checks pending approval: none
job A inserts pending approval
job B inserts pending approval
```

The issue was worse inside foreach because child step IDs repeat conceptually across iterations and only become unique after dotted key expansion.

## Execution Timeline

```text
foreach iteration starts
approval step raises ApprovalRequiredException
worker retries before/around commit boundary
approval creation re-enters
duplicate pending rows become visible
dashboard shows duplicate cards
```

## Why Retries Exposed It

Approval creation is an intentional pause point. Pause points are retry-sensitive because the business action is “create durable wait state”.

## DB Invariant Added

Partial unique index:

```text
approvals(run_id, step_id) WHERE status = 'pending'
```

## Code-Level Fix Summary

- Approval creation uses nested transaction handling.
- On integrity race, reload existing pending approval.
- Existing pending approval is reused and returned through `ApprovalRequiredException`.

## Regression Tests Added

Tests simulate concurrent approval creation and assert exactly one pending approval exists.

## Lessons Learned

Pause-state creation must be idempotent and DB-backed. “Check then insert” is not safe under workers.
