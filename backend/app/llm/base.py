from abc import ABC, abstractmethod

from app.llm.types import LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    provider_name: str
    default_model: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def supported_models(self) -> list[str]:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True
