from typing import Any

import httpx

from app.tools.base import BaseTool, ToolResult


class HttpRequestTool(BaseTool):
    name = "http_request"
    display_name = "HTTP Request"
    description = "Send an HTTP request and return the response."

    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        if action != "execute":
            return ToolResult(success=False, error=f"Unsupported action: {action}")

        url = params.get("url")
        if not url:
            return ToolResult(success=False, error="Missing required parameter: url")

        method = params.get("method", "GET").upper()
        headers = params.get("headers") or {}
        body = params.get("body")
        timeout = params.get("timeout", 30)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, json=body)
        except httpx.TimeoutException:
            return ToolResult(success=False, error="Request timed out")
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
            metadata={"status_code": response.status_code, "headers": dict(response.headers)},
        )
