import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.auth import create_approval_token
from app.config import settings
from app.models.approval import Approval
from app.utils.template_renderer import render_template_object


logger = structlog.get_logger(__name__)


class ApprovalRequiredException(Exception):
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval required: {approval_id}")


async def run_approval_step(
    step: dict[str, Any],
    context: dict[str, Any],
    run_id: str,
    db: AsyncSession,
) -> None:
    rendered_step = render_template_object(step, context)
    approver_email = rendered_step.get("approver_email") or rendered_step.get("approver_email_template")
    step_id = rendered_step["id"]
    timeout_action: str | None = None
    timeout_seconds = rendered_step.get("timeout_seconds")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=rendered_step.get("expires_hours", 24))
    if timeout_seconds is not None:
        try:
            parsed_timeout_seconds = int(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_seconds must be greater than 0") from exc
        if parsed_timeout_seconds < 1:
            raise ValueError("timeout_seconds must be greater than 0")
        timeout_action = str(rendered_step.get("timeout_action") or "reject")
        if timeout_action not in {"approve", "reject"}:
            raise ValueError("timeout_action must be approve or reject")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=parsed_timeout_seconds)

    existing = (
        await db.execute(
            select(Approval).where(
                Approval.run_id == run_id,
                Approval.step_id == step_id,
                Approval.status == "pending",
            )
        )
    ).scalars().first()
    if existing is not None:
        raise ApprovalRequiredException(existing.id)

    approval = Approval(
        run_id=run_id,
        step_id=step_id,
        token=f"pending-{uuid.uuid4()}",
        context=context,
        approver_email=approver_email,
        expires_at=expires_at,
        timeout_action=timeout_action,
    )
    try:
        async with db.begin_nested():
            db.add(approval)
            await db.flush()
    except IntegrityError:
        existing = (
            await db.execute(
                select(Approval).where(
                    Approval.run_id == run_id,
                    Approval.step_id == step_id,
                    Approval.status == "pending",
                )
            )
        ).scalars().first()
        if existing is not None:
            raise ApprovalRequiredException(existing.id)
        raise

    approval.token = create_approval_token(approval.id, approval.approver_email, rendered_step.get("expires_hours", 24))
    await db.commit()
    await db.refresh(approval)
    if approval.timeout_action:
        logger.info(
            "approval.timeout.scheduled",
            approval_id=approval.id,
            run_id=approval.run_id,
            step_id=approval.step_id,
            timeout_action=approval.timeout_action,
            expires_at=approval.expires_at.isoformat(),
        )
    _send_approval_email(approval, rendered_step, context)
    raise ApprovalRequiredException(approval.id)


def _send_approval_email(approval: Approval, step: dict[str, Any], context: dict[str, Any]) -> None:
    if not settings.smtp_user:
        return

    approve_url = f"{settings.app_base_url}/approvals/{approval.token}/approve"
    reject_url = f"{settings.app_base_url}/approvals/{approval.token}/reject"

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = approval.approver_email
    rendered_step = render_template_object(step, context)
    message["Subject"] = rendered_step.get("subject", "Workflow approval required")
    message.set_content(
        "\n".join(
            [
                rendered_step.get("body", "A workflow step requires your approval."),
                "",
                f"Approve: {approve_url}",
                f"Reject: {reject_url}",
            ]
        )
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        return
