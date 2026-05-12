import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def valid_encryption_key(monkeypatch):
    monkeypatch.setattr("app.routers.integrations.settings.encryption_key", "0" * 64)


async def test_integrations_list_includes_slack_and_discord(client, auth_headers):
    response = await client.get("/api/v1/integrations/", headers=auth_headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"slack", "discord"}.issubset(names)


async def test_can_save_slack_credentials(client, auth_headers):
    response = await client.put(
        "/api/v1/integrations/slack",
        headers=auth_headers,
        json={
            "credentials": {"webhook_url": "https://hooks.slack.test/services/test"},
            "config": {},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "name": "slack",
        "is_enabled": True,
        "has_credentials": True,
    }


async def test_can_save_discord_credentials(client, auth_headers):
    response = await client.put(
        "/api/v1/integrations/discord",
        headers=auth_headers,
        json={
            "credentials": {"webhook_url": "https://discord.test/api/webhooks/test"},
            "config": {},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "name": "discord",
        "is_enabled": True,
        "has_credentials": True,
    }
