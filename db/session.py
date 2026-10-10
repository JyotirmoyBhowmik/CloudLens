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
_engines_by_loop: dict[asyncio.AbstractEventLoop, AsyncEngine] = {}
_factories_by_loop: dict[asyncio.AbstractEventLoop, async_sessionmaker[AsyncSession]] = {}


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
    """Returns async SQLAlchemy engine configured with connection pooling, bound to current event loop."""
    global _async_engine, _engines_by_loop
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        if loop not in _engines_by_loop:
            db_url = get_database_url()
            is_test_env = (
                "pytest" in sys.modules
                or "PYTEST_CURRENT_TEST" in os.environ
                or os.getenv("CLOUDLENS_TEST_MODE") == "1"
            )
            if is_test_env:
                _engines_by_loop[loop] = create_async_engine(
                    db_url,
                    poolclass=NullPool,
                    echo=False,
                )
            else:
                _engines_by_loop[loop] = create_async_engine(
                    db_url,
                    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
                    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
                    pool_pre_ping=True,
                    echo=False,
                )
        return _engines_by_loop[loop]

    if _async_engine is None:
        db_url = get_database_url()
        _async_engine = create_async_engine(
            db_url,
            poolclass=NullPool,
            echo=False,
        )
    return _async_engine


def reset_async_engine() -> None:
    """Disposes and resets engine singleton for testing."""
    global _async_engine, _async_session_factory, _engines_by_loop, _factories_by_loop
    _async_engine = None
    _async_session_factory = None
    _engines_by_loop.clear()
    _factories_by_loop.clear()


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns async session factory bound to the current event loop."""
    global _async_session_factory, _factories_by_loop
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        if loop not in _factories_by_loop:
            engine = get_async_engine()
            _factories_by_loop[loop] = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return _factories_by_loop[loop]

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


REPOSITORY_REGISTRY_GETTERS = [
    ("tenant_settings", "domain.config.repository", "get_tenant_settings_repository"),
    ("feature_flags", "domain.config.feature_flags_repository", "get_feature_flag_repository"),
    ("identity", "domain.identity.repository", "get_identity_repository"),
    ("tenant", "domain.tenant.repository", "get_tenant_repository"),
    ("rbac", "domain.rbac.repository", "get_rbac_repository"),
    ("audit", "domain.audit.repository", "get_audit_repository"),
    ("masterdata", "masterdata.repository", "get_master_data_repository"),
    ("connectors", "domain.connectors.repository", "get_connector_repository"),
    ("sync", "domain.sync.repository", "get_sync_repository"),
    ("wizard", "domain.wizard.repository", "get_wizard_repository"),
    ("checkpoint", "connectors.contract.checkpoint_store", "get_checkpoint_store"),
    ("cost", "domain.cost.repository", "get_cost_repository"),
    ("budgets", "domain.budgets.repository", "get_budget_repository"),
    ("pricing", "domain.pricing.repository", "get_pricing_repository"),
    ("thresholds", "domain.thresholds.repository", "get_threshold_repository"),
    ("forecasting", "domain.forecasting.repository", "get_forecast_repository"),
    ("reconciliation", "domain.cost.reconciliation.repository", "get_reconciliation_repository"),
    ("alerts", "domain.alerting.repository", "get_alert_repository"),
    ("contextual_alerts", "domain.alerting.contextual", "get_contextual_alert_repository"),
    ("notifications", "domain.notification.repository", "get_notification_log_repository"),
    ("policy", "domain.policy.repository", "get_policy_repository"),
    ("remediation", "domain.remediation.repository", "get_remediation_repository"),
    ("quotas", "domain.quotas.repository", "get_quota_repository"),
    ("provisioning", "domain.provisioning.repository", "get_provisioning_repository"),
    ("statements", "domain.statements.repository", "get_statement_repository"),
    ("bulk_import", "domain.bulk_import.repository", "get_bulk_import_repository"),
    ("dependency", "domain.dependency.repository", "get_dependency_repository"),
    ("usage", "domain.usage.repository", "get_usage_repository"),
    ("runtime", "domain.runtime.repository", "get_runtime_state_repository"),
    ("hierarchy", "domain.hierarchy.repository", "get_hierarchy_repository"),
    ("catalogues", "domain.catalogues.repository", "get_catalogue_repository"),
    ("reports", "domain.reports.repository", "get_report_repository"),
    ("analytics", "domain.analytics.repository", "get_analytics_repository"),
]


def verify_persistence_startup_guard(active_repository: Any = None) -> None:
    """Enforces Startup Guard outside development across all MVP repositories.

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

        mode = os.getenv("PERSISTENCE_MODE", "").strip().lower()

        repos_to_check = []
        if active_repository is not None:
            repos_to_check.append(active_repository)
        else:
            import importlib

            for name, mod_path, getter_name in REPOSITORY_REGISTRY_GETTERS:
                try:
                    mod = importlib.import_module(mod_path)
                    getter = getattr(mod, getter_name)
                    repos_to_check.append(getter())
                except Exception as e:
                    logger.debug("Startup guard repo check skipped %s: %s", name, e)

        for repo in repos_to_check:
            repo_name = type(repo).__name__
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


# -----------------------------------------------------------------------------
# Synchronous Execution Bridge for Async SQLAlchemy Repositories
# -----------------------------------------------------------------------------
import threading
import asyncio

_sync_bridge_loop: asyncio.AbstractEventLoop | None = None
_sync_bridge_thread: threading.Thread | None = None
_sync_bridge_lock = threading.Lock()


def get_sync_bridge_loop() -> asyncio.AbstractEventLoop:
    """Returns a persistent event loop on a dedicated thread for synchronous repository bridges.

    Guarantees that asyncpg connection pool handles in SQLAlchemy are always bound
    to the same event loop across synchronous calls, preventing Windows ProactorEventLoop teardown
    crashes ('NoneType' object has no attribute 'send') when multiple sync queries access the pool.
    """
    global _sync_bridge_loop, _sync_bridge_thread
    with _sync_bridge_lock:
        if _sync_bridge_loop is None or _sync_bridge_loop.is_closed():
            _sync_bridge_loop = asyncio.new_event_loop()
            _sync_bridge_thread = threading.Thread(
                target=_sync_bridge_loop.run_forever,
                name="CloudLens-SyncBridgeLoop",
                daemon=True,
            )
            _sync_bridge_thread.start()
        return _sync_bridge_loop


def run_async(coro: Any, timeout: float = 10.0) -> Any:
    """Executes a coroutine from synchronous code on the persistent bridge event loop with timeout."""
    loop = get_sync_bridge_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)

