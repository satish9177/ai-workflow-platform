from collections.abc import AsyncGenerator
from time import monotonic

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


logger = structlog.get_logger(__name__)


def _engine_kwargs() -> dict:
    return {
        "pool_pre_ping": True,
        "pool_recycle": settings.db_pool_recycle,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "connect_args": {
            "command_timeout": settings.db_command_timeout,
            "timeout": settings.db_connect_timeout,
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "idle_in_transaction_session_timeout": str(
                    settings.db_idle_in_transaction_session_timeout_ms
                ),
            },
        },
        "echo": False,
    }


engine = create_async_engine(settings.database_url, **_engine_kwargs())


@event.listens_for(engine.sync_engine, "checkout")
def _log_connection_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
    connection_record.info["checked_out_at"] = monotonic()
    logger.debug("db.connection.checked_out", connection_id=id(dbapi_connection))


@event.listens_for(engine.sync_engine, "checkin")
def _log_connection_checkin(dbapi_connection, connection_record) -> None:
    checked_out_at = connection_record.info.pop("checked_out_at", None)
    if checked_out_at is None:
        logger.debug("db.connection.checked_in", connection_id=id(dbapi_connection))
        return

    held_seconds = monotonic() - checked_out_at
    log_context = {
        "connection_id": id(dbapi_connection),
        "held_ms": round(held_seconds * 1000, 2),
    }
    if held_seconds > settings.db_connection_hold_warn_seconds:
        logger.warning("db.connection.held_too_long", **log_context)
    else:
        logger.debug("db.connection.checked_in", **log_context)


@event.listens_for(engine.sync_engine, "invalidate")
def _log_connection_invalidate(dbapi_connection, connection_record, exception) -> None:
    logger.warning(
        "db.connection.invalidated",
        connection_id=id(dbapi_connection),
        error=str(exception) if exception else None,
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
