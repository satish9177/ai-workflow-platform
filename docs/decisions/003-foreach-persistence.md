# ADR 003: Persist Foreach Items

## Problem

Foreach items may come from templates or context. Re-resolving them on retry can produce a different list and corrupt iteration identity.

## Decision

Resolve foreach items once and persist the resolved list in `branch_executions.foreach_items`.

## Alternatives Considered

- Recompute items on every retry.
- Store only item count.
- Store items in transient worker memory.

## Why Chosen

Persisting the resolved list makes retries deterministic and keeps iteration keys stable.

## Consequences

Iteration jobs can recover item data from PostgreSQL. Worker restarts do not lose the item list.

## Tradeoffs

Large item lists increase database row size. V2 should keep foreach payloads practical and avoid huge lists.
