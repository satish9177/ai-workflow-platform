# Frontend

The frontend is an internal React dashboard in `frontend/`.

## Stack

- Vite
- React 18
- TypeScript
- TailwindCSS
- TanStack Query
- React Router
- Axios

## Pages

- `/login`: login form
- `/runs`: recent runs table
- `/runs/:id`: run detail and step results
- `/workflows`: workflow list, trigger, toggle
- `/approvals`: pending approvals

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

If `VITE_API_URL` is unset, the frontend defaults to `http://localhost:8000`.
