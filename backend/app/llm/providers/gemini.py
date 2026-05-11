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
from app.llm.normalizer import extract_system, to_gemini_format
from app.llm.types import LLMRequest, LLMResponse, LLMUsage


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"
    default_model = "gemini-1.5-flash"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise AuthenticationError("Gemini API key is not configured", provider=self.provider_name)

        system_prompt, non_system_messages = extract_system(request.messages)

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=request.model,
                system_instruction=system_prompt,
                generation_config={
                    "max_output_tokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            )
            response = await model.generate_content_async(to_gemini_format(non_system_messages))
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            total_tokens = getattr(usage, "total_token_count", prompt_tokens + completion_tokens) if usage else 0
            return LLMResponse(
                content=getattr(response, "text", "") or "",
                model=request.model,
                provider=self.provider_name,
                usage=LLMUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ),
                raw=_safe_response_dict(response),
            )
        except Exception as exc:
            raise _map_gemini_error(exc) from exc

    def supported_models(self) -> list[str]:
        return ["gemini-1.5-flash", "gemini-1.5-pro"]


def _safe_response_dict(value: Any) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def _map_gemini_error(exc: Exception) -> LLMError:
    message = str(exc)
    lowered = message.lower()
    status_code = _status_code(exc)
    class_name = exc.__class__.__name__.lower()
    if "resourceexhausted" in class_name or status_code == 429:
        return RateLimitError("Gemini rate limit exceeded", provider="gemini", retryable=True)
    if "unauthenticated" in class_name or "permissiondenied" in class_name or status_code in {401, 403}:
        return AuthenticationError("Gemini authentication failed", provider="gemini")
    if "notfound" in class_name or status_code == 404:
        return ModelNotFoundError("Gemini model not found", provider="gemini")
    if "serviceunavailable" in class_name or "deadlineexceeded" in class_name or status_code in {500, 502, 503, 504}:
        return ProviderUnavailableError("Gemini provider unavailable", provider="gemini", retryable=True)
    if ("invalidargument" in class_name or status_code == 400) and ("context" in lowered or "token" in lowered):
        return ContextLengthError("Gemini context length exceeded", provider="gemini")
    return LLMError("Gemini request failed", provider="gemini")


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "code", None)
    if callable(status_code):
        status_code = status_code()
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)
