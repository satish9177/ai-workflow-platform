# ADR 006: Approval Timeout Model

## Problem

Pending approvals can block workflows indefinitely. The system needs timeout behavior without adding a distributed timer subsystem.

## Decision

Store timeout intent on the approval row and poll due pending approvals with APScheduler. Timeout approve/reject reuses existing approval resume/reject paths.

## Alternatives Considered

- ARQ delayed jobs only.
- A dedicated timer service.
- Temporal-style durable timers.
- Expiring tokens without state transition.

## Why Chosen

Database polling is simple, durable, and consistent with existing cron polling. It survives API restarts because due work is discovered from PostgreSQL.

## Consequences

Timeouts are eventually processed by scheduler ticks. Duplicate timeout handling no-ops once the approval is no longer pending.

## Tradeoffs

Timeout precision is bounded by the poll interval. This is acceptable for V2 approval workflows.
