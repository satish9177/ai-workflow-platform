class LLMError(Exception):
    def __init__(self, message: str, provider: str = "unknown", retryable: bool = False):
        self.provider = provider
        self.retryable = retryable
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
