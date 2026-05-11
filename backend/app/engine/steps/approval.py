import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_approval_token
from app.config import settings
from app.models.approval import Approval


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
    approval = Approval(
        run_id=run_id,
        step_id=step["id"],
        token=f"pending-{uuid.uuid4()}",
        context=context,
        approver_email=step["approver_email"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=step.get("expires_hours", 24)),
    )
    db.add(approval)
    await db.flush()

    approval.token = create_approval_token(approval.id, approval.approver_email, step.get("expires_hours", 24))
    await db.commit()
    await db.refresh(approval)
    _send_approval_email(approval, step, context)
    raise ApprovalRequiredException(approval.id)


def _send_approval_email(approval: Approval, step: dict[str, Any], context: dict[str, Any]) -> None:
    if not settings.smtp_user:
        return

    approve_url = f"{settings.app_base_url}/approvals/{approval.token}/approve"
    reject_url = f"{settings.app_base_url}/approvals/{approval.token}/reject"

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = approval.approver_email
    message["Subject"] = step.get("subject", "Workflow approval required")
    message.set_content(
        "\n".join(
            [
                step.get("body", "A workflow step requires your approval."),
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
