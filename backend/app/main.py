from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.approvals import router as approvals_router
from app.routers.auth import router as auth_router
from app.routers.integrations import router as integrations_router
from app.routers.runs import router as runs_router
from app.routers.webhooks import router as webhooks_router
from app.routers.workflows import router as workflows_router


@asynccontextmanager
async def lifespan_stub(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(title="Workflow Platform", lifespan=lifespan_stub)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(workflows_router, prefix="/api/v1/workflows")
app.include_router(runs_router, prefix="/api/v1/runs")
app.include_router(approvals_router, prefix="/api/v1/approvals")
app.include_router(integrations_router, prefix="/api/v1/integrations")
app.include_router(webhooks_router, prefix="/webhooks")


@app.get("/health")
async def health():
    return {"status": "ok"}
