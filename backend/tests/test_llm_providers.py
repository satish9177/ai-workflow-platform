import pytest

from app.llm.errors import AuthenticationError
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.registry import LLMRegistry, register_configured_providers
from app.llm.types import LLMMessage, LLMRequest


pytestmark = pytest.mark.asyncio


class FakeSettings:
    openai_api_key = ""
    anthropic_api_key = ""
    gemini_api_key = ""


def make_request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="user", content="Hello")],
        model="test-model",
    )


@pytest.fixture(autouse=True)
def clear_registry():
    LLMRegistry.clear()
    yield
    LLMRegistry.clear()


async def test_openai_provider_complete_raises_authentication_error_without_key():
    provider = OpenAIProvider("")

    with pytest.raises(AuthenticationError) as exc:
        await provider.complete(make_request())

    assert exc.value.provider == "openai"


async def test_anthropic_provider_complete_raises_authentication_error_without_key():
    provider = AnthropicProvider("")

    with pytest.raises(AuthenticationError) as exc:
        await provider.complete(make_request())

    assert exc.value.provider == "anthropic"


async def test_gemini_provider_complete_raises_authentication_error_without_key():
    provider = GeminiProvider("")

    with pytest.raises(AuthenticationError) as exc:
        await provider.complete(make_request())

    assert exc.value.provider == "gemini"


async def test_supported_models_are_non_empty_for_all_providers():
    providers = [OpenAIProvider(""), AnthropicProvider(""), GeminiProvider("")]

    for provider in providers:
        assert provider.supported_models()


async def test_register_configured_providers_registers_without_real_keys():
    register_configured_providers(FakeSettings(), reset=True)

    assert set(LLMRegistry.available()) == {"openai", "anthropic", "gemini"}
    assert isinstance(LLMRegistry.get("openai"), OpenAIProvider)
    assert isinstance(LLMRegistry.get("anthropic"), AnthropicProvider)
    assert isinstance(LLMRegistry.get("gemini"), GeminiProvider)


async def test_provider_objects_construct_without_network_calls():
    OpenAIProvider("")
    AnthropicProvider("")
    GeminiProvider("")
