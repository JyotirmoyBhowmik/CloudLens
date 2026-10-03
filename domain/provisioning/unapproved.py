"""Unapproved Deployment Detector (Prompt 55).

Enforces:
- Scans newly inventoried cloud resources in gated scopes.
- Identifies unapproved deployments lacking linked or approved provisioning requests.
- Raises governance exception and creates assigned remediation task.
- Plainly discloses that the platform operates with read-only credentials and
  cannot technically block deployment (ADVISORY_GATE_NOTICE).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from domain.provisioning.models import (
    ADVISORY_GATE_NOTICE,
    ProvisioningRequest,
    ProvisioningRequestStatus,
    UnapprovedDeploymentFinding,
)
from domain.rules.monetary import round_currency

logger = logging.getLogger(__name__)


class UnapprovedDeploymentDetector:
    """Detects resources deployed in gated scopes without prior approved provisioning requests."""

    def detect_unapproved(
        self,
        tenant_id: str,
        inventoried_resources: list[dict[str, Any]],
        active_requests: list[ProvisioningRequest],
        gated_scopes: set[str],
    ) -> list[UnapprovedDeploymentFinding]:
        """Evaluates inventory against approved/linked provisioning requests.

        A resource is flagged as an unapproved deployment if:
        1. Its scope_code is in gated_scopes.
        2. It is NOT linked to any approved provisioning request.
        """
        # Build set of approved/linked resource IDs and request IDs
        linked_resource_ids = {
            r.linked_resource_id
            for r in active_requests
            if r.linked_resource_id
            and r.status
            in {ProvisioningRequestStatus.APPROVED, ProvisioningRequestStatus.LINKED_TO_RESOURCE}
        }

        gated_scopes_lower = {s.lower() for s in gated_scopes}

        findings: list[UnapprovedDeploymentFinding] = []

        for res in inventoried_resources:
            res_id = str(res.get("resource_id", ""))
            scope_code = str(res.get("scope_code", "")).strip()

            if not scope_code or scope_code.lower() not in gated_scopes_lower:
                # Not a gated scope, skip
                continue

            if res_id in linked_resource_ids:
                # Legitimate approved deployment
                continue

            monthly_cost = Decimal(str(res.get("monthly_cost", res.get("cost", "100.00"))))
            gov_exc_id = f"govex-{uuid.uuid4().hex[:8]}"
            rem_task_id = f"rem-{uuid.uuid4().hex[:8]}"

            finding = UnapprovedDeploymentFinding(
                finding_id=f"unapp-{uuid.uuid4().hex[:8]}",
                resource_id=res_id,
                resource_name=str(res.get("resource_name", res.get("name", res_id))),
                provider=str(res.get("provider", "aws")),
                service=str(res.get("service", "compute")),
                scope_code=scope_code,
                estimated_monthly_cost=round_currency(monthly_cost),
                governance_exception_id=gov_exc_id,
                remediation_task_id=rem_task_id,
                advisory_disclaimer=ADVISORY_GATE_NOTICE,
            )
            findings.append(finding)

            logger.warning(
                "Unapproved deployment detected in tenant %s: resource_id=%s in gated scope=%s (exception=%s, task=%s)",
                tenant_id,
                res_id,
                scope_code,
                gov_exc_id,
                rem_task_id,
            )

        return findings
