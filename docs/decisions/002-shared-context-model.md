# ADR 002: Shared Context Model

## Problem

Steps need to pass data to later steps. Container children also need access to trigger data and ancestor outputs.

## Decision

Use a shared JSON run context. Step outputs are written under their step key and optional `output_as` alias. Foreach adds scoped variables. Switch records selected branch metadata.

## Alternatives Considered

- Fully isolated branch contexts.
- Immutable context snapshots only.
- Event-log-derived context reconstruction.

## Why Chosen

Shared JSON context is simple, visible, and matches the product’s current workflow authoring model.

## Consequences

Later top-level steps can read container merge outputs. Switch selected child steps can write directly to normal context.

## Tradeoffs

Parallel and foreach siblings must not rely on sibling outputs during execution. Deterministic merge outputs are the safe communication boundary.
