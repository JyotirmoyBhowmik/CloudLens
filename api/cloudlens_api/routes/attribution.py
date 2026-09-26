"""CloudLens Attribution, Tag Normalisation, and Allocation REST API (Prompt 08).

Enforces:
- POST /api/v1/attribution/tags/normalise: Standardizes tag keys and parses OCI namespaces.
- POST /api/v1/attribution/ownership/resolve: Evaluates 6-level precedence ownership chain.
- POST /api/v1/attribution/allocation/rules: Registers allocation rule (validates 100% split).
- GET /api/v1/attribution/allocation/rules: Lists active allocation rules.
- POST /api/v1/attribution/allocation/evaluate: Evaluates cost facts and explains winning rules.
- POST /api/v1/attribution/allocation/aggregate: Aggregates spend with strict UNALLOCATED visibility.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from domain.attribution.aggregation import (
    AggregationSummary,
    AllocationAggregationService,
)
from domain.attribution.allocation import AllocationRuleEngine
from domain.attribution.curated import CuratedFieldProtectionService
from domain.attribution.models import (
    AllocatedCostRow,
    AllocationRule,
    OwnershipResolutionResult,
)
from domain.attribution.ownership import OwnershipResolutionService
from domain.models.exceptions import (
    InvalidSplitRuleException,
    UnresolvedOwnershipException,
)
from domain.models.facts import CostFact
from domain.models.inventory import Application, Resource
from domain.models.scope import Scope
from normalisation.tags.models import (
    NormalizedTag,
    RawTagInput,
    TagKeyConvention,
)
from normalisation.tags.normaliser import TagNormalisationService

router = APIRouter(prefix="/api/v1/attribution", tags=["Attribution & Allocation"])

# Shared services
_tag_normaliser = TagNormalisationService()
_ownership_service = OwnershipResolutionService(tag_normaliser=_tag_normaliser)
_allocation_engine = AllocationRuleEngine()
_aggregation_service = AllocationAggregationService()
_curated_service = CuratedFieldProtectionService()


# ------------------------------------------------------------------------------
# Tag Normalisation Endpoints
# ------------------------------------------------------------------------------


class NormaliseTagsRequest(BaseModel):
    tags: list[RawTagInput] = Field(..., description="List of raw tags to normalise")
    convention: TagKeyConvention | None = Field(
        default=None, description="Optional custom key convention policy"
    )


@router.post("/tags/normalise", response_model=list[NormalizedTag])
def normalise_tags_endpoint(payload: NormaliseTagsRequest) -> list[NormalizedTag]:
    """Normalises raw cloud tags into standardized canonical representation.

    Retains original keys verbatim, extracts OCI defined-tag namespaces separately,
    and tracks source hierarchy level.
    """
    return _tag_normaliser.normalise_tags(payload.tags, convention=payload.convention)


# ------------------------------------------------------------------------------
# Ownership Resolution Endpoints
# ------------------------------------------------------------------------------


class ResolveOwnershipRequest(BaseModel):
    resource: Resource = Field(..., description="Target Resource entity")
    tags: list[NormalizedTag] | None = Field(default=None)
    parent_scope: Scope | None = Field(default=None)
    scope_owner_map: dict[str, str] | None = Field(default=None)
    application: Application | None = Field(default=None)
    raise_on_unresolved: bool = Field(default=False)


@router.post("/ownership/resolve", response_model=OwnershipResolutionResult)
def resolve_ownership_endpoint(payload: ResolveOwnershipRequest) -> OwnershipResolutionResult:
    """Evaluates the 6-level deterministic ownership precedence chain.

    Order: manual assignment -> ownership tag -> inherited scope tag -> scope rule ->
    application rule -> Unresolved. Always exposes winning rule.
    """
    try:
        curated_fields = _curated_service.get_curated_fields_for_resource(payload.resource.id)
        return _ownership_service.resolve_ownership(
            resource=payload.resource,
            tags=payload.tags,
            parent_scope=payload.parent_scope,
            scope_owner_map=payload.scope_owner_map,
            application=payload.application,
            curated_fields=curated_fields,
            raise_on_unresolved=payload.raise_on_unresolved,
        )
    except UnresolvedOwnershipException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# ------------------------------------------------------------------------------
# Allocation Rules & Engine Endpoints
# ------------------------------------------------------------------------------


@router.post(
    "/allocation/rules", response_model=AllocationRule, status_code=status.HTTP_201_CREATED
)
def create_allocation_rule(rule: AllocationRule) -> AllocationRule:
    """Registers a new cost allocation rule.

    Strictly validates that SPLIT_RULE targets sum to exactly 100%. Rejects invalid splits at save time.
    """
    try:
        _allocation_engine.add_rule(rule)
        return rule
    except InvalidSplitRuleException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/allocation/rules", response_model=list[AllocationRule])
def list_allocation_rules() -> list[AllocationRule]:
    """Returns all configured allocation rules sorted by precedence tier and priority."""
    return _allocation_engine.rules


class EvaluateAllocationRequest(BaseModel):
    cost_facts: list[CostFact] = Field(..., description="Cost fact records to allocate")


@router.post("/allocation/evaluate", response_model=list[AllocatedCostRow])
def evaluate_allocation(payload: EvaluateAllocationRequest) -> list[AllocatedCostRow]:
    """Evaluates cost facts against configured allocation rules with first-match-wins semantics."""
    results: list[AllocatedCostRow] = []
    for fact in payload.cost_facts:
        allocated = _allocation_engine.allocate_cost_fact(cost_fact=fact)
        results.extend(allocated)
    return results


class AggregateAllocationRequest(BaseModel):
    allocated_rows: list[AllocatedCostRow] = Field(..., description="Allocated cost rows")
    dimension: str = Field(default="cost_center", description="Dimension to aggregate on")


@router.post("/allocation/aggregate", response_model=AggregationSummary)
def aggregate_allocation(payload: AggregateAllocationRequest) -> AggregationSummary:
    """Aggregates allocated costs ensuring UNALLOCATED spend is visible at all aggregation levels."""
    if payload.dimension == "business_unit":
        return _aggregation_service.aggregate_by_business_unit(payload.allocated_rows)
    elif payload.dimension == "scope":
        return _aggregation_service.aggregate_by_scope(payload.allocated_rows)
    elif payload.dimension == "winning_rule_type":
        return _aggregation_service.aggregate_by_winning_rule_type(payload.allocated_rows)
    else:
        return _aggregation_service.aggregate_by_cost_center(payload.allocated_rows)
