import pytest

from app.engine.steps.tool import run_tool_step
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def valid_encryption_key(monkeypatch):
    monkeypatch.setattr("app.routers.integrations.settings.encryption_key", "0" * 64)
    monkeypatch.setattr("app.engine.steps.tool.settings.encryption_key", "0" * 64)


async def _create_slack(client, auth_headers, display_name):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "slack",
            "display_name": display_name,
            "credentials": {"webhook_url": f"https://hooks.slack.test/{display_name}"},
            "config": {},
        },
    )
    assert response.status_code == 201
    return response.json()


async def _create_smtp(client, auth_headers, display_name):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "smtp",
            "display_name": display_name,
            "credentials": {
                "host": "smtp.example.com",
                "port": "587",
                "username": f"{display_name}@example.com",
                "password": "secret",
                "from_email": f"{display_name}@example.com",
            },
            "config": {},
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_executor_resolves_explicit_integration_id(client, auth_headers, monkeypatch):
    first = await _create_slack(client, auth_headers, "first")
    second = await _create_slack(client, auth_headers, "second")
    captured: dict = {}

    async def fake_execute(tool_name, action, params, credentials):
        captured["credentials"] = credentials
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        await run_tool_step(
            {
                "id": "send",
                "type": "tool",
                "tool": "slack",
                "action": "send_message",
                "integration_id": second["id"],
                "params": {"text": "hello"},
            },
            {},
            db,
        )

    assert captured["credentials"]["webhook_url"] == "https://hooks.slack.test/second"
    assert first["id"] != second["id"]


async def test_executor_fallback_uses_first_integration(client, auth_headers, monkeypatch):
    await _create_slack(client, auth_headers, "first")
    await _create_slack(client, auth_headers, "second")
    captured: dict = {}

    async def fake_execute(tool_name, action, params, credentials):
        captured["credentials"] = credentials
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        await run_tool_step(
            {
                "id": "send",
                "type": "tool",
                "tool": "slack",
                "action": "send_message",
                "params": {"text": "hello"},
            },
            {},
            db,
        )

    assert captured["credentials"]["webhook_url"] == "https://hooks.slack.test/first"


async def test_executor_invalid_integration_id_fails_clearly(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        with pytest.raises(RuntimeError, match="Integration not found: missing-id"):
            await run_tool_step(
                {
                    "id": "send",
                    "type": "tool",
                    "tool": "slack",
                    "action": "send_message",
                    "integration_id": "missing-id",
                    "params": {"text": "hello"},
                },
                {},
                db,
            )


async def test_executor_no_fallback_integration_fails_clearly(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        with pytest.raises(RuntimeError, match="No integration configured for tool: slack"):
            await run_tool_step(
                {
                    "id": "send",
                    "type": "tool",
                    "tool": "slack",
                    "action": "send_message",
                    "params": {"text": "hello"},
                },
                {},
                db,
            )


async def test_executor_resolves_explicit_email_smtp_integration_id(client, auth_headers, monkeypatch):
    smtp = await _create_smtp(client, auth_headers, "sender")
    captured: dict = {}

    async def fake_send(self, to, subject, body_text, body_html=None, reply_to=None):
        captured["host"] = self.host
        captured["username"] = self.username
        captured["to"] = to
        captured["subject"] = subject
        return {"success": True, "detail": "sent"}

    monkeypatch.setattr("app.tools.integrations.email.smtp.SmtpEmailProvider.send", fake_send)

    async with TestingSessionLocal() as db:
        output = await run_tool_step(
            {
                "id": "email",
                "type": "tool",
                "tool": "email",
                "action": "send_email",
                "integration_id": smtp["id"],
                "params": {
                    "to": "recipient@example.com",
                    "subject": "Hello",
                    "body": "Body",
                },
            },
            {},
            db,
        )

    assert output["data"]["success"] is True
    assert captured["host"] == "smtp.example.com"
    assert captured["username"] == "sender@example.com"
    assert captured["to"] == "recipient@example.com"


async def test_executor_fallback_uses_first_smtp_for_email_tool(client, auth_headers, monkeypatch):
    await _create_smtp(client, auth_headers, "first")
    await _create_smtp(client, auth_headers, "second")
    captured: dict = {}

    async def fake_send(self, to, subject, body_text, body_html=None, reply_to=None):
        captured["username"] = self.username
        return {"success": True, "detail": "sent"}

    monkeypatch.setattr("app.tools.integrations.email.smtp.SmtpEmailProvider.send", fake_send)

    async with TestingSessionLocal() as db:
        await run_tool_step(
            {
                "id": "email",
                "type": "tool",
                "tool": "email",
                "action": "send_email",
                "params": {
                    "to": "recipient@example.com",
                    "subject": "Hello",
                    "body": "Body",
                },
            },
            {},
            db,
        )

    assert captured["username"] == "first@example.com"


async def test_executor_invalid_email_integration_id_fails_clearly(monkeypatch):
    async with TestingSessionLocal() as db:
        with pytest.raises(RuntimeError, match="Integration not found: missing-email-id"):
            await run_tool_step(
                {
                    "id": "email",
                    "type": "tool",
                    "tool": "email",
                    "action": "send_email",
                    "integration_id": "missing-email-id",
                    "params": {
                        "to": "recipient@example.com",
                        "subject": "Hello",
                        "body": "Body",
                    },
                },
                {},
                db,
            )


async def test_email_tool_rejects_non_email_provider_integration(client, auth_headers):
    slack = await _create_slack(client, auth_headers, "slack")

    async with TestingSessionLocal() as db:
        with pytest.raises(RuntimeError, match=f"Integration not found: {slack['id']}"):
            await run_tool_step(
                {
                    "id": "email",
                    "type": "tool",
                    "tool": "email",
                    "action": "send_email",
                    "integration_id": slack["id"],
                    "params": {
                        "to": "recipient@example.com",
                        "subject": "Hello",
                        "body": "Body",
                    },
                },
                {},
                db,
            )
