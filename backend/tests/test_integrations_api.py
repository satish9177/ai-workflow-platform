import pytest

from app.models.workflow import Workflow
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def valid_encryption_key(monkeypatch):
    monkeypatch.setattr("app.routers.integrations.settings.encryption_key", "0" * 64)
    monkeypatch.setattr("app.engine.steps.tool.settings.encryption_key", "0" * 64)


async def _create_integration(client, auth_headers, integration_type="slack", display_name="Slack Workspace"):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": integration_type,
            "display_name": display_name,
            "credentials": {"webhook_url": f"https://{integration_type}.test/webhook"},
            "config": {},
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_integrations_list_includes_slack_and_discord(client, auth_headers):
    response = await client.get("/api/v1/integrations", headers=auth_headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"slack", "discord"}.issubset(names)


async def test_create_multiple_integrations_same_type(client, auth_headers):
    first = await _create_integration(client, auth_headers, "slack", "Engineering Slack")
    second = await _create_integration(client, auth_headers, "slack", "Support Slack")

    assert first["id"] != second["id"]
    assert first["integration_type"] == "slack"
    assert second["integration_type"] == "slack"
    assert first["display_name"] == "Engineering Slack"
    assert second["display_name"] == "Support Slack"


async def test_filter_integrations_by_type(client, auth_headers):
    await _create_integration(client, auth_headers, "slack", "Engineering Slack")
    await _create_integration(client, auth_headers, "discord", "Ops Discord")

    response = await client.get("/api/v1/integrations?type=slack", headers=auth_headers)

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["integration_type"] == "slack"


async def test_create_smtp_integration_succeeds(client, auth_headers):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "smtp",
            "display_name": "Gmail SMTP",
            "credentials": {
                "host": "smtp.gmail.com",
                "port": "587",
                "username": "you@gmail.com",
                "password": "app-password",
                "from_email": "you@gmail.com",
            },
            "config": {},
        },
    )

    assert response.status_code == 201
    assert response.json()["integration_type"] == "smtp"


async def test_filter_integrations_by_smtp_type(client, auth_headers):
    await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "smtp",
            "display_name": "Gmail SMTP",
            "credentials": {
                "host": "smtp.gmail.com",
                "port": "587",
                "username": "you@gmail.com",
                "password": "app-password",
                "from_email": "you@gmail.com",
            },
            "config": {},
        },
    )
    await _create_integration(client, auth_headers, "slack", "Engineering Slack")

    response = await client.get("/api/v1/integrations?type=smtp", headers=auth_headers)

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["integration_type"] == "smtp"


async def test_credentials_set_and_credentials_never_returned(client, auth_headers):
    integration = await _create_integration(client, auth_headers, "slack", "Engineering Slack")

    assert integration["credentials_set"] is True
    assert integration["has_credentials"] is True
    assert "credentials" not in integration


async def test_get_integration_by_id(client, auth_headers):
    integration = await _create_integration(client, auth_headers, "slack", "Engineering Slack")

    response = await client.get(f"/api/v1/integrations/{integration['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == integration["id"]
    assert "credentials" not in response.json()


async def test_can_save_slack_credentials_with_legacy_put(client, auth_headers):
    response = await client.put(
        "/api/v1/integrations/slack",
        headers=auth_headers,
        json={
            "credentials": {"webhook_url": "https://hooks.slack.test/services/test"},
            "config": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "slack"
    assert body["integration_type"] == "slack"
    assert body["credentials_set"] is True


async def test_can_save_discord_credentials_with_legacy_put(client, auth_headers):
    response = await client.put(
        "/api/v1/integrations/discord",
        headers=auth_headers,
        json={
            "credentials": {"webhook_url": "https://discord.test/api/webhooks/test"},
            "config": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "discord"
    assert body["integration_type"] == "discord"
    assert body["credentials_set"] is True


async def test_patch_updates_display_name_and_credentials(client, auth_headers):
    integration = await _create_integration(client, auth_headers, "slack", "Old Name")

    response = await client.patch(
        f"/api/v1/integrations/{integration['id']}",
        headers=auth_headers,
        json={
            "display_name": "New Name",
            "credentials": {"webhook_url": "https://hooks.slack.test/services/new"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "New Name"
    assert body["credentials_set"] is True
    assert "credentials" not in body


async def test_delete_referenced_integration_returns_409(client, auth_headers):
    integration = await _create_integration(client, auth_headers, "slack", "Referenced Slack")
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Uses integration",
            steps=[
                {
                    "id": "send",
                    "type": "tool",
                    "tool": "slack",
                    "action": "send_message",
                    "integration_id": integration["id"],
                    "params": {"text": "hello"},
                }
            ],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()

    response = await client.delete(f"/api/v1/integrations/{integration['id']}", headers=auth_headers)

    assert response.status_code == 409


async def test_successful_slack_test_persists_status(client, auth_headers, monkeypatch):
    async def post(url, payload, headers=None, timeout=15):
        return {}

    monkeypatch.setattr("app.tools.integrations.slack._post", post)
    integration = await _create_integration(client, auth_headers, "slack", "Engineering Slack")

    response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "connected",
        "message": "Connection successful",
    }

    refreshed = await client.get(f"/api/v1/integrations/{integration['id']}", headers=auth_headers)
    body = refreshed.json()
    assert body["status"] == "connected"
    assert body["last_tested_at"] is not None
    assert body["last_error"] is None


async def test_failed_slack_test_persists_last_error(client, auth_headers, monkeypatch):
    async def post(url, payload, headers=None, timeout=15):
        raise RuntimeError("HTTP 400: bad request")

    monkeypatch.setattr("app.tools.integrations.slack._post", post)
    integration = await _create_integration(client, auth_headers, "slack", "Engineering Slack")

    response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["status"] == "failed"
    assert "HTTP 400" in response.json()["message"]

    refreshed = await client.get(f"/api/v1/integrations/{integration['id']}", headers=auth_headers)
    body = refreshed.json()
    assert body["status"] == "failed"
    assert "HTTP 400" in body["last_error"]


async def test_successful_discord_test(client, auth_headers, monkeypatch):
    async def post(url, payload, headers=None, timeout=15):
        return {}

    monkeypatch.setattr("app.tools.integrations.discord._post", post)
    integration = await _create_integration(client, auth_headers, "discord", "Ops Discord")

    response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["status"] == "connected"


async def test_test_invalid_integration_id(client, auth_headers):
    response = await client.post("/api/v1/integrations/not-a-real-id/test", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Integration not found"


async def test_test_missing_credentials(client, auth_headers):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "slack",
            "display_name": "Slack without credentials",
            "credentials": {},
            "config": {},
        },
    )
    integration = response.json()

    test_response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert test_response.status_code == 200
    assert test_response.json() == {
        "success": False,
        "status": "failed",
        "message": "Missing credentials",
    }


async def test_test_invalid_webhook_url(client, auth_headers):
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "slack",
            "display_name": "Bad Slack",
            "credentials": {"webhook_url": "not-a-url"},
            "config": {},
        },
    )
    integration = response.json()

    test_response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert test_response.status_code == 200
    assert test_response.json()["success"] is False
    assert test_response.json()["status"] == "failed"
    assert test_response.json()["message"] == "Invalid webhook URL"
