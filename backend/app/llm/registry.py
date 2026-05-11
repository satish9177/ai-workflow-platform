import structlog

from app.llm.base import BaseLLMProvider
from app.llm.types import LLMRequest, LLMResponse


logger = structlog.get_logger(__name__)


class LLMRegistry:
    _providers: dict[str, BaseLLMProvider] = {}

    @classmethod
    def register(cls, provider: BaseLLMProvider) -> None:
        cls._providers[provider.provider_name] = provider

    @classmethod
    def get(cls, provider_name: str) -> BaseLLMProvider | None:
        return cls._providers.get(provider_name)

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._providers.keys())

    @classmethod
    def clear(cls) -> None:
        cls._providers.clear()

    @classmethod
    async def complete(cls, provider_name: str, request: LLMRequest) -> LLMResponse:
        provider = cls.get(provider_name)
        if provider is None:
            raise ValueError(f"Unknown LLM provider: {provider_name}")

        logger.info(
            "llm.request.started",
            provider=provider_name,
            model=request.model,
            message_count=len(request.messages),
        )
        response = await provider.complete(request)
        logger.info(
            "llm.request.completed",
            provider=provider_name,
            model=response.model,
        )
        return response


def register_configured_providers(settings, reset: bool = False) -> None:
    from app.llm.providers.anthropic import AnthropicProvider
    from app.llm.providers.gemini import GeminiProvider
    from app.llm.providers.openai import OpenAIProvider

    if reset:
        LLMRegistry.clear()

    LLMRegistry.register(OpenAIProvider(settings.openai_api_key))
    LLMRegistry.register(AnthropicProvider(settings.anthropic_api_key))
    LLMRegistry.register(GeminiProvider(settings.gemini_api_key))
