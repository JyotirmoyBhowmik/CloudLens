"""Real-DB Integration Test for Direct SQL Policy Findings Count (Prompt P07).

DONE WHEN Proof:
[ ] Findings count equals SELECT COUNT(*)
- Never hard-coded findings counts.
- Strict direct SQL query (SELECT COUNT(*)) via SqlPolicyRepository.count_findings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from db.session import get_tenant_session
from domain.models.enums import FindingLifecycleStatus, PolicyCategory, PolicyMode, PolicySeverity
from domain.policy.models import PolicyFinding
from domain.policy.repository import (
    SqlPolicyRepository,
    get_policy_repository,
    reset_policy_repository,
)
from domain.tenant.context import TenantContext


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_findings_count_equals_select_count() -> None:
    """Verifies that repository findings count strictly executes direct SQL SELECT COUNT(*),

    matching the exact row count in policy_findings and updating dynamically without hard-coded numbers.
    """
    tenant_id = f"tenant-p07-count-{uuid.uuid4().hex[:6]}"
    tc = TenantContext(
        tenant_id=tenant_id,
        user_id="user-compliance-officer",
        roles=["TENANT_ADMIN"],
        is_break_glass=False,
    )

    reset_policy_repository()
    repo = get_policy_repository()
    assert not repo.is_in_memory, "Must be backed by PostgreSQL, not InMemory fake"

    # Step 1: Initial empty state count in SQL
    async with get_tenant_session(tenant_id) as sess:
        raw_res = await sess.execute(
            text("SELECT COUNT(*) FROM policy_findings WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        sql_count_initial = raw_res.scalar() or 0

    repo_count_initial = repo.count_findings(tenant_context=tc)
    assert repo_count_initial == 0, f"Expected 0 findings, got {repo_count_initial}"
    assert repo_count_initial == sql_count_initial, "Repo count must match SELECT COUNT(*) initially"

    # Step 2: Insert 3 findings
    f1 = PolicyFinding(
        id=f"fnd-{uuid.uuid4().hex[:8]}",
        policy_id="pol-encryption-at-rest",
        policy_version=1,
        entity_id="vol-storage-01",
        lifecycle_status=FindingLifecycleStatus.OPEN,
        severity=PolicySeverity.HIGH,
        category=PolicyCategory.TAGGING,
        mode=PolicyMode.ENFORCE,
        condition_summary="Unencrypted EBS Volume",
        first_detected_at=datetime.now(UTC),
    )
    f2 = PolicyFinding(
        id=f"fnd-{uuid.uuid4().hex[:8]}",
        policy_id="pol-public-ingress-ssh",
        policy_version=1,
        entity_id="sg-security-core",
        lifecycle_status=FindingLifecycleStatus.OPEN,
        severity=PolicySeverity.CRITICAL,
        category=PolicyCategory.TAGGING,
        mode=PolicyMode.ENFORCE,
        condition_summary="Public SSH Port 22 Open",
        first_detected_at=datetime.now(UTC),
    )
    f3 = PolicyFinding(
        id=f"fnd-{uuid.uuid4().hex[:8]}",
        policy_id="pol-mandatory-tags",
        policy_version=1,
        entity_id="res-vm-dev-01",
        lifecycle_status=FindingLifecycleStatus.CLEARED,
        severity=PolicySeverity.LOW,
        category=PolicyCategory.TAGGING,
        mode=PolicyMode.ENFORCE,
        condition_summary="Missing Environment Tag",
        first_detected_at=datetime.now(UTC),
    )

    repo.save_finding(f1, tenant_context=tc)
    repo.save_finding(f2, tenant_context=tc)
    repo.save_finding(f3, tenant_context=tc)

    # Step 3: Verify total count equals SELECT COUNT(*)
    async with get_tenant_session(tenant_id) as sess:
        raw_res = await sess.execute(
            text("SELECT COUNT(*) FROM policy_findings WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        sql_count_total = raw_res.scalar() or 0

    repo_count_total = repo.count_findings(tenant_context=tc)
    assert sql_count_total == 3, f"Expected 3 in DB, found {sql_count_total}"
    assert repo_count_total == sql_count_total, f"Repo count ({repo_count_total}) != SELECT COUNT(*) ({sql_count_total})"

    # Step 4: Verify status filtered count equals SELECT COUNT(*) WHERE lifecycle_status = 'OPEN'
    async with get_tenant_session(tenant_id) as sess:
        raw_res = await sess.execute(
            text("SELECT COUNT(*) FROM policy_findings WHERE tenant_id = :tid AND lifecycle_status = 'OPEN';"),
            {"tid": tenant_id},
        )
        sql_count_open = raw_res.scalar() or 0

    repo_count_open = repo.count_findings(tenant_context=tc, status="OPEN")
    assert sql_count_open == 2, f"Expected 2 OPEN in DB, found {sql_count_open}"
    assert repo_count_open == sql_count_open, f"Repo OPEN count ({repo_count_open}) != SELECT COUNT(*) ({sql_count_open})"

    # Step 5: Delete one finding and verify count reduces immediately via SQL
    repo.delete_finding(f1.id, tenant_context=tc)

    async with get_tenant_session(tenant_id) as sess:
        raw_res = await sess.execute(
            text("SELECT COUNT(*) FROM policy_findings WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        sql_count_after_del = raw_res.scalar() or 0

    repo_count_after_del = repo.count_findings(tenant_context=tc)
    assert sql_count_after_del == 2, f"Expected 2 after delete in DB, found {sql_count_after_del}"
    assert repo_count_after_del == sql_count_after_del, "Repo count must equal SELECT COUNT(*) after deletion"
