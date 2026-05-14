import pytest

from app.queue import jobs


pytestmark = pytest.mark.asyncio


class ClosingFailureSession:
    rollback_called = False

    async def close(self) -> None:
        raise TimeoutError("Timed out closing connection after 1")

    async def rollback(self) -> None:
        self.rollback_called = True


async def test_foreach_job_does_not_fail_when_session_close_times_out(monkeypatch):
    called = False

    async def fake_execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db):
        nonlocal called
        called = True

    monkeypatch.setattr(jobs, "AsyncSessionLocal", ClosingFailureSession)
    monkeypatch.setattr(jobs, "execute_foreach_iteration", fake_execute_foreach_iteration)

    await jobs.execute_foreach_iteration_job({}, "branch-1", "run-1", "approval_loop", 2)

    assert called is True


async def test_foreach_job_preserves_business_error_when_session_close_also_fails(monkeypatch):
    async def fake_execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db):
        raise RuntimeError("business failure")

    monkeypatch.setattr(jobs, "AsyncSessionLocal", ClosingFailureSession)
    monkeypatch.setattr(jobs, "execute_foreach_iteration", fake_execute_foreach_iteration)

    with pytest.raises(RuntimeError, match="business failure"):
        await jobs.execute_foreach_iteration_job({}, "branch-1", "run-1", "approval_loop", 2)
