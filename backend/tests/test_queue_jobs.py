import pytest

from app.queue import jobs


pytestmark = pytest.mark.asyncio


class ClosingFailureSession:
    rollback_called = False

    async def close(self) -> None:
        raise TimeoutError("Timed out closing connection after 1")

    async def rollback(self) -> None:
        self.rollback_called = True


class CapturingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, event, **context):
        self.warnings.append((event, context))

    def info(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


async def test_foreach_job_does_not_fail_when_session_close_times_out(monkeypatch):
    called = False
    logger = CapturingLogger()

    async def fake_execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db):
        nonlocal called
        called = True

    monkeypatch.setattr(jobs, "AsyncSessionLocal", ClosingFailureSession)
    monkeypatch.setattr(jobs, "execute_foreach_iteration", fake_execute_foreach_iteration)
    monkeypatch.setattr(jobs, "logger", logger)

    await jobs.execute_foreach_iteration_job({}, "branch-1", "run-1", "approval_loop", 2)

    assert called is True
    assert logger.warnings == [
        (
            "arq.db_session_close_failed",
            {
                "job_name": "execute_foreach_iteration",
                "error": "Timed out closing connection after 1",
                "business_error": False,
                "branch_execution_id": "branch-1",
                "run_id": "run-1",
                "foreach_step_key": "approval_loop",
                "item_index": 2,
            },
        )
    ]


async def test_foreach_job_preserves_business_error_when_session_close_also_fails(monkeypatch):
    logger = CapturingLogger()

    async def fake_execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db):
        raise RuntimeError("business failure")

    monkeypatch.setattr(jobs, "AsyncSessionLocal", ClosingFailureSession)
    monkeypatch.setattr(jobs, "execute_foreach_iteration", fake_execute_foreach_iteration)
    monkeypatch.setattr(jobs, "logger", logger)

    with pytest.raises(RuntimeError, match="business failure"):
        await jobs.execute_foreach_iteration_job({}, "branch-1", "run-1", "approval_loop", 2)

    assert logger.warnings[-1][0] == "arq.db_session_close_failed"
    assert logger.warnings[-1][1]["business_error"] is True
