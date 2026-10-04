"""Identity & Corporate Directory Integration Adapter (Prompt 60 / BBP Section 13.5).

Enforces:
- Inherits from BaseIntegrationAdapter with declared capabilities:
  AUTHENTICATE, HEALTH_CHECK, RESOLVE_IDENTITY, DETECT_LEAVERS.
- Resolves owners against corporate directory (SCIM, Azure AD, Okta).
- Synchronises organizational team membership.
- Proactive Leaver Detection: detects departed employees and identifies ownership gaps
  before resources become orphaned.
  Acceptance requirement: A leaver in the directory raises an ownership gap before the resource
  becomes orphaned. Automatically spawns a Prompt 51 remediation task.
"""

from __future__ import annotations

import datetime as dt
import logging

from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.models import (
    DirectoryUserProfile,
    IntegrationConfig,
    OwnershipGapFinding,
)
from domain.models.enums import (
    IntegrationCapability,
    TaskCategory,
    TaskPriority,
    TaskSource,
)
from domain.remediation.models import SubjectEntity, TaskCreateRequest
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class IdentityDirectoryAdapter(BaseIntegrationAdapter):
    """Adapter interfacing with corporate identity providers (Azure AD / Entra ID, Okta SCIM)."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        super().__init__(config, declared_capabilities)
        # Directory store: email -> DirectoryUserProfile
        self._directory_users: dict[str, DirectoryUserProfile] = {}
        # Team memberships: team_id -> set of emails
        self._team_memberships: dict[str, set[str]] = {}
        # Recorded findings: finding_id -> OwnershipGapFinding
        self._gap_findings: dict[str, OwnershipGapFinding] = {}

    @property
    def adapter_name(self) -> str:
        return f"{self.config.custom_attributes.get('idp_type', 'azure_ad').lower()}_directory"

    def default_capabilities(self) -> set[IntegrationCapability]:
        return {
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
            IntegrationCapability.RESOLVE_IDENTITY,
            IntegrationCapability.DETECT_LEAVERS,
        }

    def sync_directory_users(
        self,
        users: list[DirectoryUserProfile],
        *,
        tenant_context: TenantContext,
    ) -> dict[str, int]:
        """Loads and synchronises directory users and team allocations."""

        def _action() -> dict[str, int]:
            active_count = 0
            terminated_count = 0

            for u in users:
                norm_email = u.email.strip().lower()
                self._directory_users[norm_email] = u

                if u.team_id:
                    self._team_memberships.setdefault(u.team_id, set()).add(norm_email)

                if u.is_active and u.employment_status.upper() == "ACTIVE":
                    active_count += 1
                else:
                    terminated_count += 1

            logger.info(
                "Synchronised %d directory users (%d active, %d departed/inactive) for tenant '%s'.",
                len(users),
                active_count,
                terminated_count,
                tenant_context.tenant_id,
            )
            return {"active_users": active_count, "terminated_users": terminated_count}

        return self.execute_with_resilience(
            IntegrationCapability.RESOLVE_IDENTITY,
            "sync_directory_users",
            _action,
        )

    def resolve_user(self, email: str) -> DirectoryUserProfile | None:
        """Resolves an owner identity against the cached directory."""
        return self._directory_users.get(email.strip().lower())

    def get_team_members(self, team_id: str) -> set[str]:
        """Returns email addresses associated with a team."""
        return set(self._team_memberships.get(team_id, set()))

    def detect_leavers(
        self,
        resource_ownership_map: dict[str, str],
        scope_ownership_map: dict[str, str],
        *,
        tenant_context: TenantContext,
        remediation_service: RemediationService | None = None,
        fallback_assignee: str = "cloudops-triage@company.internal",
    ) -> list[OwnershipGapFinding]:
        """Scans for departed employees and surfaces immediate ownership gaps.

        Acceptance requirement:
        - A leaver in the directory raises an ownership gap before the resource becomes orphaned.
        - Automatically creates an assigned Prompt 51 remediation task.
        """

        def _action() -> list[OwnershipGapFinding]:
            findings: list[OwnershipGapFinding] = []

            # 1. Identify all leavers in directory
            leavers: dict[str, DirectoryUserProfile] = {
                email: user
                for email, user in self._directory_users.items()
                if (not user.is_active)
                or (user.employment_status.upper() in {"TERMINATED", "DEPARTED", "DISABLED"})
            }

            if not leavers:
                logger.info("No departed employees detected during directory scan.")
                return findings

            # 2. Invert ownership maps to find resources/scopes owned by leavers
            for leaver_email, leaver_profile in leavers.items():
                owned_resources = [
                    res_id
                    for res_id, owner in resource_ownership_map.items()
                    if owner.strip().lower() == leaver_email
                ]
                owned_scopes = [
                    scope_id
                    for scope_id, owner in scope_ownership_map.items()
                    if owner.strip().lower() == leaver_email
                ]

                # If the leaver owns anything, we have a critical ownership gap!
                if owned_resources or owned_scopes:
                    finding = OwnershipGapFinding(
                        tenant_id=tenant_context.tenant_id,
                        former_owner_email=leaver_email,
                        former_owner_name=leaver_profile.display_name,
                        termination_date=leaver_profile.termination_date
                        or dt.datetime.now(dt.UTC),
                        affected_resource_ids=owned_resources,
                        affected_scopes=owned_scopes,
                    )

                    # 3. Create assigned Prompt 51 RemediationTask if service provided
                    if remediation_service:
                        subject_id = owned_resources[0] if owned_resources else owned_scopes[0]
                        subject_type = "resource" if owned_resources else "scope"
                        req = TaskCreateRequest(
                            source=TaskSource.UNOWNED_RESOURCE,
                            category=TaskCategory.UNOWNED_RESOURCE,
                            priority=TaskPriority.HIGH,
                            title=f"Ownership Gap: Departed employee {leaver_email} owns active assets",
                            description=(
                                f"Former employee {leaver_profile.display_name} ({leaver_email}) has departed "
                                f"(status: {leaver_profile.employment_status}).\n"
                                f"Active owned resources: {len(owned_resources)} ({', '.join(owned_resources[:5])})\n"
                                f"Active owned scopes: {len(owned_scopes)} ({', '.join(owned_scopes[:5])})\n"
                                f"Action required: Reassign ownership before resources become untracked orphans."
                            ),
                            subject_entity=SubjectEntity(
                                entity_type=subject_type,
                                entity_id=subject_id,
                                entity_name=f"Assets owned by {leaver_email}",
                            ),
                            assignee_id=fallback_assignee,
                            estimated_saving=0.0,
                        )
                        task = remediation_service.create_task(
                            req=req,
                            actor="directory-sync",
                            tenant_context=tenant_context,
                        )
                        finding.remediation_task_id = task.id

                    self._gap_findings[finding.finding_id] = finding
                    findings.append(finding)

                    logger.warning(
                        "Proactive Leaver Detection: Raised ownership gap '%s' for departed user '%s' "
                        "(affected resources: %d, scopes: %d). Remediation task: '%s'.",
                        finding.finding_id,
                        leaver_email,
                        len(owned_resources),
                        len(owned_scopes),
                        finding.remediation_task_id,
                    )

            return findings

        return self.execute_with_resilience(
            IntegrationCapability.DETECT_LEAVERS,
            "detect_leavers",
            _action,
        )

    def get_findings(self, tenant_id: str | None = None) -> list[OwnershipGapFinding]:
        """Returns all recorded ownership gap findings."""
        if not tenant_id:
            return list(self._gap_findings.values())
        return [f for f in self._gap_findings.values() if f.tenant_id == tenant_id]
