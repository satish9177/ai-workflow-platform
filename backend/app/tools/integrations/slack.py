from typing import Any

from app.tools.base import BaseTool, ToolResult
from app.tools.integrations._http import _post


class SlackTool(BaseTool):
    name = "slack"
    display_name = "Slack"
    description = "Send messages to Slack via webhook"

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        if action != "send_message":
            return ToolResult(success=False, error=f"Unknown action: {action}")

        webhook_url = credentials.get("webhook_url")
        if not webhook_url:
            return ToolResult(success=False, error="webhook_url missing from credentials")

        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            return ToolResult(success=False, error="text is required")

        payload: dict[str, Any] = {"text": text}
        username = params.get("username")
        if username:
            payload["username"] = username
        icon_emoji = params.get("icon_emoji")
        if icon_emoji:
            payload["icon_emoji"] = icon_emoji

        try:
            await _post(webhook_url, payload)
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data={"sent": True})
