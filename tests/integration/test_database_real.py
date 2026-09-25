"""Integration Tests against a real PostgreSQL instance (No Mocks allowed).

Prompt 04 Requirement:
Integration tests against a real PostgreSQL instance (not a mock).
Constraints: No mocked databases in integration tests; no retry of flaky tests.
"""

import os
import socket

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from domain.config import config_resolver


def is_postgres_available(host: str, port: int, timeout: float = 1.5) -> bool:
    """Check if PostgreSQL port is actively listening before attempting DB connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def get_real_postgres_url() -> str:
    """Builds PostgreSQL connection URL from environment or configuration surface."""
    # Allow override via DATABASE_URL or standard POSTGRES_* environment variables
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    host = os.getenv("POSTGRES_HOST", config_resolver.get_effective_value("database.host"))
    port = int(os.getenv("POSTGRES_PORT", config_resolver.get_effective_value("database.port")))
    user = os.getenv("POSTGRES_USER", config_resolver.get_effective_value("database.user"))
    password = os.getenv(
        "POSTGRES_PASSWORD", config_resolver.get_effective_value("database.password")
    )
    name = os.getenv("POSTGRES_DB", config_resolver.get_effective_value("database.name"))

    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


@pytest.fixture(scope="module")
def real_postgres_engine():
    """Provides a real SQLAlchemy engine connected to PostgreSQL, or skips if unreachable."""
    host = os.getenv("POSTGRES_HOST", config_resolver.get_effective_value("database.host"))
    port = int(os.getenv("POSTGRES_PORT", config_resolver.get_effective_value("database.port")))

    if not is_postgres_available(host, port):
        pytest.skip(
            f"Real PostgreSQL instance is not reachable at {host}:{port}. "
            "Skipping real database integration test. "
            "(Strict constraint: Mock databases are strictly forbidden per Prompt 04 & BBP Section 47)."
        )

    db_url = get_real_postgres_url()
    engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(
            f"Connected to port {port} but failed PostgreSQL authentication/database access: {exc}. "
            "Skipping real database test (no mocks allowed)."
        )

    yield engine
    engine.dispose()


def test_real_postgres_dialect_and_version(real_postgres_engine):
    """Verify connected database is genuine PostgreSQL and retrieve engine version."""
    with real_postgres_engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        row = result.fetchone()
        assert row is not None
        version_str = row[0]
        assert "PostgreSQL" in version_str, f"Expected PostgreSQL dialect, got: {version_str}"


def test_real_postgres_ddl_and_partitioning(real_postgres_engine):
    """Verify real PostgreSQL DDL execution with range-partitioned table creation and cleanup."""
    table_name = "test_audit_log_p04"
    part_name = "test_audit_log_p04_2026"

    with real_postgres_engine.begin() as conn:
        # Cleanup if previously left over
        conn.execute(text(f"DROP TABLE IF EXISTS {part_name} CASCADE;"))
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))

        try:
            # Create partitioned table (PostgreSQL native declarative partitioning)
            create_parent_ddl = f"""
            CREATE TABLE {table_name} (
                event_id VARCHAR(64) NOT NULL,
                tenant_id VARCHAR(64) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                payload JSONB NOT NULL,
                PRIMARY KEY (event_id, created_at)
            ) PARTITION BY RANGE (created_at);
            """
            conn.execute(text(create_parent_ddl))

            # Create partition for year 2026
            create_partition_ddl = f"""
            CREATE TABLE {part_name} PARTITION OF {table_name}
            FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
            """
            conn.execute(text(create_partition_ddl))

            # Insert sample record
            insert_stmt = text(
                f"""
                INSERT INTO {table_name} (event_id, tenant_id, created_at, payload)
                VALUES (:event_id, :tenant_id, '2026-06-15 12:00:00+00', :payload)
                """
            )
            conn.execute(
                insert_stmt,
                {
                    "event_id": "evt-real-pg-001",
                    "tenant_id": "tenant-enterprise-prod",
                    "payload": '{"action": "quality_gate_passed", "gate": "PR"}',
                },
            )

            # Query from partitioned parent table
            select_stmt = text(
                f"SELECT tenant_id, payload->>'action' FROM {table_name} WHERE event_id = :event_id;"
            )
            res = conn.execute(select_stmt, {"event_id": "evt-real-pg-001"}).fetchone()
            assert res is not None
            assert res[0] == "tenant-enterprise-prod"
            assert res[1] == "quality_gate_passed"

        finally:
            # Deterministic cleanup per Enterprise Rule 5.1
            conn.execute(text(f"DROP TABLE IF EXISTS {part_name} CASCADE;"))
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))


def test_real_postgres_transactional_rollback(real_postgres_engine):
    """Verify ACID transactional rollback ensures zero partial state commits."""
    table_name = "test_transact_isolation_p04"

    with real_postgres_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name};"))
        conn.execute(text(f"CREATE TABLE {table_name} (id INT PRIMARY KEY, name VARCHAR(50));"))

    # Intentional transaction rollback
    try:
        with real_postgres_engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text(f"INSERT INTO {table_name} VALUES (1, 'rollback_test');"))
            # Trigger rollback
            trans.rollback()
    finally:
        pass

    # Assert row was never committed
    with real_postgres_engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name};")).scalar()
        assert count == 0
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name};"))
        conn.commit()
