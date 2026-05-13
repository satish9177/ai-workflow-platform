import pytest

from app.tools.integrations.email.smtp import SmtpEmailProvider
from app.tools.integrations.email_tool import run_email_tool


def _credentials() -> dict[str, str]:
    return {
        "host": "smtp.example.com",
        "port": "587",
        "username": "sender@example.com",
        "password": "secret",
        "from_email": "sender@example.com",
        "from_name": "Workflow Bot",
    }


def test_make_html_converts_newlines_to_br_tags():
    provider = SmtpEmailProvider(_credentials())

    assert provider._make_html("hello\nworld") == "<html><body><p>hello<br>world</p></body></html>"


def test_make_html_escapes_html_special_characters():
    provider = SmtpEmailProvider(_credentials())

    assert "&lt;script&gt;" in provider._make_html("<script>")


async def test_run_email_tool_missing_to_raises():
    with pytest.raises(RuntimeError, match="Email 'to' field is required"):
        await run_email_tool("send_email", {"subject": "Hi", "body": "Body"}, _credentials(), "smtp")


async def test_run_email_tool_missing_subject_raises():
    with pytest.raises(RuntimeError, match="Email 'subject' field is required"):
        await run_email_tool("send_email", {"to": "a@example.com", "body": "Body"}, _credentials(), "smtp")


async def test_run_email_tool_missing_body_raises():
    with pytest.raises(RuntimeError, match="Email 'body' field is required"):
        await run_email_tool("send_email", {"to": "a@example.com", "subject": "Hi"}, _credentials(), "smtp")


async def test_run_email_tool_unknown_action_raises():
    with pytest.raises(RuntimeError, match="Unknown email action"):
        await run_email_tool("unknown", {}, _credentials(), "smtp")


async def test_run_email_tool_unsupported_integration_type_raises():
    with pytest.raises(RuntimeError, match="Unsupported email integration type"):
        await run_email_tool("send_email", {"to": "a@example.com", "subject": "Hi", "body": "Body"}, {}, "gmail")


async def test_subject_header_injection_newlines_are_stripped(monkeypatch):
    captured = {}

    async def fake_send(message, **kwargs):
        captured["subject"] = message["Subject"]

    monkeypatch.setattr("app.tools.integrations.email.smtp.aiosmtplib.send", fake_send)
    provider = SmtpEmailProvider(_credentials())

    await provider.send("a@example.com", "Hello\nBcc: evil@example.com", "Body")

    assert "\n" not in captured["subject"]
    assert "\r" not in captured["subject"]


async def test_to_header_injection_newlines_are_stripped(monkeypatch):
    captured = {}

    async def fake_send(message, **kwargs):
        captured["to"] = message["To"]

    monkeypatch.setattr("app.tools.integrations.email.smtp.aiosmtplib.send", fake_send)
    provider = SmtpEmailProvider(_credentials())

    await provider.send("a@example.com\nBcc: evil@example.com", "Hello", "Body")

    assert "\n" not in captured["to"]
    assert "\r" not in captured["to"]


async def test_send_calls_aiosmtplib_with_expected_connection_args(monkeypatch):
    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr("app.tools.integrations.email.smtp.aiosmtplib.send", fake_send)
    provider = SmtpEmailProvider(_credentials())

    result = await provider.send("a@example.com", "Hello", "Body")

    assert result == {"success": True, "detail": "Email sent to a@example.com"}
    assert captured["kwargs"]["hostname"] == "smtp.example.com"
    assert captured["kwargs"]["port"] == 587
    assert captured["kwargs"]["username"] == "sender@example.com"
    assert captured["kwargs"]["password"] == "secret"
    assert captured["kwargs"]["use_tls"] is True


async def test_smtp_authentication_error_maps_to_readable_runtime_error(monkeypatch):
    class FakeAuthError(Exception):
        pass

    async def fake_send(message, **kwargs):
        raise FakeAuthError("bad auth")

    monkeypatch.setattr("app.tools.integrations.email.smtp.SMTPAuthenticationError", FakeAuthError)
    monkeypatch.setattr("app.tools.integrations.email.smtp.aiosmtplib.send", fake_send)
    provider = SmtpEmailProvider(_credentials())

    with pytest.raises(RuntimeError, match="Email authentication failed"):
        await provider.send("a@example.com", "Hello", "Body")


async def test_smtp_integration_test_endpoint_uses_provider(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.routers.integrations.settings.encryption_key", "0" * 64)

    async def fake_test_connection(self):
        return {"success": True, "message": "Connected successfully"}

    monkeypatch.setattr("app.routers.integrations.SmtpEmailProvider.test_connection", fake_test_connection)
    response = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "integration_type": "smtp",
            "display_name": "Gmail SMTP",
            "credentials": _credentials(),
            "config": {},
        },
    )
    integration = response.json()

    test_response = await client.post(f"/api/v1/integrations/{integration['id']}/test", headers=auth_headers)

    assert test_response.status_code == 200
    assert test_response.json() == {
        "success": True,
        "status": "connected",
        "message": "Connected successfully",
    }
