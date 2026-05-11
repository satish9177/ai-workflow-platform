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
from app.llm.normalizer import to_openai_format
from app.llm.types import LLMRequest, LLMResponse, LLMUsage


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise AuthenticationError("OpenAI API key is not configured", provider=self.provider_name)

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=request.model,
                messages=to_openai_format(request.messages),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            message = response.choices[0].message.content or ""
            usage = response.usage
            return LLMResponse(
                content=message,
                model=response.model or request.model,
                provider=self.provider_name,
                usage=LLMUsage(
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                    total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
                ),
                raw=_safe_model_dump(response),
            )
        except Exception as exc:
            raise _map_openai_error(exc) from exc

    def supported_models(self) -> list[str]:
        return ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]


def _safe_model_dump(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _map_openai_error(exc: Exception) -> LLMError:
    message = str(exc)
    lowered = message.lower()
    status_code = _status_code(exc)
    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or status_code == 429:
        return RateLimitError("OpenAI rate limit exceeded", provider="openai", retryable=True)
    if "authentication" in class_name or status_code in {401, 403}:
        return AuthenticationError("OpenAI authentication failed", provider="openai")
    if "notfound" in class_name or status_code == 404:
        return ModelNotFoundError("OpenAI model not found", provider="openai")
    if "connection" in class_name or "timeout" in class_name:
        return ProviderUnavailableError("OpenAI provider unavailable", provider="openai", retryable=True)
    if ("badrequest" in class_name or status_code == 400) and ("context" in lowered or "token" in lowered):
        return ContextLengthError("OpenAI context length exceeded", provider="openai")
    if status_code in {500, 502, 503, 504}:
        return ProviderUnavailableError("OpenAI provider unavailable", provider="openai", retryable=True)
    return LLMError("OpenAI request failed", provider="openai")


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
