# AGENTS.md

## Project Overview

AI workflow orchestration platform built with:

Backend:

* FastAPI
* Async SQLAlchemy
* PostgreSQL
* Redis
* ARQ workers

Frontend:

* React
* TypeScript
* TailwindCSS
* TanStack Query

## Architecture Principles

* Keep orchestration engine modular
* Avoid hardcoded tool/provider logic
* Prefer registry patterns over conditionals
* Preserve async-first architecture
* Do not introduce unnecessary abstractions
* Prefer pragmatic V2 implementations
* Avoid overengineering

## Backend Rules

* Use async SQLAlchemy patterns
* Keep services separated from API routes
* Use Alembic for all schema changes
* Preserve current workflow execution architecture
* Maintain retry/backoff compatibility

## Frontend Rules

* Use TanStack Query for API state
* Use reusable UI components
* Keep timeline UI modular
* Prefer composition over massive components

## Workflow Engine Constraints

* Workflow runs must remain resumable
* Execution state must persist in DB
* Step execution should be traceable
* Future compatibility with parallel execution matters
* Future compatibility with foreach execution matters

## Coding Style

* Production-quality code only
* No pseudo-code
* Minimal diffs
* Keep naming consistent
* Avoid breaking existing APIs
* Add tests for major functionality
