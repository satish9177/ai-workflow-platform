from typing import Any

from app.llm.base import BaseLLMProvider
from app.llm.errors import (
    AuthenticationError,
    ContextLengthError,
    LLMError,
    ModelNotFoundError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.llm.normalizer import extract_system, to_anthropic_format
from app.llm.types import LLMRequest, LLMResponse, LLMUsage


class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"
    default_model = "claude-3-5-sonnet-latest"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise AuthenticationError("Anthropic API key is not configured", provider=self.provider_name)

        system_prompt, non_system_messages = extract_system(request.messages)
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": to_anthropic_format(non_system_messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self.api_key)
            response = await client.messages.create(**kwargs)
            content = "".join(
                getattr(block, "text", "")
                for block in getattr(response, "content", [])
                if getattr(block, "type", "text") == "text"
            )
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
            completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0
            return LLMResponse(
                content=content,
                model=getattr(response, "model", request.model),
                provider=self.provider_name,
                usage=LLMUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
                raw=_safe_model_dump(response),
            )
        except Exception as exc:
            raise _map_anthropic_error(exc) from exc

    def supported_models(self) -> list[str]:
        return ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"]


def _safe_model_dump(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _map_anthropic_error(exc: Exception) -> LLMError:
    message = str(exc)
    lowered = message.lower()
    status_code = _status_code(exc)
    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or status_code == 429:
        return RateLimitError("Anthropic rate limit exceeded", provider="anthropic", retryable=True)
    if "authentication" in class_name or "permission" in class_name or status_code in {401, 403}:
        return AuthenticationError("Anthropic authentication failed", provider="anthropic")
    if "notfound" in class_name or status_code == 404:
        return ModelNotFoundError("Anthropic model not found", provider="anthropic")
    if "connection" in class_name or "timeout" in class_name:
        return ProviderUnavailableError("Anthropic provider unavailable", provider="anthropic", retryable=True)
    if ("badrequest" in class_name or status_code == 400) and ("context" in lowered or "token" in lowered):
        return ContextLengthError("Anthropic context length exceeded", provider="anthropic")
    if status_code in {500, 502, 503, 504}:
        return ProviderUnavailableError("Anthropic provider unavailable", provider="anthropic", retryable=True)
    return LLMError("Anthropic request failed", provider="anthropic")


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
