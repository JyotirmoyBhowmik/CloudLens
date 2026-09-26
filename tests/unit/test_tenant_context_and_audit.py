"""Unit Tests for Tenant Scoping, Append-Only Audit Stream, and Overrides (Prompt 13).

Acceptance Criteria:
- No role, including Super Admin, can edit or delete an audit record; the attempt is itself audited.
- An override submitted without a reason or expiry is rejected.
- An expired override reverts automatically and the reversion is audited.
- Queries without tenant context fail at test time.
- Object storage enforces tenant prefixes and rejects traversal.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service, reset_audit_service
from domain.models.enums import AuditEventType, OverrideClass, OverrideStatus
from domain.models.exceptions import (
    AuditTamperForbiddenException,
    CrossTenantStorageAccessException,
    InvalidStoragePathException,
    MissingTenantContextException,
    OverrideValidationException,
    PermanentOverrideNotAllowedException,
)
from domain.overrides.models import OverrideApproval, OverrideCreateRequest
from domain.overrides.service import get_override_service, reset_override_service
from domain.tenant.context import TenantContext, require_tenant_context
from domain.tenant.object_store import InMemoryTenantObjectStorage
from domain.tenant.repository import TenantAwareRepository
from workers.cloudlens_workers.celery_app import execute_tenant_job


@pytest.fixture(autouse=True)
def clean_services():
    reset_audit_service()
    reset_override_service()
    yield
    reset_audit_service()
    reset_override_service()


# ==============================================================================
# 1. TenantContext & Repository Scoping (Item 83, 84)
# ==============================================================================


def test_tenant_context_validation_rejects_empty():
    """Verify TenantContext rejects empty or whitespace tenant_id."""
    with pytest.raises(MissingTenantContextException):
        TenantContext(tenant_id="")

    with pytest.raises(MissingTenantContextException):
        TenantContext(tenant_id="   ")

    tc = TenantContext(tenant_id="org-acme", user_id="user-1")
    assert tc.tenant_id == "org-acme"
    assert require_tenant_context(tc) is tc

    with pytest.raises(MissingTenantContextException):
        require_tenant_context(None)

    with pytest.raises(MissingTenantContextException):
        require_tenant_context("not-a-context")


class DummyEntity:
    pass


class DummyRepository(TenantAwareRepository[Any]):
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> Any:
        self._validate_tenant_context(tenant_context)
        return {"id": entity_id, "tenant": tenant_context.tenant_id}

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        _ = (filter_params, limit, offset)
        self._validate_tenant_context(tenant_context)
        return []

    def save(self, entity: Any, *, tenant_context: TenantContext) -> Any:
        self._validate_tenant_context(tenant_context)
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        _ = entity_id
        self._validate_tenant_context(tenant_context)
        return True

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        _ = entity_id
        self._validate_tenant_context(tenant_context)
        return True


def test_repository_fails_without_tenant_context():
    """Acceptance: A query without tenant context fails at test time."""
    repo = DummyRepository()

    # Omission of required argument fails at test/call time with TypeError
    with pytest.raises(TypeError):
        repo.get("entity-1")  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        repo.list()  # type: ignore[call-arg]

    # Passing None fails with MissingTenantContextException
    with pytest.raises(MissingTenantContextException):
        repo.get("entity-1", tenant_context=None)  # type: ignore[arg-type]


# ==============================================================================
# 2. Tenant-Prefixed Object Storage (Item 85)
# ==============================================================================


def test_tenant_object_storage_prefixes_and_isolation():
    """Verify object storage applies tenants/{tenant_id}/ prefix and blocks path traversal."""
    store = InMemoryTenantObjectStorage()
    tc_a = TenantContext(tenant_id="tenant-alpha", user_id="alice")
    tc_b = TenantContext(tenant_id="tenant-beta", user_id="bob")

    # Store in Tenant A
    scoped = store.put_object(tenant_context=tc_a, key="reports/march.csv", data=b"data-a")
    assert scoped == "tenants/tenant-alpha/reports/march.csv"

    # Read from Tenant A
    assert store.get_object(tenant_context=tc_a, key="reports/march.csv") == b"data-a"

    # Attempt to read Tenant A object using Tenant B context fails
    with pytest.raises(FileNotFoundError):
        store.get_object(tenant_context=tc_b, key="reports/march.csv")

    # Attempt cross-tenant prefix injection fails with CrossTenantStorageAccessException
    with pytest.raises(CrossTenantStorageAccessException):
        store.put_object(
            tenant_context=tc_a,
            key="tenants/tenant-beta/malicious.txt",
            data=b"exploit",
        )

    # Attempt directory traversal fails with InvalidStoragePathException
    with pytest.raises(InvalidStoragePathException):
        store.put_object(
            tenant_context=tc_a,
            key="../secrets.txt",
            data=b"traversal",
        )

    with pytest.raises(InvalidStoragePathException):
        store.get_object(
            tenant_context=tc_a,
            key="sub/../../etc/passwd",
        )


# ==============================================================================
# 3. Append-Only Audit Stream & Tamper Auditing (Item 86)
# ==============================================================================


def test_append_only_audit_stream_and_hash_chaining():
    """Verify audit stream appends events and maintains cryptographic hash chaining."""
    service = get_audit_service()
    tc = TenantContext(tenant_id="tenant-audit-1", user_id="sec-admin")

    e1 = service.append_event(
        tenant_context=tc,
        event_in=AuditEventCreate(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            actor_id="sec-admin@corp.internal",
            action="OIDC_LOGIN",
            resource_type="SESSION",
            resource_id="ses-101",
            details={"ip": "127.0.0.1"},
        ),
    )
    assert e1.previous_event_hash is None
    assert len(e1.event_hash) == 64

    e2 = service.append_event(
        tenant_context=tc,
        event_in=AuditEventCreate(
            event_type=AuditEventType.CREDENTIAL_CREATED,
            actor_id="sec-admin@corp.internal",
            action="CREATE_CREDENTIAL",
            resource_type="CREDENTIAL_PROFILE",
            resource_id="cred-aws-01",
            details={"provider": "AWS"},
        ),
    )
    assert e2.previous_event_hash == e1.event_hash
    assert service.verify_stream_integrity(tenant_context=tc) is True


def test_audit_records_immutable_even_for_super_admin():
    """Acceptance: No role, including Super Admin, can edit or delete an audit record; the attempt is itself audited."""
    service = get_audit_service()
    super_admin_tc = TenantContext(
        tenant_id="tenant-audit-2",
        user_id="admin@jyotirmoyb.com",
        roles=["GLOBAL_ADMIN"],
        is_superuser=True,
    )

    event = service.append_event(
        tenant_context=super_admin_tc,
        event_in=AuditEventCreate(
            event_type=AuditEventType.CONFIG_CHANGED,
            actor_id="admin@jyotirmoyb.com",
            action="UPDATE_CONFIG",
            resource_type="SYSTEM_SETTING",
            resource_id="retention.days",
            details={"old": 90, "new": 180},
        ),
    )

    # Super Admin attempts to DELETE audit event -> Forbidden!
    with pytest.raises(AuditTamperForbiddenException):
        service.attempt_mutation(
            tenant_context=super_admin_tc,
            event_id=event.id,
            operation="DELETE",
        )

    # Super Admin attempts to UPDATE audit event -> Forbidden!
    with pytest.raises(AuditTamperForbiddenException):
        service.attempt_mutation(
            tenant_context=super_admin_tc,
            event_id=event.id,
            operation="UPDATE",
        )

    # Verify the attempt itself was audited!
    events = service.list_events(tenant_context=super_admin_tc)
    mutation_events = [e for e in events if e.event_type == AuditEventType.AUDIT_MUTATION_ATTEMPT]
    assert len(mutation_events) == 2
    assert any("ILLEGAL_DELETE" in e.action for e in mutation_events)
    assert any("ILLEGAL_UPDATE" in e.action for e in mutation_events)
    assert mutation_events[0].details["is_superuser"] is True


# ==============================================================================
# 4. Override Records with 8 Mandatory Attributes & Automatic Expiry (Item 87)
# ==============================================================================


def test_override_rejected_without_reason_or_short_reason():
    """Acceptance: An override submitted without a reason or with short reason is rejected."""
    service = get_override_service()
    tc = TenantContext(tenant_id="tenant-ovr-1", user_id="ops-lead")
    future_expiry = datetime.now(UTC) + timedelta(days=7)

    # Empty reason fails
    with pytest.raises(OverrideValidationException):
        service.create_override(
            tenant_context=tc,
            req=OverrideCreateRequest(
                override_class=OverrideClass.BUDGET_THRESHOLD,
                who="ops-lead",
                what="budget.marketing.q3",
                why="",
                previous_value=10000,
                new_value=15000,
                expiry=future_expiry,
            ),
        )

    # Short trivial reason (< 20 characters) fails
    with pytest.raises(OverrideValidationException):
        service.create_override(
            tenant_context=tc,
            req=OverrideCreateRequest(
                override_class=OverrideClass.BUDGET_THRESHOLD,
                who="ops-lead",
                what="budget.marketing.q3",
                why="temporary fix",
                previous_value=10000,
                new_value=15000,
                expiry=future_expiry,
            ),
        )


def test_override_rejected_without_expiry_unless_approved():
    """Acceptance: Reject temporary override missing expiry; reject permanent override without approval."""
    service = get_override_service()
    tc = TenantContext(tenant_id="tenant-ovr-2", user_id="finops-lead")

    # Missing expiry on temporary override fails
    with pytest.raises(OverrideValidationException, match="Expiry timestamp is mandatory"):
        service.create_override(
            tenant_context=tc,
            req=OverrideCreateRequest(
                override_class=OverrideClass.BUDGET_THRESHOLD,
                who="finops-lead",
                what="budget.dev.limit",
                why="Temporary capacity increase for load test campaign",
                previous_value=5000,
                new_value=8000,
                expiry=None,
                is_permanent=False,
            ),
        )

    # Permanent override without approval fails
    with pytest.raises(PermanentOverrideNotAllowedException):
        service.create_override(
            tenant_context=tc,
            req=OverrideCreateRequest(
                override_class=OverrideClass.RATE_CARD,
                who="finops-lead",
                what="rate_card.custom_discount",
                why="Permanent corporate discount tier for dedicated clusters",
                previous_value=0.10,
                new_value=0.25,
                is_permanent=True,
                approval=None,
            ),
        )

    # Permanent override with approval succeeds
    approved_req = OverrideCreateRequest(
        override_class=OverrideClass.RATE_CARD,
        who="finops-lead",
        what="rate_card.custom_discount",
        why="Permanent corporate discount tier for dedicated clusters",
        previous_value=0.10,
        new_value=0.25,
        is_permanent=True,
        approval=OverrideApproval(
            approver_id="cfo@company.com",
            ticket_ref="CHG-99882",
            permanent_approved=True,
        ),
    )
    rec = service.create_override(tenant_context=tc, req=approved_req)
    assert rec.is_permanent is True
    assert rec.status == OverrideStatus.ACTIVE


def test_expired_override_reverts_automatically_and_reversion_is_audited():
    """Acceptance: An expired override reverts automatically and the reversion is audited."""
    service = get_override_service()
    audit_svc = get_audit_service()
    tc = TenantContext(tenant_id="tenant-ovr-3", user_id="engineer")

    # Override expired 1 hour ago
    past_expiry = datetime.now(UTC) - timedelta(hours=1)
    record = service.create_override(
        tenant_context=tc,
        req=OverrideCreateRequest(
            override_class=OverrideClass.TAG_POLICY,
            who="engineer",
            what="tag_policy.mandatory_owner",
            why="Bypass tagging rule during database emergency migration",
            previous_value="REQUIRED",
            new_value="OPTIONAL",
            expiry=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )
    # Mutate expiry directly into past for test
    record.expiry = past_expiry
    service.repository.save(record, tenant_context=tc)

    # Run automatic expiration engine
    reverted_items = service.revert_expired_overrides(tenant_context=tc)
    assert len(reverted_items) == 1
    assert reverted_items[0].id == record.id
    assert reverted_items[0].status == OverrideStatus.EXPIRED
    assert reverted_items[0].reverted_by == "system:automatic_reversion"

    # Verify audit trail contains OVERRIDE_EXPIRED
    audit_events = audit_svc.list_events(tenant_context=tc)
    expired_events = [e for e in audit_events if e.event_type == AuditEventType.OVERRIDE_EXPIRED]
    assert len(expired_events) == 1
    assert expired_events[0].resource_id == "tag_policy.mandatory_owner"
    assert expired_events[0].details["restored_value"] == "REQUIRED"


# ==============================================================================
# 5. Background Jobs Tenant Context Propagation (Item 85)
# ==============================================================================


def test_background_job_requires_explicit_tenant_context():
    """Verify background worker jobs require and propagate explicit tenant context."""
    # Job without tenant context payload fails
    with pytest.raises(MissingTenantContextException):
        execute_tenant_job(None, lambda _tc: True)

    with pytest.raises(MissingTenantContextException):
        execute_tenant_job({}, lambda _tc: True)

    with pytest.raises(MissingTenantContextException):
        execute_tenant_job({"tenant_id": ""}, lambda _tc: True)

    # Job with valid payload succeeds and passes TenantContext
    called = []

    def sample_worker_fn(tc: TenantContext, x: int) -> int:
        called.append(tc.tenant_id)
        return x * 2

    res = execute_tenant_job({"tenant_id": "tenant-worker-99"}, sample_worker_fn, 21)
    assert res == 42
    assert called == ["tenant-worker-99"]
