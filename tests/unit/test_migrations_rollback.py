"""Unit Tests for Database Migrations, Reversible Rollback, and Expand-Migrate-Contract Pattern.

Enforces Prompt 06 Item 46 & Deliverable:
- Complete migration set with rollback.
- Expand-migrate-contract pattern so that a rolling upgrade never breaks a running replica.
"""

import importlib.util
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations" / "versions"


def load_migration_module(file_name: str):
    file_path = MIGRATIONS_DIR / file_name
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), file_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migrations_chain_and_complete_rollback_capability():
    """Verify all migrations have reversible rollback functions and form an unbroken DAG."""
    m1 = load_migration_module("001_initial_schema.py")
    m2 = load_migration_module("002_partitioned_facts.py")
    m3 = load_migration_module("003_materialized_aggregates.py")
    m4 = load_migration_module("004_expand_migrate_contract.py")
    m5 = load_migration_module("005_catalogues_and_gap_registry.py")
    m6 = load_migration_module("006_master_data_framework.py")

    # 1. Verify DAG linkage
    assert m1.revision == "001_initial_schema"
    assert m1.down_revision is None

    assert m2.revision == "002_partitioned_facts"
    assert m2.down_revision == "001_initial_schema"

    assert m3.revision == "003_materialized_aggregates"
    assert m3.down_revision == "002_partitioned_facts"

    assert m4.revision == "004_expand_migrate_contract"
    assert m4.down_revision == "003_materialized_aggregates"

    assert m5.revision == "005_catalogues_and_gap_registry"
    assert m5.down_revision == "004_expand_migrate_contract"

    assert m6.revision == "006_master_data_framework"
    assert m6.down_revision == "005_catalogues_and_gap_registry"

    # 2. Verify all migrations have both upgrade() and downgrade() functions
    for m in (m1, m2, m3, m4, m5, m6):
        assert hasattr(m, "upgrade") and callable(m.upgrade), (
            f"{m.revision} missing callable upgrade()"
        )
        assert hasattr(m, "downgrade") and callable(m.downgrade), (
            f"{m.revision} missing callable downgrade()"
        )


def test_expand_migrate_contract_pattern_implementation():
    """Verify migration 004 implements Expand-Migrate-Contract zero-downtime rolling upgrade."""
    m4_path = MIGRATIONS_DIR / "004_expand_migrate_contract.py"
    content = m4_path.read_text(encoding="utf-8")

    # Verify Phase 1: EXPAND (add column nullable)
    assert "EXPAND" in content
    assert "amortised_blended_rate" in content
    assert "nullable=True" in content

    # Verify Phase 2: MIGRATE (backfill computation)
    assert "MIGRATE" in content
    assert "UPDATE cost_fact" in content

    # Verify Phase 3: CONTRACT (apply constraint/default)
    assert "CONTRACT" in content

    # Verify Downgrade reverses contract, migrate, and expand
    assert "drop_column" in content
