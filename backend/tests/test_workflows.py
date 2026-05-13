import pytest

from app.routers import runs as runs_router
from app.routers import workflows as workflows_router


pytestmark = pytest.mark.asyncio


class FakeQueue:
    async def enqueue_job(self, name, run_id):
        return {"name": name, "run_id": run_id}

    async def close(self):
        return None


async def fake_create_pool(*args, **kwargs):
    return FakeQueue()


@pytest.fixture(autouse=True)
def mock_arq(monkeypatch):
    monkeypatch.setattr(workflows_router, "create_pool", fake_create_pool)
    monkeypatch.setattr(runs_router, "create_pool", fake_create_pool)


async def create_workflow(client, auth_headers, payload):
    return await client.post("/api/v1/workflows/", json=payload, headers=auth_headers)


async def trigger_run(client, auth_headers, workflow_id):
    return await client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        json={"trigger_data": {"source": "test"}},
        headers=auth_headers,
    )


async def test_create_workflow(client, auth_headers, sample_workflow):
    response = await create_workflow(client, auth_headers, sample_workflow)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_workflow["name"]
    assert data["steps"] == sample_workflow["steps"]


async def test_create_workflow_step_missing_id_returns_422(client, auth_headers, sample_workflow):
    payload = {
        **sample_workflow,
        "steps": [{"type": "tool", "tool": "http_request", "action": "execute", "params": {"url": "https://example.test"}}],
    }

    response = await create_workflow(client, auth_headers, payload)

    assert response.status_code == 422
    assert "id is required" in response.text


async def test_create_workflow_invalid_step_type_returns_422(client, auth_headers, sample_workflow):
    payload = {
        **sample_workflow,
        "steps": [{"id": "bad", "type": "http_request", "config": {"url": "https://example.test"}}],
    }

    response = await create_workflow(client, auth_headers, payload)

    assert response.status_code == 422
    assert "type must be one of" in response.text


async def test_list_workflows(client, auth_headers, sample_workflow):
    await create_workflow(client, auth_headers, {**sample_workflow, "name": "First"})
    await create_workflow(client, auth_headers, {**sample_workflow, "name": "Second"})

    response = await client.get("/api/v1/workflows/", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_get_workflow(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["steps"] == sample_workflow["steps"]


async def test_update_workflow(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"name": "Updated workflow"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated workflow"


async def test_update_workflow_cron_valid_expression_succeeds(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"trigger_type": "cron", "trigger_config": {"cron_expression": "0 9 * * 1"}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["trigger_type"] == "cron"
    assert response.json()["trigger_config"]["cron_expression"] == "0 9 * * 1"
    assert response.json()["trigger_config"]["cron"] == "0 9 * * 1"

    refetch = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)

    assert refetch.status_code == 200
    assert refetch.json()["trigger_config"]["cron_expression"] == "0 9 * * 1"
    assert refetch.json()["trigger_config"]["cron"] == "0 9 * * 1"


async def test_update_workflow_cron_invalid_expression_returns_422(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"trigger_type": "cron", "trigger_config": {"cron_expression": "not a cron"}},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid cron expression"


async def test_update_workflow_cron_missing_expression_returns_422(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"trigger_type": "cron", "trigger_config": {}},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "cron_expression is required in trigger_config"


async def test_update_workflow_manual_empty_trigger_config_succeeds(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"trigger_type": "manual", "trigger_config": {}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["trigger_type"] == "manual"
    assert response.json()["trigger_config"] == {}


async def test_delete_workflow(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.delete(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)
    refetch = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert refetch.status_code == 404


async def test_trigger_run(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await trigger_run(client, auth_headers, workflow_id)

    assert response.status_code == 202
    assert response.json()["run_id"]
    assert response.json()["status"] == "queued"


async def test_toggle_workflow(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    workflow_id = created.json()["id"]

    response = await client.post(f"/api/v1/workflows/{workflow_id}/toggle", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_get_run(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    run_response = await trigger_run(client, auth_headers, created.json()["id"])
    run_id = run_response.json()["run_id"]

    response = await client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == run_id
    assert response.json()["step_results"] == []


async def test_cancel_run(client, auth_headers, sample_workflow):
    created = await create_workflow(client, auth_headers, sample_workflow)
    run_response = await trigger_run(client, auth_headers, created.json()["id"])
    run_id = run_response.json()["run_id"]

    response = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
