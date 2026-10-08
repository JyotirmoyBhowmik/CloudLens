"""Persistence Tier 2: Connections, Sync, Wizard, Landing (Prompt P05).

Revision ID: 013_persistence_tier2_unique_idempotency
Revises: 012_persistence_tier1_identity_audit_config
Create Date: 2026-10-09 00:00:00.000000

Enforces Prompt P05:
- Unique idempotency constraint on sync_jobs for (tenant_id, connector_id, capability, period_start, period_end, dataset_version).
- Ensures NULLS NOT DISTINCT so jobs with null period or version are strictly covered.
- Confirms grants to cloudlens_app role.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013_persistence_tier2_unique_idempotency"
down_revision: Union[str, None] = "012_persistence_tier1_identity_audit_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add Unique Idempotency Constraint on sync_jobs (connector, capability, period, version)
    op.execute("""
        ALTER TABLE sync_jobs
        ADD CONSTRAINT uq_sync_jobs_idempotency
        UNIQUE NULLS NOT DISTINCT (tenant_id, connector_id, capability, period_start, period_end, dataset_version);
    """)

    # 2. Re-grant privileges to cloudlens_app
    op.execute("""
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cloudlens_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cloudlens_app;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE sync_jobs
        DROP CONSTRAINT IF EXISTS uq_sync_jobs_idempotency;
    """)
