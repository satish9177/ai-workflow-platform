import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

from conftest import test_engine


pytestmark = pytest.mark.asyncio


def tool_step(step_id: str = "notify") -> dict:
    return {
        "id": step_id,
        "type": "tool",
        "tool": "http_request",
        "action": "execute",
        "params": {"method": "GET", "url": "https://example.com"},
    }


async def create_workflow(client, auth_headers, steps):
    return await client.post(
        "/api/v1/workflows/",
        json={
            "name": "Grouped workflow",
            "trigger_type": "manual",
            "steps": steps,
        },
        headers=auth_headers,
    )


async def table_columns(table_name: str) -> set[str]:
    async with test_engine.begin() as conn:
        return await conn.run_sync(
            lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns(table_name)}
        )


async def test_parallel_group_step_validates(client, auth_headers):
    response = await create_workflow(
        client,
        auth_headers,
        [
            {
                "id": "notify_everyone",
                "type": "parallel_group",
                "fail_fast": True,
                "concurrency_limit": 2,
                "steps": [tool_step("slack"), tool_step("discord")],
            }
        ],
    )

    assert response.status_code == 201
    assert response.json()["steps"][0]["type"] == "parallel_group"


async def test_parallel_group_rejects_empty_steps(client, auth_headers):
    response = await create_workflow(
        client,
        auth_headers,
        [{"id": "empty_group", "type": "parallel_group", "steps": []}],
    )

    assert response.status_code == 422
    assert "parallel_group steps must not be empty" in response.text


async def test_parallel_group_rejects_invalid_concurrency_limit(client, auth_headers):
    response = await create_workflow(
        client,
        auth_headers,
        [{"id": "bad_group", "type": "parallel_group", "concurrency_limit": 0, "steps": [tool_step()]}],
    )

    assert response.status_code == 422
    assert "concurrency_limit must be greater than 0" in response.text


async def test_foreach_step_validates(client, auth_headers):
    response = await create_workflow(
        client,
        auth_headers,
        [
            {
                "id": "email_customers",
                "type": "foreach",
                "items": "{{ trigger_data.body.customers }}",
                "item_variable": "customer",
                "index_variable": "index",
                "concurrency_limit": 3,
                "fail_fast": False,
                "step": tool_step("send_email"),
            }
        ],
    )

    assert response.status_code == 201
    assert response.json()["steps"][0]["type"] == "foreach"


async def test_foreach_rejects_nested_foreach_depth_greater_than_one(client, auth_headers):
    response = await create_workflow(
        client,
        auth_headers,
        [
            {
                "id": "outer",
                "type": "foreach",
                "items": [1, 2],
                "item_variable": "item",
                "step": {
                    "id": "inner",
                    "type": "foreach",
                    "items": [3, 4],
                    "item_variable": "inner_item",
                    "step": tool_step("notify_inner"),
                },
            }
        ],
    )

    assert response.status_code == 422
    assert "nested foreach depth greater than 1 is not supported" in response.text


async def test_existing_linear_workflow_still_validates(client, auth_headers, sample_workflow):
    response = await client.post("/api/v1/workflows/", json=sample_workflow, headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["steps"] == sample_workflow["steps"]


async def test_phase0_model_metadata_contains_branch_foundation_columns():
    branch_columns = await table_columns("branch_executions")
    run_columns = await table_columns("runs")
    step_execution_columns = await table_columns("step_executions")

    assert {
        "run_id",
        "step_key",
        "branch_type",
        "total_branches",
        "completed_branches",
        "failed_branches",
        "cancelled_branches",
        "merge_triggered",
        "fail_fast",
        "fail_fast_triggered",
        "foreach_items",
        "merged_context",
    }.issubset(branch_columns)
    assert "current_branch_depth" in run_columns
    assert {
        "branch_execution_id",
        "foreach_index",
        "foreach_item",
        "branch_key",
    }.issubset(step_execution_columns)


async def test_phase0_migration_extends_current_alembic_head():
    migration_path = Path("alembic/versions/c6e8a41f0b23_parallel_foreach_foundation.py")
    spec = importlib.util.spec_from_file_location("parallel_foreach_foundation", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "b4f83c9a2d11"
