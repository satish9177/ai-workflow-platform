import inspect
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.auth import decode_approval_token
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.engine.executor import resume_branch_approval
from app.models.approval import Approval
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.user import User
from app.schemas.approval import ApprovalActionRequest, ApprovalRead


router = APIRouter(tags=["approvals"])
logger = structlog.get_logger(__name__)


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


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


async def _fail_rejected_approval_step(
    approval: Approval,
    db: AsyncSession,
    now: datetime,
) -> None:
    result = await db.execute(
        select(StepExecution).where(
            StepExecution.run_id == approval.run_id,
            StepExecution.status == "awaiting_approval",
        ).order_by(
            StepExecution.started_at.desc().nullslast(),
            StepExecution.created_at.desc(),
        )
    )
    step_execution = result.scalars().first()
    if step_execution is None:
        logger.warning(
            "approval.reject_step_execution_not_found",
            run_id=approval.run_id,
            approval_id=approval.id,
            step_id=approval.step_id,
        )
        return

    step_execution.status = "failed"
    step_execution.completed_at = now
    step_execution.duration_ms = _duration_ms(step_execution.started_at, now)
    step_execution.error_details = {
        "type": "ApprovalRejected",
        "message": "Rejected by approver",
    }
    step_execution.output_preview = {"approved": False, "status": "rejected"}


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

    handled_branch = await resume_branch_approval(approval.run_id, approval.step_id, False, db)
    if not handled_branch:
        run = await db.get(Run, approval.run_id)
        if run is not None:
            run.status = "failed"
            run.error = "Rejected by approver"
            run.completed_at = now

        await _fail_rejected_approval_step(approval, db, now)
        await db.commit()
    await db.refresh(approval)
    return approval
