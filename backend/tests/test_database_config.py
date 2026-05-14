from app.config import settings
from app.database import _engine_kwargs, engine
from app.queue.settings import WorkerSettings


def test_async_engine_hardening_config_applies():
    kwargs = _engine_kwargs()

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == settings.db_pool_recycle == 1800
    assert kwargs["pool_size"] == settings.db_pool_size == 25
    assert kwargs["max_overflow"] == settings.db_max_overflow == 10
    assert kwargs["pool_timeout"] == settings.db_pool_timeout == 30


def test_asyncpg_connect_args_are_configured():
    connect_args = _engine_kwargs()["connect_args"]

    assert connect_args["command_timeout"] == settings.db_command_timeout == 30
    assert connect_args["timeout"] == settings.db_connect_timeout == 10
    assert connect_args["server_settings"] == {
        "statement_timeout": "60000",
        "idle_in_transaction_session_timeout": "30000",
    }


def test_engine_pool_matches_settings():
    pool = engine.sync_engine.pool

    assert pool._pre_ping is True
    assert pool._recycle == settings.db_pool_recycle
    assert pool.size() == settings.db_pool_size
    assert pool._max_overflow == settings.db_max_overflow
    assert pool._timeout == settings.db_pool_timeout


def test_arq_max_jobs_uses_settings_with_pool_headroom():
    assert WorkerSettings.max_jobs == settings.arq_max_jobs == 10
    assert settings.db_pool_size >= settings.arq_max_jobs
