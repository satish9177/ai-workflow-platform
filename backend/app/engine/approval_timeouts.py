from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import AsyncSessionLocal
from app.engine.executor import reject_approval, resume_run
from app.models.approval import Approval


logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def handle_approval_timeout(approval_id: str, db: AsyncSession) -> bool:
    now = _now()
    result = await db.execute(
        select(Approval)
        .where(Approval.id == approval_id, Approval.status == "pending")
        .with_for_update()
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        logger.info("approval.timeout.skipped", approval_id=approval_id, reason="not_pending")
        return False

    if approval.timeout_action not in {"approve", "reject"}:
        logger.info(
            "approval.timeout.skipped",
            approval_id=approval.id,
            run_id=approval.run_id,
            step_id=approval.step_id,
            reason="timeout_not_configured",
        )
        return False

    expires_at = _as_aware(approval.expires_at)
    if expires_at > now:
        logger.info(
            "approval.timeout.skipped",
            approval_id=approval.id,
            run_id=approval.run_id,
            step_id=approval.step_id,
            timeout_action=approval.timeout_action,
            reason="not_due",
            expires_at=expires_at.isoformat(),
        )
        return False

    action = approval.timeout_action
    logger.info(
        "approval.timeout.triggered",
        approval_id=approval.id,
        run_id=approval.run_id,
        step_id=approval.step_id,
        timeout_action=action,
    )

    approval.status = "approved" if action == "approve" else "rejected"
    approval.responded_at = now
    approval.timed_out_at = now
    await db.flush()

    if action == "approve":
        await resume_run(
            approval.run_id,
            approval.step_id,
            db,
            timed_out=True,
            timeout_action=action,
        )
    else:
        await reject_approval(
            approval.run_id,
            approval.step_id,
            db,
            timed_out=True,
            timeout_action=action,
        )

    logger.info(
        "approval.timeout.completed",
        approval_id=approval.id,
        run_id=approval.run_id,
        step_id=approval.step_id,
        timeout_action=action,
    )
    return True


async def poll_approval_timeouts() -> None:
    now = _now()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Approval.id)
            .where(
                Approval.status == "pending",
                Approval.timeout_action.is_not(None),
                Approval.expires_at <= now,
            )
            .order_by(Approval.expires_at.asc())
        )
        approval_ids = list(result.scalars().all())

    for approval_id in approval_ids:
        async with AsyncSessionLocal() as db:
            try:
                await handle_approval_timeout(approval_id, db)
            except Exception:
                logger.exception("approval.timeout.failed", approval_id=approval_id)
