from typing import Any

import httpx


async def _post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    if not url:
        raise RuntimeError("url is required")

    request_headers = headers or {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=request_headers)
    except httpx.TimeoutException:
        raise RuntimeError(f"Request timed out after {timeout}s") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(str(exc)) from exc

    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

    try:
        return response.json()
    except ValueError:
        return {}
