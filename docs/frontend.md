# Frontend

The frontend is an internal React dashboard in `frontend/`. It is intentionally plain: no component library, no complex state manager, and no workflow-canvas runtime.

## Stack

- Vite
- React 18
- TypeScript
- TailwindCSS
- TanStack Query
- React Router
- Axios

## Pages

- `/login`: login form.
- `/runs`: run list with status badges and polling.
- `/runs/:id`: run timeline and debugging view.
- `/workflows`: workflow list, trigger, toggle, schedule badge.
- `/workflows/:id`: workflow detail, trigger settings, schedule/webhook UI, lightweight step editor.
- `/workflows/:id/studio`: Workflow Studio V1 for full JSON-first workflow editing.
- `/workflows/new/studio`: create a new workflow from a full JSON document.
- `/approvals`: pending approval cards.
- `/integrations`: integration instance management.
- `/providers`: LLM provider/model browser.
- `/templates`: template gallery.
- `/templates/:id`: create workflow from template.

## Timeline UI

The run detail page consumes `GET /api/v1/runs/{run_id}/timeline`.

Timeline data comes from:

- `StepExecution` rows for step/container lifecycle.
- `BranchExecution` rows for parallel/foreach fan-in state.

The Run Detail timeline renders a nested execution tree, not a DAG/canvas view. It supports:

- linear step hierarchy
- `parallel_group` branches
- `foreach` iterations
- `switch` selected/skipped branches
- approvals and approval timeout states
- retry attempts
- payload previews and structured errors

The UI builds hierarchy from `parent_step_id` and dotted `step_key` fallback. It should treat `step_key`, `parent_step_id`, `foreach_index`, and `branch_key` as display/debugging metadata. It should not infer execution semantics that are not present in the API.

## API Client

`src/api/client.ts` owns:

- base URL selection from `VITE_API_URL`
- JWT Authorization header
- 401 redirect to `/login`
- normalized error messages

Feature-specific clients live under `src/api/`.

## Workflow Editing

The workflow detail editor is intentionally form/textarea based:

- LLM prompts and system messages
- approval messages
- tool params JSON
- integration selection
- trigger config

It preserves unknown step fields to avoid damaging workflow definitions created through API or future UI versions.

## Workflow Studio V1

Workflow Studio is the JSON-first editor for full workflow documents, including `steps`.

It provides:

- full workflow JSON editing
- frontend validation panel
- backend save errors
- structure preview for linear, `parallel_group`, `foreach`, and `switch`
- step snippets for common V2 primitives
- save and run actions

It is not a DAG canvas, graph editor, or drag/drop builder. The goal is developer/operator workflow testing without Swagger.

## Local Commands

```bash
cd frontend
npm install
npm run dev
```

Build:

```bash
npm run build
```

## Configuration

Create `frontend/.env` from `frontend/.env.example`.

```bash
VITE_API_URL=http://localhost:8000
```

If unset, the client falls back to `http://localhost:8000`.

## UI Boundaries

The current UI is an operator dashboard plus JSON-first Workflow Studio. It intentionally does not implement drag/drop graph editing, branch graph visualization, or schema-driven form generation yet.
