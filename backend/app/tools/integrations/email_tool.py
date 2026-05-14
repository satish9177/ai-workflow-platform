from typing import Any

from app.tools.base import BaseTool, ToolResult
from app.tools.integrations.email.smtp import SmtpEmailProvider


PROVIDER_MAP = {
    "smtp": SmtpEmailProvider,
}


async def run_email_tool(
    action: str,
    params: dict[str, Any],
    credentials: dict[str, Any],
    integration_type: str,
) -> ToolResult:
    ProviderClass = PROVIDER_MAP.get(integration_type)
    if not ProviderClass:
        raise RuntimeError(f"Unsupported email integration type: {integration_type}")

    provider = ProviderClass(credentials)

    if action == "send_email":
        to = str(params.get("to", "")).strip()
        subject = str(params.get("subject", "")).strip()
        body = str(params.get("body", "")).strip()
        reply_to = params.get("reply_to")

        if not to:
            raise RuntimeError("Email 'to' field is required")
        if not subject:
            raise RuntimeError("Email 'subject' field is required")
        if not body:
            raise RuntimeError("Email 'body' field is required")

        result = await provider.send(
            to=to,
            subject=subject,
            body_text=body,
            reply_to=str(reply_to) if reply_to else None,
        )
        return ToolResult(success=True, data=result)

    raise RuntimeError(f"Unknown email action: {action}")


class EmailTool(BaseTool):
    name = "email"
    display_name = "Email"
    description = "Send emails through configured email providers."

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        integration_type = str(credentials.pop("_integration_type", ""))
        return await run_email_tool(action, params, credentials, integration_type)
