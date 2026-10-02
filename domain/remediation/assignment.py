"""Ownership Assignment Resolver for Remediation Tasks (Prompt 51).

Enforces:
- Prompt 08 (Ownership Precedence Chain) and Prompt 46 (Owner Master):
  1. Technical Owner first
  2. Scope Owner second
  3. Application Owner third
  4. Fallback Queue fourth
  5. Governance Exception if unresolvable (never leave a task floating unassigned).
"""

from __future__ import annotations

import logging
from typing import Any

from domain.models.enums import TaskAssignmentRule
from domain.models.exceptions import NoResolvableAssigneeException
from domain.remediation.models import SubjectEntity
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)

# Standard tags inspected for technical ownership
TECHNICAL_OWNER_TAG_KEYS = ("technical-owner", "technical_owner", "owner", "owner-email", "contact")


class AssignmentResolver:
    """Resolves task accountability following the deterministic 4-tier ownership hierarchy."""

    def __init__(
        self,
        master_data_service: MasterDataService | None = None,
        default_fallback_queue: str = "queue-finops-operations",
    ) -> None:
        self.master_data_service = master_data_service or get_master_data_service()
        self.default_fallback_queue = default_fallback_queue

    def resolve(
        self,
        subject: SubjectEntity,
        *,
        resource: Any = None,
        tags: dict[str, str] | None = None,
        scope_owner_id: str | None = None,
        app_owner_id: str | None = None,
        fallback_queue_id: str | None = None,
        allow_unassigned_exception: bool = False,
    ) -> tuple[str, str, TaskAssignmentRule]:
        """Resolves the accountable assignee for a remediation task.

        Returns:
            Tuple of (assignee_id, assignee_type, rule_used).

        Raises:
            NoResolvableAssigneeException if nothing resolves and fallback queue is unavailable.
        """
        # ----------------------------------------------------------------------
        # Tier 1: Technical Owner
        # ----------------------------------------------------------------------
        # 1.a Direct attribute on resource
        if resource is not None:
            tech_owner = getattr(resource, "technical_owner_id", None) or getattr(
                resource, "owner_id", None
            )
            if tech_owner and str(tech_owner).strip():
                return str(tech_owner).strip(), "USER", TaskAssignmentRule.TECHNICAL_OWNER

        # 1.b Tags on resource or payload
        if tags:
            for k, v in tags.items():
                if k.lower() in TECHNICAL_OWNER_TAG_KEYS and v and str(v).strip():
                    return str(v).strip(), "USER", TaskAssignmentRule.TECHNICAL_OWNER

        # 1.c Check Owner Master (Prompt 46) for exact match
        try:
            owner_records = self.master_data_service.list_records("OWNER_TEAM")
            for rec in owner_records:
                attrs = rec.attributes or {}
                if attrs.get("role") == "TECHNICAL_OWNER" and rec.code == subject.entity_id:
                    return rec.code, "TEAM", TaskAssignmentRule.TECHNICAL_OWNER
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # Tier 2: Scope Owner
        # ----------------------------------------------------------------------
        if scope_owner_id and scope_owner_id.strip():
            return scope_owner_id.strip(), "USER", TaskAssignmentRule.SCOPE_OWNER

        # ----------------------------------------------------------------------
        # Tier 3: Application Owner
        # ----------------------------------------------------------------------
        if app_owner_id and app_owner_id.strip():
            return app_owner_id.strip(), "USER", TaskAssignmentRule.APPLICATION_OWNER

        # ----------------------------------------------------------------------
        # Tier 4: Configured Fallback Queue
        # ----------------------------------------------------------------------
        queue = fallback_queue_id if fallback_queue_id is not None else self.default_fallback_queue
        if queue and queue.strip() and not allow_unassigned_exception:
            return queue.strip(), "QUEUE", TaskAssignmentRule.FALLBACK_QUEUE

        # ----------------------------------------------------------------------
        # Tier 5: Governance Exception (No Unassigned Tasks Permitted)
        # ----------------------------------------------------------------------
        raise NoResolvableAssigneeException(
            subject.entity_id,
            details=f"Entity '{subject.entity_name or subject.entity_id}' has no technical owner, "
            f"scope owner, or application owner, and fallback queue is unset.",
        )
