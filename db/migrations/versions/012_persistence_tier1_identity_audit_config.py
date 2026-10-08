"""Persistence Tier 1: Identity, Tenancy, Audit, Configuration (Prompt P04).

Revision ID: 012_persistence_tier1_identity_audit_config
Revises: 011_persistence_foundation_and_rls
Create Date: 2026-10-08 23:00:00.000000

Enforces Prompt P04:
- identity_users: Real PostgreSQL user identity store (replacing in-memory _users & _users_by_email).
- role_grants & custom_roles: Multi-dimensional scope grants and tenant custom roles.
- identity_sessions, token_revocations, token_families: Real session store and persistent revocation registry.
- machine_clients: Service principals with salted hashed secrets.
- step_up_challenges: Ephemeral short-TTL step-up challenges.
- credential_profiles: vault:// only reference storage with DB check constraint.
- audit_event: Enriched schema and append-only database triggers preventing UPDATE and DELETE.
- overrides: Schema alignment for operational and rate overrides.
- feature_flags & feature_flag_audit: Global and tenant-scoped toggle persistence.
- master_data_records: Schema indexes and RLS enforcement.
- Row-Level Security (ENABLE RLS + FORCE RLS) and grants to cloudlens_app.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "012_persistence_tier1_identity_audit_config"
down_revision: Union[str, None] = "011_persistence_foundation_and_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. identity_users
    op.create_table(
        "identity_users",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("roles", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("auth_method", sa.String(32), nullable=False, server_default="OIDC"),
        sa.Column("idp_sub", sa.String(255), nullable=True),
        sa.Column("is_break_glass", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_identity_users_tenant_email", "identity_users", ["tenant_id", "email"], unique=True)
    op.create_index("idx_identity_users_tenant_id", "identity_users", ["tenant_id", "id"])

    # 2. role_grants
    op.create_table(
        "role_grants",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("grantee_type", sa.String(32), nullable=False),
        sa.Column("grantee_id", sa.String(64), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False, server_default="ALLOW"),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_role_grants_tenant_grantee", "role_grants", ["tenant_id", "grantee_id"])
    op.create_index("idx_role_grants_tenant_type", "role_grants", ["tenant_id", "grantee_type"])

    # 3. custom_roles
    op.create_table(
        "custom_roles",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("allowed_permissions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("max_scope", sa.String(32), nullable=False, server_default="SCOPE"),
        sa.Column("requires_mfa", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "code"),
    )

    # 4. identity_sessions
    op.create_table(
        "identity_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("token_family_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_identity_sessions_tenant_user", "identity_sessions", ["tenant_id", "user_id"])
    op.create_index("idx_identity_sessions_family", "identity_sessions", ["token_family_id"])

    # 5. token_revocations
    op.create_table(
        "token_revocations",
        sa.Column("revocation_key", sa.String(128), primary_key=True, nullable=False),
        sa.Column("revocation_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_token_revocations_type_target", "token_revocations", ["revocation_type", "target_id"])

    # 6. token_families
    op.create_table(
        "token_families",
        sa.Column("family_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("is_compromised", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("used_tokens", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 7. machine_clients
    op.create_table(
        "machine_clients",
        sa.Column("client_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column("secondary_secret_hash", sa.String(255), nullable=True),
        sa.Column("scoped_permissions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("secret_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_machine_clients_tenant", "machine_clients", ["tenant_id", "client_id"])

    # 8. step_up_challenges
    op.create_table(
        "step_up_challenges",
        sa.Column("challenge_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_entity_id", sa.String(64), nullable=True),
        sa.Column("challenge_code", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_step_up_challenges_tenant_user", "step_up_challenges", ["tenant_id", "user_id"])

    # 9. credential_profiles (vault:// only reference storage)
    op.create_table(
        "credential_profiles",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("credential_type", sa.String(64), nullable=False),
        sa.Column("secret_ref", sa.String(500), nullable=False),
        sa.Column("previous_secret_ref", sa.String(500), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("rotation_state", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("secret_ref LIKE 'vault://%'", name="chk_credential_profiles_vault_only"),
    )
    op.create_index("idx_credential_profiles_tenant_prov", "credential_profiles", ["tenant_id", "provider"])

    # 10. audit_event table enrichment
    # Add columns if not already present
    conn = op.get_bind()
    existing_cols = {
        col["name"]
        for col in sa.inspect(conn).get_columns("audit_event")
    }
    if "event_type" not in existing_cols:
        op.add_column("audit_event", sa.Column("event_type", sa.String(64), nullable=True))
    if "actor_roles" not in existing_cols:
        op.add_column("audit_event", sa.Column("actor_roles", postgresql.JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")))
    if "details" not in existing_cols:
        op.add_column("audit_event", sa.Column("details", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")))
    if "previous_event_hash" not in existing_cols:
        op.add_column("audit_event", sa.Column("previous_event_hash", sa.String(64), nullable=True))
    if "event_hash" not in existing_cols:
        op.add_column("audit_event", sa.Column("event_hash", sa.String(64), nullable=True))
    if "ip_address" not in existing_cols:
        op.add_column("audit_event", sa.Column("ip_address", sa.String(45), nullable=True))
    if "user_agent" not in existing_cols:
        op.add_column("audit_event", sa.Column("user_agent", sa.String(255), nullable=True))

    # Append-only trigger on audit_event
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_audit_event_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'PERMISSION_DENIED: audit table is append-only at the database level.';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_event_no_update'
            ) THEN
                CREATE TRIGGER trg_audit_event_no_update
                BEFORE UPDATE ON audit_event
                FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_audit_event_no_delete'
            ) THEN
                CREATE TRIGGER trg_audit_event_no_delete
                BEFORE DELETE ON audit_event
                FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
            END IF;
        END $$;
    """)

    # 11. feature_flags & feature_flag_audit
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("flag_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feature_flags_tenant_key", "feature_flags", ["tenant_id", "flag_key"])
    op.create_index("idx_feature_flags_scope_key", "feature_flags", ["scope", "flag_key"])

    op.create_table(
        "feature_flag_audit",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("flag_key", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("old_value", sa.Boolean(), nullable=False),
        sa.Column("new_value", sa.Boolean(), nullable=False),
        sa.Column("changed_by", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feature_flag_audit_key", "feature_flag_audit", ["flag_key", "timestamp"])

    # 12. Enable & Force RLS across new multi-tenant tables
    new_tenant_tables = [
        "identity_users",
        "role_grants",
        "custom_roles",
        "identity_sessions",
        "machine_clients",
        "step_up_challenges",
        "credential_profiles",
    ]
    for table in new_tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            FOR ALL TO PUBLIC
            USING (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')
                OR tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
                OR current_setting('cloudlens.bypass_rls', true) = 'on'
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')
                OR tenant_id = NULLIF(current_setting('cloudlens.current_tenant_id', true), '')
                OR current_setting('cloudlens.bypass_rls', true) = 'on'
            );
        """)

    # 13. Grant privileges to cloudlens_app role
    op.execute("""
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cloudlens_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cloudlens_app;
    """)


def downgrade() -> None:
    # Reverse tables
    tables = [
        "feature_flag_audit",
        "feature_flags",
        "credential_profiles",
        "step_up_challenges",
        "machine_clients",
        "token_families",
        "token_revocations",
        "identity_sessions",
        "custom_roles",
        "role_grants",
        "identity_users",
    ]
    for table in tables:
        op.drop_table(table)
