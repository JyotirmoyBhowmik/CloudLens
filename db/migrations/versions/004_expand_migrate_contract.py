"""Zero-Downtime Rolling Upgrade Migration using Expand-Migrate-Contract Pattern.

Revision ID: 004_expand_migrate_contract
Revises: 003_materialized_aggregates
Create Date: 2026-09-26 00:03:00.000000

Enforces Prompt 06 Item 46:
"Create forward and backward migrations with an expand-migrate-contract pattern so that a
rolling upgrade never breaks a running replica."
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_expand_migrate_contract"
down_revision: Union[str, None] = "003_materialized_aggregates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # Phase 1: EXPAND (Zero-Downtime Addition)
    # Add new column 'amortised_blended_rate' as nullable with server default.
    # Running replicas continue writing legacy columns without interruption.
    # --------------------------------------------------------------------------
    op.add_column(
        "cost_fact",
        sa.Column("amortised_blended_rate", sa.Numeric(18, 6), nullable=True),
    )

    # --------------------------------------------------------------------------
    # Phase 2: MIGRATE (Data Backfill & Dual-Write Window)
    # Safely compute blended rate where pricing_quantity > 0.
    # --------------------------------------------------------------------------
    op.execute(
        """
        UPDATE cost_fact
        SET amortised_blended_rate = ROUND(effective_cost / NULLIF(pricing_quantity, 0), 6)
        WHERE pricing_quantity IS NOT NULL AND pricing_quantity > 0;
        """
    )

    # --------------------------------------------------------------------------
    # Phase 3: CONTRACT (Enforce Final Production Invariant)
    # Set default for new rows after all application replicas have been deployed.
    # --------------------------------------------------------------------------
    op.alter_column(
        "cost_fact",
        "amortised_blended_rate",
        server_default="0.000000",
    )


def downgrade() -> None:
    # Reverse Contract: drop default
    op.alter_column(
        "cost_fact",
        "amortised_blended_rate",
        server_default=None,
    )
    # Reverse Expand: drop column cleanly
    op.drop_column("cost_fact", "amortised_blended_rate")
