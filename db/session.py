"""Enterprise Database Session and Async Engine Manager (Prompt R-PERSIST).

Enforces:
- SQLAlchemy 2.0 async engine + asyncpg driver.
- Managed connection pool with deterministic cleanup.
- SET LOCAL app.current_tenant_id and SET LOCAL cloudlens.current_tenant_id per transaction.
- Startup guard enforcing SQL persistence outside development.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("cloudlens.db.session")

DEFAULT_DATABASE_URL = "postgresql+asyncpg://cloudlens:cloudlens_dev_password@localhost:5432/cloudlens"

_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Resolves async PostgreSQL URL from environment or configuration."""
    raw_url = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def get_async_engine() -> AsyncEngine:
    """Returns singleton async SQLAlchemy engine configured with connection pooling."""
    global _async_engine
    if _async_engine is None:
        db_url = get_database_url()
        _async_engine = create_async_engine(
            db_url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_pre_ping=True,
            echo=False,
        )
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns singleton async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _async_session_factory


@asynccontextmanager
async def get_tenant_session(tenant_id: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Yields an AsyncSession with tenant RLS isolation parameter set locally.

    Enforces Prompt R-PERSIST Pattern P4:
    'Every statement filters tenant_id; additionally SET LOCAL app.current_tenant_id per transaction
     so the existing RLS policies enforce isolation even if a WHERE clause is forgotten.'
    """
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            if tenant_id:
                # Use set_config(setting_name, value, is_local=true) for parameterized RLS session context
                await session.execute(
                    text("SELECT set_config('app.current_tenant_id', :tid, true);"),
                    {"tid": tenant_id},
                )
                await session.execute(
                    text("SELECT set_config('cloudlens.current_tenant_id', :tid, true);"),
                    {"tid": tenant_id},
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def verify_persistence_startup_guard(active_repository_type: str = "SQL") -> None:
    """Enforces Pattern P6 Startup Guard.

    'Startup guard: CLOUDLENS_ENV in (staging, production) with ANY InMemory repository selected -> exit non-zero.'
    """
    env = os.getenv("CLOUDLENS_ENV", "").strip().lower()
    if env in ("staging", "production") and active_repository_type.upper() == "INMEMORY":
        logger.critical(
            "FATAL STARTUP GUARD FAILURE: CLOUDLENS_ENV='%s' refuses InMemory repository configuration. "
            "Real PostgreSQL database persistence (SqlRepository) is strictly mandatory in production environments.",
            env,
        )
        sys.exit(1)
