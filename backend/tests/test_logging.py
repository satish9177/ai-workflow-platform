import pytest


pytestmark = pytest.mark.asyncio


async def test_health_returns_request_id_header(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


async def test_health_reuses_provided_request_id(client):
    request_id = "test-request-id"

    response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
