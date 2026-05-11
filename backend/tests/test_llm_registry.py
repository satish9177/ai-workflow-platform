import pytest

from app.llm.errors import ProviderUnavailableError
from app.llm.providers.mock import MockLLMProvider
from app.llm.registry import LLMRegistry
from app.llm.types import LLMMessage, LLMRequest


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_registry():
    LLMRegistry.clear()
    yield
    LLMRegistry.clear()


def make_request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="user", content="Hello")],
        model="mock-model",
    )


async def test_registry_register_get_available_clear():
    provider = MockLLMProvider()

    LLMRegistry.register(provider)

    assert LLMRegistry.get("mock") is provider
    assert LLMRegistry.available() == ["mock"]

    LLMRegistry.clear()

    assert LLMRegistry.get("mock") is None
    assert LLMRegistry.available() == []


async def test_registry_complete_uses_mock_provider():
    provider = MockLLMProvider()
    provider.set_response("Hello from mock")
    LLMRegistry.register(provider)

    response = await LLMRegistry.complete("mock", make_request())

    assert response.content == "Hello from mock"
    assert response.provider == "mock"
    assert response.model == "mock-model"
    assert provider.call_count == 1
    assert provider.last_request == make_request()


async def test_registry_unknown_provider_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown LLM provider: missing"):
        await LLMRegistry.complete("missing", make_request())


async def test_mock_provider_response_sequence():
    provider = MockLLMProvider()
    provider.set_responses(["first", "second"])

    first = await provider.complete(make_request())
    second = await provider.complete(make_request())
    third = await provider.complete(make_request())

    assert first.content == "first"
    assert second.content == "second"
    assert third.content == "Mock response"
    assert provider.call_count == 3


async def test_mock_provider_error_raising():
    provider = MockLLMProvider()
    provider.set_error(ProviderUnavailableError("Provider unavailable", provider="mock", retryable=True))

    with pytest.raises(ProviderUnavailableError, match="Provider unavailable"):
        await provider.complete(make_request())

    assert provider.call_count == 1
