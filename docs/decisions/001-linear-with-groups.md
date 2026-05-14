# ADR 001: Linear-With-Groups Execution Model

## Problem

The platform needs branching, iteration, approvals, and concurrency, but a full DAG engine would add scheduling, dependency resolution, replay, and operational complexity before the product requires it.

## Decision

Use a linear top-level workflow with scoped container steps:

- `parallel_group`
- `foreach`
- `switch`

Containers execute child steps, merge or finish locally, then return control to the parent sequence.

## Alternatives Considered

- General DAG execution.
- Temporal-style durable workflow runtime.
- Airflow-style task graph scheduling.
- Event-sourced replay engine.

## Why Chosen

The current platform benefits more from deterministic state, simple debugging, and fast iteration than from arbitrary graph expressiveness.

## Consequences

Workflow execution is easier to reason about from database rows. Some advanced dependency patterns are intentionally unsupported.

## Tradeoffs

The model cannot express arbitrary joins or dynamic graph rewrites. Those should not be added by stealth through step semantics.
