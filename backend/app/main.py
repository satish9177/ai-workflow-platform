from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router


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


@app.get("/health")
async def health():
    return {"status": "ok"}
