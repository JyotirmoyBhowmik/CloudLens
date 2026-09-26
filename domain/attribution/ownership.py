"""Ownership Resolution Service with Deterministic Precedence Chain (Prompt 08 Item 55, 56).

Enforces:
1. 6-level deterministic precedence chain:
   - manual assignment on the resource
   - ownership tag policy
   - inherited tag from parent scope
   - scope ownership rule
   - application membership rule
   - Unresolved fallback
2. Always record and expose which rule produced the result.
3. Make Unresolved a governance exception — never silently assign an owner,
   and never leave ownership blank without raising/recording the exception.
4. Do not infer ownership from a name pattern without an explicit configured rule.
"""

from datetime import UTC, datetime

from domain.attribution.models import (
    CuratedField,
    OwnershipResolutionResult,
    OwnershipResolutionRule,
)
from domain.models.enums import OriginType
from domain.models.exceptions import UnresolvedOwnershipException
from domain.models.inventory import Application, Resource, Tag
from domain.models.scope import Scope
from normalisation.tags.models import NormalizedTag, TagSourceLevel
from normalisation.tags.normaliser import TagNormalisationService

# Configured default ownership tag keys (in normalized form)
DEFAULT_OWNERSHIP_TAG_KEYS = [
    "owner",
    "owner-email",
    "contact",
    "technical-owner",
    "business-owner",
    "created-by",
]


