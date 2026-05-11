import inspect
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_approval_token
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.approval import Approval
from app.models.run import Run
from app.models.user import User
from app.schemas.approval import ApprovalActionRequest, ApprovalRead


router = APIRouter(tags=["approvals"])


async def enqueue_resume_workflow(run_id: str, step_id: str) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("resume_workflow", run_id, step_id)
    finally:
        close = getattr(pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(approval: Approval) -> bool:
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < _now()


async def _approval_from_token(token: str, db: AsyncSession) -> Approval:
    try:
        payload = decode_approval_token(token)
        approval_id = payload.get("sub")
        if not approval_id:
            raise JWTError("Missing approval id")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid approval token") from exc

    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    if _is_expired(approval):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Approval expired")
    return approval


@router.get("/pending", response_model=list[ApprovalRead])
async def pending_approvals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Approval]:
    result = await db.execute(
        select(Approval)
        .where(Approval.status == "pending", Approval.expires_at > _now())
        .order_by(Approval.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{token}", response_model=ApprovalRead)
async def get_approval(token: str, db: AsyncSession = Depends(get_db)) -> Approval:
    return await _approval_from_token(token, db)


@router.post("/{token}/approve", response_model=ApprovalRead)
async def approve(
    token: str,
    payload: ApprovalActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> Approval:
    approval = await _approval_from_token(token, db)
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval is not pending")

    approval.status = "approved"
    approval.responded_at = _now()
    await db.commit()
    await db.refresh(approval)
    await enqueue_resume_workflow(approval.run_id, approval.step_id)
    return approval


@router.post("/{token}/reject", response_model=ApprovalRead)
async def reject(
    token: str,
    payload: ApprovalActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> Approval:
    approval = await _approval_from_token(token, db)
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval is not pending")

    now = _now()
    approval.status = "rejected"
    approval.responded_at = now

    run = await db.get(Run, approval.run_id)
    if run is not None:
        run.status = "failed"
        run.error = "Rejected by approver"
        run.completed_at = now

    await db.commit()
    await db.refresh(approval)
    return approval
