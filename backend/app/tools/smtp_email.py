import smtplib
from email.message import EmailMessage
from typing import Any

from app.config import settings
from app.tools.base import BaseTool, ToolResult


class SmtpEmailTool(BaseTool):
    name = "smtp_email"
    display_name = "SMTP Email"
    description = "Send an email through SMTP."

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        if action != "send":
            return ToolResult(success=False, error=f"Unsupported action: {action}")

        to_email = params.get("to")
        subject = params.get("subject")
        body = params.get("body")
        html = params.get("html")
        if not to_email or not subject or body is None:
            return ToolResult(success=False, error="Missing required email parameters")

        smtp_host = credentials.get("smtp_host") or settings.smtp_host
        smtp_port = int(credentials.get("smtp_port") or settings.smtp_port)
        smtp_user = credentials.get("smtp_user") or settings.smtp_user
        smtp_password = credentials.get("smtp_password") or settings.smtp_password
        from_email = credentials.get("smtp_from_email") or settings.smtp_from_email

        message = EmailMessage()
        message["From"] = from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(message)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data={"sent": True, "to": to_email})
