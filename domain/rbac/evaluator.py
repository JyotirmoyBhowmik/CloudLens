"""Scope Grant Evaluator (Prompt 11 Item 71, 72, 73).

Evaluates access permissions and declarative scope grants across all eight canonical dimensions:
1. provider (Cloud provider code: 'aws', 'azure', 'gcp', 'oci', or '*')
2. account/billing boundary (Cloud account, subscription, or billing account IDs)
3. hierarchy subtree (Cascading to descendants or leaf-only)
4. project/application (Project codes and application identifiers)
5. cost centre and business unit (Organizational cost centre and business unit codes)
6. financial data sensitivity (FULL_FINANCIAL_DETAIL, COST_TOTALS_ONLY, NON_FINANCIAL)
7. administrative (Administrative / governance capabilities)
8. resource-level allow/deny exceptions (Explicit resource inclusions/exclusions)

Enforces strict DENY-OVER-ALLOW precedence (Item 72):
- A deny grant defeats any overlapping allow grant.
"""

from domain.models.enums import FinancialSensitivity, GranteeType, GrantEffect, SystemRole
from domain.rbac.catalogue import PermissionCatalogue, get_permission_catalogue
from domain.rbac.models import AuthorizationDecision, ResourceTarget, ScopeGrant


class ScopeGrantEvaluator:
    """Evaluates scope grants across all eight scoping dimensions with deny-over-allow precedence."""

    def __init__(self, catalogue: PermissionCatalogue | None = None) -> None:
        self._catalogue = catalogue or get_permission_catalogue()

    def matches_dimension(
        self, grant: ScopeGrant, target: ResourceTarget
    ) -> tuple[bool, str | None]:
        """Evaluates whether a scope grant matches the resource target across all eight dimensions.

        Returns:
            (matches, failing_dimension_name)
        """
        # Dimension 1: Cloud Provider
        if grant.providers and "*" not in grant.providers:
            if target.provider is None:
                return False, "provider"
            allowed_providers = {p.strip().lower() for p in grant.providers}
            if target.provider.strip().lower() not in allowed_providers:
                return False, "provider"

        # Dimension 2: Account / Billing Boundary
        if grant.account_ids and "*" not in grant.account_ids:
            if target.account_id is None or target.account_id not in grant.account_ids:
                return False, "account_billing_boundary"

        # Dimension 3: Hierarchy Subtree (cascading to descendants)
        if grant.hierarchy_subtree_roots and "*" not in grant.hierarchy_subtree_roots:
            matched_hierarchy = False
            root_set = set(grant.hierarchy_subtree_roots)

            if target.hierarchy_path:
                if grant.cascade_hierarchy:
                    matched_hierarchy = any(node in root_set for node in target.hierarchy_path)
                else:
                    matched_hierarchy = target.hierarchy_path[-1] in root_set

            # Check direct fallback match against account_id or resource_id
            if not matched_hierarchy:
                if target.account_id and target.account_id in root_set:
                    matched_hierarchy = True
                elif target.resource_id and target.resource_id in root_set:
                    matched_hierarchy = True

            if not matched_hierarchy:
                return False, "hierarchy_subtree"

        # Dimension 4: Project / Application
        if grant.project_ids and "*" not in grant.project_ids:
            if target.project_id is None or target.project_id not in grant.project_ids:
                return False, "project_application"

        if grant.application_ids and "*" not in grant.application_ids:
            if target.application_id is None or target.application_id not in grant.application_ids:
                return False, "project_application"

        # Dimension 5: Cost Centre and Business Unit
        if grant.cost_centre_ids and "*" not in grant.cost_centre_ids:
            if target.cost_centre_id is None or target.cost_centre_id not in grant.cost_centre_ids:
                return False, "cost_centre_business_unit"

        if grant.business_unit_ids and "*" not in grant.business_unit_ids:
            if (
                target.business_unit_id is None
                or target.business_unit_id not in grant.business_unit_ids
            ):
                return False, "cost_centre_business_unit"

        # Dimension 6: Financial Data Sensitivity
        if target.is_financial:
            if grant.financial_sensitivity == FinancialSensitivity.NON_FINANCIAL:
                return False, "financial_data_sensitivity"

        if target.is_rate_detail:
            if grant.financial_sensitivity != FinancialSensitivity.FULL_FINANCIAL_DETAIL:
                return False, "financial_data_sensitivity"

        # Dimension 7: Administrative Scoping
        if target.is_administrative and not grant.is_administrative:
            return False, "administrative"

        # Dimension 8: Resource-Level Allow/Deny Exceptions
        if grant.effect == GrantEffect.ALLOW:
            # For ALLOW grants: explicit resource_exceptions are EXCLUDED from the allow grant
            if target.resource_id and target.resource_id in grant.resource_exceptions:
                return False, "resource_exception"
        elif grant.effect == GrantEffect.DENY:
            # For DENY grants: if exceptions list is non-empty, deny targets ONLY those resources
            if grant.resource_exceptions:
                if not (target.resource_id and target.resource_id in grant.resource_exceptions):
                    return False, "resource_exception"

        return True, None

    def evaluate_scope_grants(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        grants: list[ScopeGrant],
        target: ResourceTarget,
    ) -> AuthorizationDecision:
        """Evaluates active scope grants enforcing DENY-OVER-ALLOW precedence (Item 72).

        Rules:
        1. Any matching DENY grant immediately denies access.
        2. Otherwise, at least one matching ALLOW grant grants access.
        3. Super Admin and Platform Admin have role-level implicit allow authority
           within their boundary, but are STILL defeated by an explicit matching DENY grant.
        4. If no grant matches, access is DENIED by default.
        """
        applicable_grants = [
            g
            for g in grants
            if g.is_active
            and (g.tenant_id == tenant_id or g.tenant_id == "*")
            and (
                (g.grantee_type == GranteeType.USER and g.grantee_id == user_id)
                or (g.grantee_type == GranteeType.ROLE and g.grantee_id in role_codes)
            )
        ]

        deny_grants = [g for g in applicable_grants if g.effect == GrantEffect.DENY]
        allow_grants = [g for g in applicable_grants if g.effect == GrantEffect.ALLOW]

        # STEP 1: Strict Deny-Over-Allow (Item 72)
        for deny_grant in deny_grants:
            matches, _ = self.matches_dimension(deny_grant, target)
            if matches:
                return AuthorizationDecision(
                    allowed=False,
                    effect=GrantEffect.DENY,
                    reason=(
                        f"Access denied by deny scope grant '{deny_grant.id}' "
                        f"(grantee: {deny_grant.grantee_id}). A deny grant defeats all overlapping allow grants."
                    ),
                    matched_grant_id=deny_grant.id,
                    effective_financial_sensitivity=FinancialSensitivity.NON_FINANCIAL,
                    can_view_rates=False,
                )

        # STEP 2: Evaluate Allow Grants
        matching_allow_grants: list[ScopeGrant] = []
        for allow_grant in allow_grants:
            matches, _ = self.matches_dimension(allow_grant, target)
            if matches:
                matching_allow_grants.append(allow_grant)

        if matching_allow_grants:
            # Resolve most permissive financial sensitivity among matching allow grants
            can_view_rates = any(
                g.financial_sensitivity == FinancialSensitivity.FULL_FINANCIAL_DETAIL
                for g in matching_allow_grants
            )
            fin_sens = (
                FinancialSensitivity.FULL_FINANCIAL_DETAIL
                if can_view_rates
                else FinancialSensitivity.COST_TOTALS_ONLY
            )

            primary_grant = matching_allow_grants[0]
            return AuthorizationDecision(
                allowed=True,
                effect=GrantEffect.ALLOW,
                reason=f"Access granted by allow scope grant '{primary_grant.id}' (grantee: {primary_grant.grantee_id}).",
                matched_grant_id=primary_grant.id,
                effective_financial_sensitivity=fin_sens,
                can_view_rates=can_view_rates,
            )

        # STEP 3: Role-Level Scope Authority for Global & Tenant Admins
        if SystemRole.GLOBAL_ADMIN.value in role_codes:
            return AuthorizationDecision(
                allowed=True,
                effect=GrantEffect.ALLOW,
                reason="Access granted via Super Admin (GLOBAL_ADMIN) platform authority.",
                matched_grant_id=None,
                effective_financial_sensitivity=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
                can_view_rates=True,
            )

        if SystemRole.TENANT_ADMIN.value in role_codes:
            return AuthorizationDecision(
                allowed=True,
                effect=GrantEffect.ALLOW,
                reason="Access granted via Platform Admin (TENANT_ADMIN) tenant authority.",
                matched_grant_id=None,
                effective_financial_sensitivity=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
                can_view_rates=True,
            )

        # STEP 4: Default Deny
        return AuthorizationDecision(
            allowed=False,
            effect=GrantEffect.DENY,
            reason="Access denied: No matching allow scope grant found for the requested target context.",
            matched_grant_id=None,
            effective_financial_sensitivity=FinancialSensitivity.NON_FINANCIAL,
            can_view_rates=False,
        )

    def evaluate(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        permission_code: str,
        target: ResourceTarget | None = None,
        grants: list[ScopeGrant] | None = None,
    ) -> AuthorizationDecision:
        """Full authorization evaluation: checks permission catalogue and evaluated scope grants.

        Item 73: Separates financial detail permission from cost totals permission.
        """
        # Resolve effective permissions across assigned roles and custom roles
        all_perms: set[str] = set()
        for role_code in role_codes:
            role_def = self._catalogue.get_role(role_code, tenant_id=tenant_id)
            if role_def:
                all_perms.update(role_def.allowed_permissions)

        # 1. Base Permission Check
        if permission_code not in all_perms:
            return AuthorizationDecision(
                allowed=False,
                effect=GrantEffect.DENY,
                reason=f"Permission denied: Principal lacks required permission '{permission_code}'.",
                matched_grant_id=None,
                effective_financial_sensitivity=FinancialSensitivity.NON_FINANCIAL,
                can_view_rates=False,
            )

        # 2. Financial Detail & Rate Permission Check (Item 73)
        has_rate_perm = bool(
            {"financial:detail:read", "cost:rates:read", "pricing:read"}.intersection(all_perms)
        )

        if target and target.is_rate_detail and not has_rate_perm:
            return AuthorizationDecision(
                allowed=False,
                effect=GrantEffect.DENY,
                reason=(
                    "Access denied: Viewing granular rate details, unit costs, or charge lines "
                    "requires 'financial:detail:read' permission."
                ),
                matched_grant_id=None,
                effective_financial_sensitivity=FinancialSensitivity.COST_TOTALS_ONLY,
                can_view_rates=False,
            )

        # 3. Unscoped Target Authorization
        if target is None:
            return AuthorizationDecision(
                allowed=True,
                effect=GrantEffect.ALLOW,
                reason=f"Permission '{permission_code}' verified. No scope boundaries applied.",
                matched_grant_id=None,
                effective_financial_sensitivity=(
                    FinancialSensitivity.FULL_FINANCIAL_DETAIL
                    if has_rate_perm
                    else FinancialSensitivity.COST_TOTALS_ONLY
                ),
                can_view_rates=has_rate_perm,
            )

        # 4. Scoped Target Evaluation
        active_grants = grants or []
        decision = self.evaluate_scope_grants(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=role_codes,
            grants=active_grants,
            target=target,
        )

        # Final Rate Permission Gate: user can see rates only if BOTH scope AND permission allow
        if decision.allowed:
            decision.can_view_rates = decision.can_view_rates and has_rate_perm

        return decision
