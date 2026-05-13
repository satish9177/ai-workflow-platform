from typing import Any


SENSITIVE_KEYS = {
    "auth",
    "auth_header",
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "bearer_token",
    "token",
    "secret",
    "client_secret",
    "password",
    "credentials",
    "webhook_url",
}
MAX_PREVIEW_STRING_LENGTH = 2000


def sanitize_preview_payload(value: Any, max_string_length: int = MAX_PREVIEW_STRING_LENGTH) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_preview_payload(item, max_string_length=max_string_length)
        return sanitized
    if isinstance(value, list):
        return [sanitize_preview_payload(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, tuple):
        return [sanitize_preview_payload(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, str):
        return _truncate_string(_redact_sensitive_string(value), max_string_length)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS


def _redact_sensitive_string(value: str) -> str:
    lowered = value.lower()
    if "hooks.slack.com/services/" in lowered or "discord.com/api/webhooks/" in lowered:
        return "[redacted-url]"
    return value


def _truncate_string(value: str, max_string_length: int) -> str:
    if len(value) <= max_string_length:
        return value
    return f"{value[:max_string_length]}...[truncated]"
