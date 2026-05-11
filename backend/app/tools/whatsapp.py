from typing import Any

import httpx

from app.tools.base import BaseTool, ToolResult


class WhatsAppTool(BaseTool):
    name = "whatsapp"
    display_name = "WhatsApp"
    description = "Send WhatsApp messages through the Meta Graph API."

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        if action != "send_message":
            return ToolResult(success=False, error=f"Unsupported action: {action}")

        phone_number_id = credentials.get("phone_number_id")
        access_token = credentials.get("access_token")
        to_number = params.get("to")
        body = params.get("body")
        if not phone_number_id or not access_token:
            return ToolResult(success=False, error="Missing WhatsApp credentials")
        if not to_number or body is None:
            return ToolResult(success=False, error="Missing required WhatsApp parameters")

        normalized_to = str(to_number).replace("+", "").replace(" ", "")
        url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": normalized_to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            data: dict[str, Any] | list[Any] | str = response.json()
        except ValueError:
            data = response.text

        return ToolResult(
            success=response.is_success,
            data=data,
            error=None if response.is_success else response.text,
            metadata={"status_code": response.status_code},
        )

    async def test_connection(self, credentials: dict[str, Any]) -> ToolResult:
        phone_number_id = credentials.get("phone_number_id")
        access_token = credentials.get("access_token")
        if not phone_number_id or not access_token:
            return ToolResult(success=False, error="Missing WhatsApp credentials")

        url = f"https://graph.facebook.com/v19.0/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            data: dict[str, Any] | list[Any] | str = response.json()
        except ValueError:
            data = response.text

        return ToolResult(
            success=response.is_success,
            data=data,
            error=None if response.is_success else response.text,
            metadata={"status_code": response.status_code},
        )
