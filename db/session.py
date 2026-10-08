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
from sqlalchemy.pool import NullPool

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("cloudlens.db.session")

DEFAULT_DATABASE_URL = "postgresql+asyncpg://cloudlens@localhost:5432/cloudlens"

_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Resolves async PostgreSQL URL from environment or configuration."""
    raw_url = os.getenv("DATABASE_URL")
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()
    if not raw_url:
        if env in ("staging", "production"):
            logger.critical(
                "CRITICAL STARTUP FAILURE: CLOUDLENS_ENV is '%s' but DATABASE_URL is not set. Exiting non-zero.",
                env,
            )
            sys.exit(1)
        raw_url = DEFAULT_DATABASE_URL
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def get_async_engine() -> AsyncEngine:
    """Returns singleton async SQLAlchemy engine configured with connection pooling."""
    global _async_engine
    if _async_engine is None:
        db_url = get_database_url()
        is_test_env = (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or os.getenv("CLOUDLENS_TEST_MODE") == "1"
        )
        if is_test_env:
            _async_engine = create_async_engine(
                db_url,
                poolclass=NullPool,
                echo=False,
            )
        else:
            _async_engine = create_async_engine(
                db_url,
                pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
                pool_pre_ping=True,
                echo=False,
            )
    return _async_engine


def reset_async_engine() -> None:
    """Disposes and resets engine singleton for testing."""
    global _async_engine, _async_session_factory
    _async_engine = None
    _async_session_factory = None


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

    Enforces Prompt P03 Items 1 & 5:
    - Sets SET LOCAL app.current_tenant_id per transaction.
    - Sets SET LOCAL cloudlens.current_tenant_id for compatibility.
    - Commits transaction on success, rolls back on exception.
    """
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            tid = tenant_id if tenant_id and tenant_id != "anonymous" else ""
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true);"),
                {"tid": tid},
            )
            await session.execute(
                text("SELECT set_config('cloudlens.current_tenant_id', :tid, true);"),
                {"tid": tid},
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session(
    request: Any = None,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI request dependency yielding an AsyncSession with tenant RLS isolation (Prompt P03 Item 1).

    Enforces:
    - Derives effective tenant ID from request TenantContext or observability contextvar.
    - Sets SET LOCAL app.current_tenant_id for the transaction.
    - Commits on success, rolls back on error, ensures deterministic cleanup.
    """
    effective_tid = None
    if request is not None and hasattr(request, "state") and hasattr(request.state, "tenant_context"):
        tc = request.state.tenant_context
        if tc:
            effective_tid = getattr(tc, "effective_tenant_id", None)

    if not effective_tid:
        from domain.observability import current_tenant_id
        effective_tid = current_tenant_id.get(None)

    async with get_tenant_session(effective_tid) as session:
        yield session


def verify_persistence_startup_guard(active_repository: Any = None) -> None:
    """Enforces Prompt P03 Item 4 Startup Guard outside development.

    Staging and production strictly refuse any InMemory repository configuration.
    """
    env = os.getenv("CLOUDLENS_ENV", "").strip().lower()
    if env in ("staging", "production"):
        if not os.getenv("DATABASE_URL"):
            logger.critical(
                "CRITICAL STARTUP FAILURE: CLOUDLENS_ENV is '%s' but DATABASE_URL is not set. Exiting non-zero.",
                env,
            )
            sys.exit(1)

        from domain.config.repository import get_tenant_settings_repository

        repo = active_repository or get_tenant_settings_repository()
        repo_name = type(repo).__name__
        mode = os.getenv("PERSISTENCE_MODE", "").strip().lower()
        if (
            mode == "inmemory"
            or "InMemory" in repo_name
            or getattr(repo, "is_in_memory", False)
        ):
            logger.critical(
                "FATAL STARTUP GUARD FAILURE: CLOUDLENS_ENV='%s' refuses InMemory repository configuration (%s). "
                "Real PostgreSQL database persistence (SqlRepository) is strictly mandatory in production environments.",
                env,
                repo_name,
            )
            sys.exit(1)

