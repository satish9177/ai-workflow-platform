class LLMError(Exception):
    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        retryable: bool = False,
        status_code: int | None = None,
        model: str | None = None,
    ):
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        self.model = model
        super().__init__(message)


class RateLimitError(LLMError):
    pass


class AuthenticationError(LLMError):
    pass


class ContextLengthError(LLMError):
    pass


class ProviderUnavailableError(LLMError):
    pass


class ModelNotFoundError(LLMError):
    pass
