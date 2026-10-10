"""Tenant Administration Fields (Prompt P12).

Revision ID: 017_tenant_administration_fields
Revises: 016_persistence_tier5_remaining_modules
Create Date: 2026-10-10 11:30:00.000000

Enforces Prompt P12:
- code: unique tenant code (unique index)
- type: PRODUCTION | NON_PRODUCTION | DEMO
- fiscal_year_start: 1..12
- iana_timezone: IANA timezone identifier
- retention_profile: data retention profile identifier
- status: ACTIVE | SUSPENDED
- suspension_reason: textual rationale when suspended
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "017_tenant_administration_fields"
down_revision: Union[str, None] = "016_persistence_tier5_remaining_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add tenant administration columns
    op.add_column("tenants", sa.Column("code", sa.String(64), nullable=True))
    op.add_column("tenants", sa.Column("type", sa.String(32), nullable=False, server_default="PRODUCTION"))
    op.add_column("tenants", sa.Column("fiscal_year_start", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tenants", sa.Column("iana_timezone", sa.String(64), nullable=False, server_default="UTC"))
    op.add_column("tenants", sa.Column("retention_profile", sa.String(64), nullable=False, server_default="STANDARD"))
    op.add_column("tenants", sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"))
    op.add_column("tenants", sa.Column("suspension_reason", sa.Text(), nullable=True))

    # 2. Backfill existing records with unique uppercase codes derived from id
    op.execute("""
        UPDATE tenants
        SET code = UPPER(REPLACE(id, 'tenant-', ''))
        WHERE code IS NULL OR code = '';
    """)
    op.execute("""
        UPDATE tenants
        SET code = UPPER(id)
        WHERE code IS NULL OR code = '';
    """)

    # 3. Create unique index on code
    op.create_index("idx_tenants_code", "tenants", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_tenants_code", table_name="tenants")
    op.drop_column("tenants", "suspension_reason")
    op.drop_column("tenants", "status")
    op.drop_column("tenants", "retention_profile")
    op.drop_column("tenants", "iana_timezone")
    op.drop_column("tenants", "fiscal_year_start")
    op.drop_column("tenants", "type")
    op.drop_column("tenants", "code")
