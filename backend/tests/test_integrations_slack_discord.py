from unittest.mock import AsyncMock

import httpx
import pytest

from app.tools.integrations import _http
from app.tools.integrations.discord import DiscordTool
from app.tools.integrations.slack import SlackTool
from app.tools.registry import ToolRegistry


pytestmark = pytest.mark.asyncio


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "", json_data: dict | None = None, json_error: bool = False):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._json_data


class FakeAsyncClient:
    response = FakeResponse()
    error: Exception | None = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


async def test_post_success_json_response(monkeypatch):
    FakeAsyncClient.response = FakeResponse(json_data={"ok": True})
    FakeAsyncClient.error = None
    monkeypatch.setattr("app.tools.integrations._http.httpx.AsyncClient", FakeAsyncClient)

    result = await _http._post("https://example.test/webhook", {"hello": "world"})

    assert result == {"ok": True}


async def test_post_success_non_json_response(monkeypatch):
    FakeAsyncClient.response = FakeResponse(text="ok", json_error=True)
    FakeAsyncClient.error = None
    monkeypatch.setattr("app.tools.integrations._http.httpx.AsyncClient", FakeAsyncClient)

    result = await _http._post("https://example.test/webhook", {"hello": "world"})

    assert result == {}


async def test_post_http_error(monkeypatch):
    FakeAsyncClient.response = FakeResponse(status_code=400, text="bad request")
    FakeAsyncClient.error = None
    monkeypatch.setattr("app.tools.integrations._http.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        await _http._post("https://example.test/webhook", {"hello": "world"})


async def test_post_timeout(monkeypatch):
    FakeAsyncClient.response = FakeResponse()
    FakeAsyncClient.error = httpx.TimeoutException("timeout")
    monkeypatch.setattr("app.tools.integrations._http.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(RuntimeError, match="Request timed out"):
        await _http._post("https://example.test/webhook", {"hello": "world"}, timeout=3)


async def test_post_missing_url():
    with pytest.raises(RuntimeError, match="url is required"):
        await _http._post("", {"hello": "world"})


async def test_slack_send_message_success(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.slack._post", post)

    result = await SlackTool().execute(
        "send_message",
        {"text": "Hello"},
        {"webhook_url": "https://hooks.slack.test"},
    )

    assert result.success is True
    assert result.data == {"sent": True}


async def test_slack_payload_contains_text(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.slack._post", post)

    await SlackTool().execute(
        "send_message",
        {"text": "Hello Slack"},
        {"webhook_url": "https://hooks.slack.test"},
    )

    post.assert_awaited_once_with("https://hooks.slack.test", {"text": "Hello Slack"})


async def test_slack_optional_username_and_icon(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.slack._post", post)

    await SlackTool().execute(
        "send_message",
        {"text": "Hello", "username": "Workflow Bot", "icon_emoji": ":robot_face:"},
        {"webhook_url": "https://hooks.slack.test"},
    )

    post.assert_awaited_once_with(
        "https://hooks.slack.test",
        {"text": "Hello", "username": "Workflow Bot", "icon_emoji": ":robot_face:"},
    )


async def test_slack_missing_webhook_url():
    result = await SlackTool().execute("send_message", {"text": "Hello"}, {})

    assert result.success is False
    assert "webhook_url" in result.error


async def test_slack_missing_text():
    result = await SlackTool().execute(
        "send_message",
        {"text": ""},
        {"webhook_url": "https://hooks.slack.test"},
    )

    assert result.success is False
    assert "text is required" in result.error


async def test_slack_unknown_action():
    result = await SlackTool().execute(
        "unknown",
        {"text": "Hello"},
        {"webhook_url": "https://hooks.slack.test"},
    )

    assert result.success is False


async def test_slack_http_error_propagates(monkeypatch):
    post = AsyncMock(side_effect=RuntimeError("HTTP 400: bad request"))
    monkeypatch.setattr("app.tools.integrations.slack._post", post)

    result = await SlackTool().execute(
        "send_message",
        {"text": "Hello"},
        {"webhook_url": "https://hooks.slack.test"},
    )

    assert result.success is False
    assert result.error == "HTTP 400: bad request"


async def test_discord_send_message_success(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.discord._post", post)

    result = await DiscordTool().execute(
        "send_message",
        {"text": "Hello"},
        {"webhook_url": "https://discord.test/webhook"},
    )

    assert result.success is True
    assert result.data == {"sent": True}


async def test_discord_payload_uses_content_not_text(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.discord._post", post)

    await DiscordTool().execute(
        "send_message",
        {"text": "Hello Discord"},
        {"webhook_url": "https://discord.test/webhook"},
    )

    payload = post.await_args.args[1]
    assert payload == {"content": "Hello Discord"}
    assert "text" not in payload


async def test_discord_optional_username(monkeypatch):
    post = AsyncMock(return_value={})
    monkeypatch.setattr("app.tools.integrations.discord._post", post)

    await DiscordTool().execute(
        "send_message",
        {"text": "Hello", "username": "Workflow Bot"},
        {"webhook_url": "https://discord.test/webhook"},
    )

    post.assert_awaited_once_with(
        "https://discord.test/webhook",
        {"content": "Hello", "username": "Workflow Bot"},
    )


async def test_discord_missing_webhook_url():
    result = await DiscordTool().execute("send_message", {"text": "Hello"}, {})

    assert result.success is False
    assert "webhook_url" in result.error


async def test_discord_missing_text():
    result = await DiscordTool().execute(
        "send_message",
        {},
        {"webhook_url": "https://discord.test/webhook"},
    )

    assert result.success is False
    assert "text is required" in result.error


async def test_discord_unknown_action():
    result = await DiscordTool().execute(
        "unknown",
        {"text": "Hello"},
        {"webhook_url": "https://discord.test/webhook"},
    )

    assert result.success is False


async def test_discord_http_error_propagates(monkeypatch):
    post = AsyncMock(side_effect=RuntimeError("HTTP 400: bad request"))
    monkeypatch.setattr("app.tools.integrations.discord._post", post)

    result = await DiscordTool().execute(
        "send_message",
        {"text": "Hello"},
        {"webhook_url": "https://discord.test/webhook"},
    )

    assert result.success is False
    assert result.error == "HTTP 400: bad request"


async def test_registry_contains_slack_and_discord():
    names = ToolRegistry.all_names()

    assert "slack" in names
    assert "discord" in names
    assert ToolRegistry.get("slack").display_name == "Slack"
    assert ToolRegistry.get("discord").display_name == "Discord"
