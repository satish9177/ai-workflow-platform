import pytest


pytestmark = pytest.mark.asyncio


async def test_register(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["email"] == "user@example.com"


async def test_register_duplicate_email(client):
    payload = {"email": "user@example.com", "password": "password123"}
    await client.post("/api/v1/auth/register", json=payload)

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409


async def test_login_success(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_wrong_password(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401


async def test_me_authenticated(client, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"


async def test_me_unauthenticated(client):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 403
