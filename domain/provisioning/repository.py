"""Thread-Safe Repository for Cost-Aware Provisioning Gate (Prompt 55).

Enforces:
- Tenant isolation across all provisioning entities.
- Thread-safe in-memory storage with reentrant locks.
- Estimates, requests, gate triggers, AM-12 rules, tracking records, and findings.
"""

from __future__ import annotations

import logging
import threading

from domain.provisioning.models import (
    ApprovalAuthorityRule,
    BypassRecord,
    EstimateVsActualTracking,
    GateTriggerRule,
    ProvisioningRequest,
    SavedEstimate,
    UnapprovedDeploymentFinding,
)

logger = logging.getLogger(__name__)


class ProvisioningRepository:
    """Thread-safe tenant-isolated repository for provisioning entities."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._estimates: dict[tuple[str, str], SavedEstimate] = {}
        self._requests: dict[tuple[str, str], ProvisioningRequest] = {}
        self._gate_rules: dict[tuple[str, str], GateTriggerRule] = {}
        self._authority_rules: dict[tuple[str, str], ApprovalAuthorityRule] = {}
        self._trackings: dict[tuple[str, str], EstimateVsActualTracking] = {}
        self._bypass_records: dict[tuple[str, str], BypassRecord] = {}
        self._findings: dict[tuple[str, str], UnapprovedDeploymentFinding] = {}

    def reset(self) -> None:
        """Clears all stored records (useful for test isolation)."""
        with self._lock:
            self._estimates.clear()
            self._requests.clear()
            self._gate_rules.clear()
            self._authority_rules.clear()
            self._trackings.clear()
            self._bypass_records.clear()
            self._findings.clear()

    # --------------------------------------------------------------------------
    # 1. Saved Estimates
    # --------------------------------------------------------------------------
    def save_estimate(self, estimate: SavedEstimate) -> SavedEstimate:
        with self._lock:
            key = (estimate.tenant_id, estimate.estimate_id)
            self._estimates[key] = estimate
            return estimate

    def get_estimate(self, tenant_id: str, estimate_id: str) -> SavedEstimate | None:
        with self._lock:
            return self._estimates.get((tenant_id, estimate_id))

    def list_estimates(self, tenant_id: str) -> list[SavedEstimate]:
        with self._lock:
            return [e for (t, _), e in self._estimates.items() if t == tenant_id]

    # --------------------------------------------------------------------------
    # 2. Provisioning Requests
    # --------------------------------------------------------------------------
    def save_request(self, request: ProvisioningRequest) -> ProvisioningRequest:
        with self._lock:
            key = (request.tenant_id, request.request_id)
            self._requests[key] = request
            return request

    def get_request(self, tenant_id: str, request_id: str) -> ProvisioningRequest | None:
        with self._lock:
            return self._requests.get((tenant_id, request_id))

    def list_requests(
        self,
        tenant_id: str,
        status: str | None = None,
        scope_code: str | None = None,
    ) -> list[ProvisioningRequest]:
        with self._lock:
            res = [r for (t, _), r in self._requests.items() if t == tenant_id]
            if status:
                res = [r for r in res if r.status.value == status]
            if scope_code:
                res = [r for r in res if r.target_scope.lower() == scope_code.lower()]
            return res

    # --------------------------------------------------------------------------
    # 3. Gate Trigger Rules
    # --------------------------------------------------------------------------
    def save_gate_rule(self, tenant_id: str, rule: GateTriggerRule) -> GateTriggerRule:
        with self._lock:
            self._gate_rules[(tenant_id, rule.rule_id)] = rule
            return rule

    def list_gate_rules(self, tenant_id: str) -> list[GateTriggerRule]:
        with self._lock:
            return [r for (t, _), r in self._gate_rules.items() if t == tenant_id]

    # --------------------------------------------------------------------------
    # 4. AM-12 Authority Rules
    # --------------------------------------------------------------------------
    def save_authority_rule(
        self, tenant_id: str, rule: ApprovalAuthorityRule
    ) -> ApprovalAuthorityRule:
        with self._lock:
            self._authority_rules[(tenant_id, rule.rule_id)] = rule
            return rule

    def list_authority_rules(self, tenant_id: str) -> list[ApprovalAuthorityRule]:
        with self._lock:
            return [r for (t, _), r in self._authority_rules.items() if t == tenant_id]

    # --------------------------------------------------------------------------
    # 5. Tracking & Reconciliation Records
    # --------------------------------------------------------------------------
    def save_tracking(
        self, tenant_id: str, tracking: EstimateVsActualTracking
    ) -> EstimateVsActualTracking:
        with self._lock:
            self._trackings[(tenant_id, tracking.tracking_id)] = tracking
            return tracking

    def get_tracking_by_request_id(
        self, tenant_id: str, request_id: str
    ) -> EstimateVsActualTracking | None:
        with self._lock:
            for (t, _), tr in self._trackings.items():
                if t == tenant_id and tr.request_id == request_id:
                    return tr
            return None

    def list_trackings(self, tenant_id: str) -> list[EstimateVsActualTracking]:
        with self._lock:
            return [tr for (t, _), tr in self._trackings.items() if t == tenant_id]

    # --------------------------------------------------------------------------
    # 6. Bypass Records
    # --------------------------------------------------------------------------
    def save_bypass(self, tenant_id: str, bypass: BypassRecord) -> BypassRecord:
        with self._lock:
            self._bypass_records[(tenant_id, bypass.bypass_id)] = bypass
            return bypass

    def list_bypass_records(self, tenant_id: str) -> list[BypassRecord]:
        with self._lock:
            return [b for (t, _), b in self._bypass_records.items() if t == tenant_id]

    # --------------------------------------------------------------------------
    # 7. Unapproved Deployment Findings
    # --------------------------------------------------------------------------
    def save_finding(
        self, tenant_id: str, finding: UnapprovedDeploymentFinding
    ) -> UnapprovedDeploymentFinding:
        with self._lock:
            self._findings[(tenant_id, finding.finding_id)] = finding
            return finding

    def list_findings(self, tenant_id: str) -> list[UnapprovedDeploymentFinding]:
        with self._lock:
            return [f for (t, _), f in self._findings.items() if t == tenant_id]


_GLOBAL_PROVISIONING_REPOSITORY: ProvisioningRepository | None = None


def get_provisioning_repository() -> ProvisioningRepository:
    """Singleton provider for ProvisioningRepository."""
    global _GLOBAL_PROVISIONING_REPOSITORY
    if _GLOBAL_PROVISIONING_REPOSITORY is None:
        _GLOBAL_PROVISIONING_REPOSITORY = ProvisioningRepository()
    return _GLOBAL_PROVISIONING_REPOSITORY


def reset_provisioning_repository() -> None:
    """Resets the repository singleton."""
    global _GLOBAL_PROVISIONING_REPOSITORY
    if _GLOBAL_PROVISIONING_REPOSITORY is not None:
        _GLOBAL_PROVISIONING_REPOSITORY.reset()
    _GLOBAL_PROVISIONING_REPOSITORY = None
