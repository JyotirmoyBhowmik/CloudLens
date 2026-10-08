"""Real-Database Restart Proofs Across All 11 Entities (Prompt P04).

Enforces:
- Pattern P1/P3/P4: Authoritative PostgreSQL persistence across process restarts.
- Proof per entity: entity written by Repository Instance A, Repository Instance A is discarded,
  fresh Repository Instance B is created, and the entity is retrieved from PostgreSQL.

Entities covered:
1. Tenants & Settings (SqlTenantRepository)
2. Identity Users (SqlIdentityRepository)
3. RBAC Scope Grants & Custom Roles (SqlRBACRepository)
4. Sessions & Token Revocation Registry (SqlIdentityRepository)
5. Machine Clients (SqlIdentityRepository)
6. Step-Up Challenges (SqlIdentityRepository)
7. Credential References - vault:// only (SqlCredentialRepository)
8. Audit Events - Append-Only & Hash-Chained (SqlAuditRepository)
9. Operational Overrides (SqlOverrideRepository)
10. Feature Flags (SqlFeatureFlagRepository)
11. Master Data Records & Registry (SqlMasterDataRepository)
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.audit.models import AuditEvent
from domain.audit.repository import SqlAuditRepository
from domain.config.feature_flags import FlagAuditEvent
from domain.config.feature_flags_repository import SqlFeatureFlagRepository
from domain.credentials.models import CredentialProfile
from domain.credentials.repository import SqlCredentialRepository
from domain.identity.models import (
    MachineClient,
    Session,
    StepUpChallenge,
    User,
)
from domain.identity.repository import SqlIdentityRepository
from domain.models.enums import (
    AuditEventType,
    AuthMethod,
    CredentialType,
    GrantEffect,
    GranteeType,
    OverrideClass,
    ProviderType,
    RotationState,
    StepUpAction,
    SystemRole,
    UserStatus,
)
from domain.overrides.models import OverrideRecord
from domain.overrides.repository import SqlOverrideRepository
from domain.rbac.models import RoleDefinition, ScopeGrant
from domain.rbac.repository import SqlRBACRepository
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant
from domain.tenant.repository import SqlTenantRepository
from masterdata.models import LifecycleStatus, MasterDataRecord, MasterRegistryEntry
from masterdata.repository import SqlMasterDataRepository

pytestmark = [pytest.mark.realdb]


# -----------------------------------------------------------------------------
# 1. Tenants & Settings
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tenant_persistence_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlTenantRepository()
    tenant = Tenant(
        id=tenant_id,
        name=f"Enterprise Corp {tenant_id}",
        reporting_currency="USD",
        created_at=now,
        updated_at=now,
    )
    await repo_a.save(tenant)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlTenantRepository()
    reloaded = await repo_b.get(tenant_id)
    assert reloaded is not None
    assert reloaded.id == tenant_id
    assert reloaded.name == f"Enterprise Corp {tenant_id}"
    assert reloaded.reporting_currency == "USD"


# -----------------------------------------------------------------------------
# 2. Identity Users
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_user_persistence_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    email = f"user_{uuid.uuid4().hex[:8]}@cloudlens.internal"
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlIdentityRepository()
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        display_name="Restart User",
        status=UserStatus.ACTIVE,
        roles=[SystemRole.FINANCE_USER],
        auth_method=AuthMethod.OIDC,
        is_break_glass=False,
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_user(user)

    # Discard Process A
    del repo_a

    # Process B reads by ID and by Email
    repo_b = SqlIdentityRepository()
    reloaded_by_id = await repo_b.get_user(user_id)
    assert reloaded_by_id is not None
    assert reloaded_by_id.email == email
    assert reloaded_by_id.roles == [SystemRole.FINANCE_USER]

    reloaded_by_email = await repo_b.get_user_by_email(tenant_id, email)
    assert reloaded_by_email is not None
    assert reloaded_by_email.id == user_id


# -----------------------------------------------------------------------------
# 3. RBAC Scope Grants & Custom Roles
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rbac_grants_and_custom_roles_survive_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    grant_id = f"grnt-{uuid.uuid4().hex[:12]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    role_code = f"ROLE_{uuid.uuid4().hex[:6].upper()}"

    # Process A writes grant and custom role
    repo_a = SqlRBACRepository()
    grant = ScopeGrant(
        id=grant_id,
        tenant_id=tenant_id,
        grantee_type=GranteeType.USER,
        grantee_id=user_id,
        effect=GrantEffect.ALLOW,
        providers=["AWS", "AZURE"],
        account_ids=["111222333444"],
        cost_centre_ids=["CC-ENG-01"],
        is_active=True,
    )
    await repo_a.save_scope_grant(grant)

    role_def = RoleDefinition(
        id=f"role-{tenant_id}-{role_code.lower()}",
        tenant_id=tenant_id,
        code=role_code,
        display_name="Custom FinOps Lead",
        description="Tenant specific FinOps Lead role",
        allowed_permissions=["cost:view", "budget:approve"],
        is_built_in=False,
    )
    await repo_a.save_custom_role(role_def)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlRBACRepository()
    reloaded_grant = await repo_b.get_scope_grant(grant_id)
    assert reloaded_grant is not None
    assert reloaded_grant.grantee_id == user_id
    assert "AWS" in reloaded_grant.providers
    assert "CC-ENG-01" in reloaded_grant.cost_centre_ids

    reloaded_role = await repo_b.get_custom_role(tenant_id, role_code)
    assert reloaded_role is not None
    assert reloaded_role.display_name == "Custom FinOps Lead"
    assert "cost:view" in reloaded_role.allowed_permissions


# -----------------------------------------------------------------------------
# 4. Sessions & Token Revocations
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_and_token_revocations_survive_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    family_id = f"fam-{uuid.uuid4().hex[:12]}"
    jti = f"jti-{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlIdentityRepository()
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"sess_{uuid.uuid4().hex[:6]}@cloudlens.internal",
        display_name="Session User",
        status=UserStatus.ACTIVE,
        roles=[SystemRole.READ_ONLY_USER],
        created_at=now,
        updated_at=now,
    )
    await repo_a.save_user(user)

    session = Session(
        id=session_id,
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        token_family_id=family_id,
        expires_at=now + timedelta(hours=2),
        is_active=True,
    )
    await repo_a.save_session(session)
    await repo_a.revoke_session(session_id, reason="EXPLICIT_TEST_LOGOUT")
    await repo_a.revoke_token(jti, expires_at=(now + timedelta(hours=1)).timestamp())

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlIdentityRepository()
    reloaded_sess = await repo_b.get_session(session_id)
    assert reloaded_sess is not None
    assert reloaded_sess.is_active is False
    assert reloaded_sess.revocation_reason == "EXPLICIT_TEST_LOGOUT"

    assert await repo_b.is_token_revoked(jti=jti) is True


# -----------------------------------------------------------------------------
# 5. Machine Clients
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_machine_client_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    client_id = f"mc-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlIdentityRepository()
    client = MachineClient(
        id=client_id,
        client_id=client_id,
        tenant_id=tenant_id,
        name="Ingestion Worker",
        secret_hash="argon2id$hashedsecretvalue123",
        scoped_permissions=["ingest:cur", "ingest:azure"],
        is_active=True,
    )
    await repo_a.save_machine_client(client)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlIdentityRepository()
    reloaded = await repo_b.get_machine_client(client_id)
    assert reloaded is not None
    assert reloaded.name == "Ingestion Worker"
    assert reloaded.secret_hash == "argon2id$hashedsecretvalue123"
    assert "ingest:cur" in reloaded.scoped_permissions


# -----------------------------------------------------------------------------
# 6. Step-Up Challenges
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step_up_challenge_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    challenge_id = f"step-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlIdentityRepository()
    challenge = StepUpChallenge(
        id=challenge_id,
        tenant_id=tenant_id,
        user_id=user_id,
        action=StepUpAction.CREDENTIAL_CREATION,
        target_entity_id="report-999",
        challenge_code="849201",
        expires_at=now + timedelta(minutes=5),
        is_verified=False,
    )
    await repo_a.save_step_up_challenge(challenge)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlIdentityRepository()
    reloaded = await repo_b.get_step_up_challenge(challenge_id)
    assert reloaded is not None
    assert reloaded.action == StepUpAction.CREDENTIAL_CREATION
    assert reloaded.challenge_code == "849201"
    assert reloaded.target_entity_id == "report-999"


# -----------------------------------------------------------------------------
# 7. Credential References (vault:// only)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_credential_reference_vault_only_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    profile_id = f"cred-{uuid.uuid4().hex[:12]}"

    # Process A writes
    repo_a = SqlCredentialRepository()
    profile = CredentialProfile(
        id=profile_id,
        tenant_id=tenant_id,
        name="AWS Master Billing Role",
        provider=ProviderType.AWS,
        credential_type=CredentialType.ROLE_ARN,
        secret_ref="vault://secret/cloudlens/tenants/aws/billing-role",
        fingerprint="fp-849102",
        version=1,
        rotation_state=RotationState.ACTIVE,
    )
    await repo_a.save(profile)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlCredentialRepository()
    reloaded = await repo_b.get(profile_id)
    assert reloaded is not None
    assert reloaded.name == "AWS Master Billing Role"
    assert reloaded.secret_ref == "vault://secret/cloudlens/tenants/aws/billing-role"

    # Enforce vault:// check constraint at repo level
    with pytest.raises(ValueError, match="Secret reference must start with 'vault://'"):
        bad_profile = CredentialProfile(
            id=f"cred-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name="Plain Secret",
            provider=ProviderType.AWS,
            credential_type=CredentialType.CLIENT_SECRET,
            secret_ref="plain://plaintext-secret-is-forbidden",
            fingerprint="bad",
        )
        await repo_b.save(bad_profile)


# -----------------------------------------------------------------------------
# 8. Audit Events
# -----------------------------------------------------------------------------
def test_audit_event_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    event_id = f"audit-{uuid.uuid4().hex[:12]}"
    ctx = TenantContext(tenant_id=tenant_id, user_id="system-audit")
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlAuditRepository()
    event = AuditEvent(
        id=event_id,
        tenant_id=tenant_id,
        event_type=AuditEventType.CONFIG_CHANGED,
        actor_id="usr-audit-agent",
        action="TENANT_SETTINGS_UPDATE",
        resource_type="TENANT",
        resource_id=tenant_id,
        correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
        occurred_at=now,
        event_hash="hash-abc-123",
    )
    repo_a.save(event, tenant_context=ctx)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlAuditRepository()
    reloaded = repo_b.get(event_id, tenant_context=ctx)
    assert reloaded is not None
    assert reloaded.action == "TENANT_SETTINGS_UPDATE"
    assert reloaded.actor_id == "usr-audit-agent"


# -----------------------------------------------------------------------------
# 9. Operational Overrides
# -----------------------------------------------------------------------------
def test_operational_override_survives_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    override_id = f"ovr-{uuid.uuid4().hex[:12]}"
    ctx = TenantContext(tenant_id=tenant_id, user_id="usr-ops-lead")
    now = datetime.now(UTC)

    # Process A writes
    repo_a = SqlOverrideRepository()
    override = OverrideRecord(
        id=override_id,
        tenant_id=tenant_id,
        override_class=OverrideClass.BUDGET_THRESHOLD,
        who="usr-ops-lead",
        what="budget.monthly.threshold",
        why="Quarter-end batch compute spike approved by VP",
        when=now,
        previous_value={"threshold_pct": 80},
        new_value={"threshold_pct": 95},
        expiry=now + timedelta(days=7),
    )
    repo_a.save(override, tenant_context=ctx)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlOverrideRepository()
    reloaded = repo_b.get(override_id, tenant_context=ctx)
    assert reloaded is not None
    assert reloaded.what == "budget.monthly.threshold"
    assert reloaded.new_value == {"threshold_pct": 95}


# -----------------------------------------------------------------------------
# 10. Feature Flags
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feature_flags_survive_process_restart():
    tenant_id = f"ten-{uuid.uuid4().hex[:8]}"
    flag_key = f"flag_{uuid.uuid4().hex[:8]}"

    # Process A writes tenant override and audit record
    repo_a = SqlFeatureFlagRepository()
    await repo_a.set_override(
        flag_key=flag_key,
        enabled=True,
        tenant_id=tenant_id,
        updated_by="lead-admin@cloudlens.internal",
        reason="Early access program",
    )
    audit = FlagAuditEvent(
        flag_key=flag_key,
        tenant_id=tenant_id,
        old_value=False,
        new_value=True,
        changed_by="lead-admin@cloudlens.internal",
        reason="Early access program",
    )
    await repo_a.record_audit(audit)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlFeatureFlagRepository()
    val = await repo_b.get_override(flag_key=flag_key, tenant_id=tenant_id)
    assert val is True

    audit_logs = await repo_b.get_audit_log(flag_key=flag_key, tenant_id=tenant_id)
    assert len(audit_logs) >= 1
    assert audit_logs[0].new_value is True
    assert audit_logs[0].changed_by == "lead-admin@cloudlens.internal"


# -----------------------------------------------------------------------------
# 11. Master Data Records & Registry
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_master_data_records_and_registry_survive_process_restart():
    code = f"CAT_{uuid.uuid4().hex[:6].upper()}"
    record_id = f"rec-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    # Process A writes registry entry and record
    repo_a = SqlMasterDataRepository()
    entry = MasterRegistryEntry(
        code=code,
        name=f"Category {code}",
        purpose="Classification of cloud services",
        is_tenant_scoped=False,
        is_editable=True,
        requires_approval=False,
        consuming_modules=["billing", "analytics"],
        seed_file="seeds/category.json",
    )
    await repo_a.save_registry_entry(entry)

    record = MasterDataRecord(
        id=record_id,
        master_type=code,
        code="COMPUTE",
        display_name="Cloud Compute Engines",
        description="IaaS Virtual Machines and Containers",
        effective_from=now,
        lifecycle_status=LifecycleStatus.PUBLISHED,
        attributes={"cores_range": "1-128"},
    )
    await repo_a.save_record(record)

    # Discard Process A
    del repo_a

    # Process B reads
    repo_b = SqlMasterDataRepository()
    reloaded_entry = await repo_b.get_registry_entry(code)
    assert reloaded_entry is not None
    assert reloaded_entry.name == f"Category {code}"
    assert "billing" in reloaded_entry.consuming_modules

    reloaded_record = await repo_b.get_record(record_id)
    assert reloaded_record is not None
    assert reloaded_record.code == "COMPUTE"
    assert reloaded_record.display_name == "Cloud Compute Engines"
    assert reloaded_record.attributes == {"cores_range": "1-128"}
