# ADR 005: Switch as Inline Container

## Problem

Workflows need conditional branching without introducing graph edges or DAG scheduling.

## Decision

Implement `switch` as a scoped inline container. It renders `on`, selects one branch, persists the selection, executes selected child steps sequentially, and continues the parent workflow.

## Alternatives Considered

- DAG edges from conditions to arbitrary later steps.
- Multiple matching branches.
- Dynamic runtime branch creation.

## Why Chosen

Inline branching preserves the linear-with-groups model and keeps timeline hierarchy simple.

## Consequences

Skipped branch containers are visible in timeline, but skipped child steps are not created. Branch selection is idempotent because it is persisted before child execution.

## Tradeoffs

Switch cannot express arbitrary graph jumps. That is intentional.
