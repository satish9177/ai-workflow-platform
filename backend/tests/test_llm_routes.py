import pytest

from app.config import settings
from app.llm.providers.mock import MockLLMProvider
from app.llm.registry import LLMRegistry, register_configured_providers


@pytest.fixture
def mock_llm():
    register_configured_providers(settings, reset=True)
    provider = MockLLMProvider()
    LLMRegistry.register(provider)
    yield provider
    LLMRegistry.clear()


@pytest.mark.asyncio
async def test_list_providers_returns_provider_objects(client, auth_headers, mock_llm):
    response = await client.get("/api/v1/llm/providers", headers=auth_headers)

    assert response.status_code == 200
    providers = response.json()
    assert isinstance(providers, list)
    assert providers
    assert all({"id", "name"} <= set(provider.keys()) for provider in providers)


@pytest.mark.asyncio
async def test_list_providers_includes_mock(client, auth_headers, mock_llm):
    response = await client.get("/api/v1/llm/providers", headers=auth_headers)

    assert response.status_code == 200
    ids = {provider["id"] for provider in response.json()}
    assert "mock" in ids


@pytest.mark.asyncio
async def test_list_providers_names_are_non_empty(client, auth_headers, mock_llm):
    response = await client.get("/api/v1/llm/providers", headers=auth_headers)

    assert response.status_code == 200
    assert all(provider["name"] for provider in response.json())


@pytest.mark.asyncio
async def test_list_mock_models(client, auth_headers, mock_llm):
    response = await client.get("/api/v1/llm/providers/mock/models", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert "mock-model" in payload["models"]


@pytest.mark.asyncio
async def test_list_models_unknown_provider_returns_404(client, auth_headers, mock_llm):
    response = await client.get("/api/v1/llm/providers/bad_name/models", headers=auth_headers)

    assert response.status_code == 404
    assert "bad_name" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_providers_requires_auth(client, mock_llm):
    response = await client.get("/api/v1/llm/providers")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_models_requires_auth(client, mock_llm):
    response = await client.get("/api/v1/llm/providers/mock/models")

    assert response.status_code == 403
