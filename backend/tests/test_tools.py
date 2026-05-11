import pytest

from app.tools.http_request import HttpRequestTool
from app.tools.registry import ToolRegistry
from app.tools.smtp_email import SmtpEmailTool
from app.tools.whatsapp import WhatsAppTool


pytestmark = pytest.mark.asyncio


class FakeResponse:
    is_success = True
    status_code = 200
    headers = {"content-type": "application/json"}
    text = '{"ok": true}'

    def json(self):
        return {"ok": True}


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.request_args = None
        self.request_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def request(self, *args, **kwargs):
        self.request_args = args
        self.request_kwargs = kwargs
        return FakeResponse()


async def test_tool_registry_has_expected_tools():
    names = ToolRegistry.all_names()

    assert "http_request" in names
    assert "smtp_email" in names
    assert "whatsapp" in names


async def test_tool_registry_get_nonexistent_returns_none():
    assert ToolRegistry.get("nonexistent") is None


async def test_http_request_missing_url_returns_failure():
    result = await HttpRequestTool().execute("execute", {}, {})

    assert result.success is False
    assert "url" in result.error


async def test_http_request_success_uses_mocked_async_client(monkeypatch):
    monkeypatch.setattr("app.tools.http_request.httpx.AsyncClient", FakeAsyncClient)

    result = await HttpRequestTool().execute(
        "execute",
        {"url": "https://example.test/api", "method": "post", "body": {"hello": "world"}},
        {},
    )

    assert result.success is True
    assert result.data == {"ok": True}
    assert result.metadata["status_code"] == 200


async def test_whatsapp_missing_credentials_returns_failure():
    result = await WhatsAppTool().execute(
        "send_message",
        {"to": "+1 555 0100", "body": "Hello"},
        {},
    )

    assert result.success is False
    assert "credentials" in result.error


async def test_smtp_email_missing_to_returns_failure():
    result = await SmtpEmailTool().execute(
        "send",
        {"subject": "Hello", "body": "Body"},
        {},
    )

    assert result.success is False
    assert "email parameters" in result.error
