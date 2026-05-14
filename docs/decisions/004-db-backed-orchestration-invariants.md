# ADR 004: DB-Backed Orchestration Invariants

## Problem

ARQ jobs can retry, overlap, or complete out of order. App-level existence checks are not sufficient under concurrency.

## Decision

Enforce important orchestration identities in PostgreSQL:

- one pending approval per `run_id + step_id`
- one foreach step execution per `run_id + step_key + foreach_index`
- merge claim through atomic `UPDATE ... RETURNING`

## Alternatives Considered

- In-memory locks.
- Redis locks.
- App-level “check then insert” only.

## Why Chosen

PostgreSQL already owns correctness-critical state. Constraints and atomic updates remain valid across processes and retries.

## Consequences

Race-prone paths become deterministic. Integrity errors are handled by reloading the existing row and continuing.

## Tradeoffs

Migrations are required for new invariants. Tests must exercise concurrency-like retry shapes, not only happy paths.
