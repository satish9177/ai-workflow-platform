from app.llm.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    provider_name = "mock"
    default_model = "mock-model"

    def __init__(self) -> None:
        self._response = "Mock response"
        self._responses: list[str] = []
        self._error: Exception | None = None
        self._call_count = 0
        self._last_request: LLMRequest | None = None

    def set_response(self, content: str) -> None:
        self._response = content
        self._responses = []

    def set_responses(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def set_error(self, error: Exception) -> None:
        self._error = error

    def reset(self) -> None:
        self._response = "Mock response"
        self._responses = []
        self._error = None
        self._call_count = 0
        self._last_request = None

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_request(self) -> LLMRequest | None:
        return self._last_request

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self._call_count += 1
        self._last_request = request

        if self._error is not None:
            raise self._error

        content = self._responses.pop(0) if self._responses else self._response
        return LLMResponse(
            content=content,
            model=request.model,
            provider=self.provider_name,
        )

    def supported_models(self) -> list[str]:
        return ["mock-model"]
