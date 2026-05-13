from dataclasses import dataclass

from app.llm.errors import AuthenticationError, LLMError, ModelNotFoundError, ProviderUnavailableError, RateLimitError


@dataclass
class ProviderExecutionError(Exception):
    provider: str
    model: str | None
    error_type: str
    message: str
    retryable: bool
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message

    def to_error_details(self) -> dict:
        details = {
            "type": self.error_type,
            "provider": self.provider,
            "model": self.model,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.status_code is not None:
            details["status_code"] = self.status_code
        return details


def is_retryable_provider_error(error: Exception) -> bool:
    normalized = normalize_provider_error(error)
    return normalized.retryable if normalized is not None else False


def normalize_provider_error(error: Exception, provider: str = "unknown", model: str | None = None) -> ProviderExecutionError | None:
    if isinstance(error, ProviderExecutionError):
        return error

    message = str(error) or error.__class__.__name__
    lowered = message.lower()
    status_code = _status_code(error)

    if isinstance(error, LLMError):
        provider = error.provider or provider
        model = error.model or model
        status_code = error.status_code if error.status_code is not None else status_code
        return ProviderExecutionError(
            provider=provider,
            model=model,
            error_type=_llm_error_type(error, status_code, lowered),
            message=message,
            retryable=error.retryable,
            status_code=status_code,
        )

    if status_code == 429 or "rate limit" in lowered or "rate-limit" in lowered or "rate limit exceeded" in lowered:
        return ProviderExecutionError(provider, model, "ProviderRateLimitError", message, True, status_code or 429)
    if "timeout" in lowered or "timed out" in lowered:
        return ProviderExecutionError(provider, model, "ProviderTimeoutError", message, True, status_code)
    if "temporary" in lowered and ("network" in lowered or "provider" in lowered):
        return ProviderExecutionError(provider, model, "ProviderTemporaryNetworkError", message, True, status_code)
    if status_code is not None and status_code >= 500:
        return ProviderExecutionError(provider, model, "ProviderUnavailableError", message, True, status_code)
    if status_code is not None and 400 <= status_code < 500:
        return ProviderExecutionError(provider, model, "ProviderRequestError", message, False, status_code)
    if "invalid api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return ProviderExecutionError(provider, model, "ProviderAuthenticationError", message, False, status_code)
    if "unsupported model" in lowered or "model not found" in lowered:
        return ProviderExecutionError(provider, model, "ProviderModelNotFoundError", message, False, status_code)
    if "malformed request" in lowered or "validation error" in lowered:
        return ProviderExecutionError(provider, model, "ProviderRequestError", message, False, status_code)

    return None


def _llm_error_type(error: LLMError, status_code: int | None, lowered: str) -> str:
    if isinstance(error, RateLimitError) or status_code == 429 or "rate limit" in lowered:
        return "ProviderRateLimitError"
    if isinstance(error, AuthenticationError):
        return "ProviderAuthenticationError"
    if isinstance(error, ModelNotFoundError):
        return "ProviderModelNotFoundError"
    if isinstance(error, ProviderUnavailableError):
        return "ProviderUnavailableError"
    return error.__class__.__name__


def _status_code(error: Exception) -> int | None:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    code = getattr(error, "code", None)
    if callable(code):
        code = code()
    if isinstance(code, int):
        return code
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None