class OwnershipResolutionService:
    """Evaluates and attributes workload accountability across the enterprise."""

    def __init__(
        self,
        tag_normaliser: TagNormalisationService | None = None,
        ownership_tag_keys: list[str] | None = None,
        default_raise_on_unresolved: bool = False,
    ) -> None:
        self.tag_normaliser = tag_normaliser or TagNormalisationService()
        self.ownership_tag_keys = ownership_tag_keys or DEFAULT_OWNERSHIP_TAG_KEYS
        self.default_raise_on_unresolved = default_raise_on_unresolved

    def resolve_ownership(
        self,
        resource: Resource,
        tags: list[NormalizedTag] | None = None,
        parent_scope: Scope | None = None,
        scope_owner_map: dict[str, str] | None = None,
        application: Application | None = None,
        curated_fields: set[str] | None = None,
        raise_on_unresolved: bool | None = None,
    ) -> OwnershipResolutionResult:
        """Resolves resource ownership using the 6-level deterministic precedence chain.

        Precedence order:
        1. Manual assignment on the resource (Curated)
        2. Ownership tag policy (Direct tag on resource)
        3. Inherited tag from parent scope hierarchy
        4. Scope ownership rule
        5. Application membership rule
        6. Unresolved (Governance exception)
        """
        _ = parent_scope
        should_raise = (
            raise_on_unresolved
            if raise_on_unresolved is not None
            else self.default_raise_on_unresolved
        )

        # ------------------------------------------------------------------
        # Tier 1: Manual Assignment on the Resource
        # ------------------------------------------------------------------
        is_curated_owner = False
        if curated_fields and CuratedField.OWNER.value in curated_fields:
            is_curated_owner = True
        elif (
            resource.source_provenance
            and resource.source_provenance.origin_type == OriginType.CURATED
        ):
            is_curated_owner = True

        if resource.owner_id and is_curated_owner:
            return OwnershipResolutionResult(
                resource_id=resource.id,
                owner_id=resource.owner_id,
                owner_email=resource.owner_id if "@" in resource.owner_id else None,
                winning_rule=OwnershipResolutionRule.MANUAL_ASSIGNMENT,
                rule_description=(
                    f"Direct manual curation assigned to resource '{resource.name}' ({resource.id})"
                ),
                is_resolved=True,
                resolved_at=datetime.now(UTC),
            )

        # Normalize tags if raw domain Tag objects provided
        norm_tags: list[NormalizedTag] = []
        if tags is not None:
            norm_tags = tags
        elif resource.tags:
            for t in resource.tags:
                raw_t = from_tag_to_raw(t)
                norm_tag = self.tag_normaliser.normalise_tag(raw=raw_t)
                norm_tags.append(norm_tag)

        # ------------------------------------------------------------------
        # Tier 2: Ownership Tag Policy (Direct Tag on Resource)
        # ------------------------------------------------------------------
        for tag in norm_tags:
            if not tag.inherited and tag.source_level == TagSourceLevel.RESOURCE:
                if tag.normalized_key.lower() in self.ownership_tag_keys and tag.value.strip():
                    val = tag.value.strip()
                    return OwnershipResolutionResult(
                        resource_id=resource.id,
                        owner_id=val,
                        owner_email=val if "@" in val else None,
                        winning_rule=OwnershipResolutionRule.OWNERSHIP_TAG,
                        rule_description=(
                            f"Matched direct resource tag '{tag.normalized_key}: {val}'"
                        ),
                        is_resolved=True,
                        resolved_at=datetime.now(UTC),
                    )

        # ------------------------------------------------------------------
        # Tier 3: Inherited Tag from Parent Scope Hierarchy
        # ------------------------------------------------------------------
        for tag in norm_tags:
            if tag.inherited or tag.source_level != TagSourceLevel.RESOURCE:
                if tag.normalized_key.lower() in self.ownership_tag_keys and tag.value.strip():
                    val = tag.value.strip()
                    return OwnershipResolutionResult(
                        resource_id=resource.id,
                        owner_id=val,
                        owner_email=val if "@" in val else None,
                        winning_rule=OwnershipResolutionRule.INHERITED_TAG,
                        rule_description=(
                            f"Matched inherited scope tag '{tag.normalized_key}: {val}' "
                            f"from level {tag.source_level.value}"
                        ),
                        is_resolved=True,
                        resolved_at=datetime.now(UTC),
                    )

        # ------------------------------------------------------------------
        # Tier 4: Scope Ownership Rule
        # ------------------------------------------------------------------
        if scope_owner_map and resource.scope_id in scope_owner_map:
            scope_owner = scope_owner_map[resource.scope_id].strip()
            if scope_owner:
                return OwnershipResolutionResult(
                    resource_id=resource.id,
                    owner_id=scope_owner,
                    owner_email=scope_owner if "@" in scope_owner else None,
                    winning_rule=OwnershipResolutionRule.SCOPE_RULE,
                    rule_description=(
                        f"Scope ownership rule on parent scope '{resource.scope_id}'"
                    ),
                    is_resolved=True,
                    resolved_at=datetime.now(UTC),
                )

        # ------------------------------------------------------------------
        # Tier 5: Application Membership Rule
        # ------------------------------------------------------------------
        if resource.application_id and application and application.id == resource.application_id:
            if application.owner_id and application.owner_id.strip():
                app_owner = application.owner_id.strip()
                return OwnershipResolutionResult(
                    resource_id=resource.id,
                    owner_id=app_owner,
                    owner_email=app_owner if "@" in app_owner else None,
                    winning_rule=OwnershipResolutionRule.APPLICATION_RULE,
                    rule_description=(
                        f"Application membership rule for application '{application.name}' "
                        f"({application.code}) owned by '{app_owner}'"
                    ),
                    is_resolved=True,
                    resolved_at=datetime.now(UTC),
                )

        # ------------------------------------------------------------------
        # Tier 6: Unresolved (Governance Exception)
        # ------------------------------------------------------------------
        # Never silently assign an owner, never leave blank without raising exception.
        # Do not infer ownership from name pattern without configured rule.
        exception_msg = (
            f"UNRESOLVED_OWNERSHIP: Resource '{resource.id}' ('{resource.name}') in scope "
            f"'{resource.scope_id}' failed all 5 ownership tiers. Manual curation or policy "
            "tagging required. Ownership inference from name patterns is strictly forbidden."
        )

        if should_raise:
            raise UnresolvedOwnershipException(exception_msg)

        return OwnershipResolutionResult(
            resource_id=resource.id,
            owner_id=None,
            owner_email=None,
            winning_rule=OwnershipResolutionRule.UNRESOLVED,
            rule_description="No matching ownership rule in 6-level precedence chain.",
            is_resolved=False,
            resolved_at=datetime.now(UTC),
            governance_exception=exception_msg,
        )


def from_tag_to_raw(tag: Tag):
    """Converts a domain Tag model to RawTagInput for normalisation."""
    from normalisation.tags.models import RawTagInput, TagSourceLevel

    source_lvl = TagSourceLevel.RESOURCE if not tag.inherited else TagSourceLevel.SUBSCRIPTION
    return RawTagInput(
        key=tag.key,
        value=tag.value,
        source_level=source_lvl,
        inherited=tag.inherited,
    )
