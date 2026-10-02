"""CloudLens Dependency Model & Multi-Layer Discovery Subsystem (Prompt 32).

Public domain exports for Prompt 32 / BBP Section 24.
"""

from domain.dependency.discovery import DependencyDiscoveryEngine
from domain.dependency.impact import ImpactAnalysisEngine
from domain.dependency.importer import BulkDependencyImporter
from domain.dependency.merger import EdgeMergeEngine
from domain.dependency.models import (
    BillingAllocationSyncItem,
    BillingAllocationSyncRequest,
    BillingAllocationSyncResult,
    BillingAttributes,
    BulkImportItem,
    BulkImportRequest,
    BulkImportResult,
    ConflictResolveRequest,
    DependencyEdge,
    DiscoveryConfiguration,
    DiscoveryRunRequest,
    DiscoveryRunResult,
    EdgeConflict,
    EdgeHistoryEntry,
    EdgeProvenance,
    EdgeUpdateRequest,
    ImpactNode,
    ImpactSet,
    ManualEdgeCreateRequest,
    NamingInferenceRule,
    TopologyGraph,
    TypedEntityRef,
)
from domain.dependency.repository import (
    DependencyRepository,
    get_dependency_repository,
    reset_dependency_repository,
)
from domain.dependency.service import (
    DependencyService,
    get_dependency_service,
    reset_dependency_service,
)

__all__ = [
    # Models & Contracts
    "TypedEntityRef",
    "EdgeProvenance",
    "BillingAttributes",
    "EdgeHistoryEntry",
    "EdgeConflict",
    "DependencyEdge",
    "ImpactNode",
    "ImpactSet",
    "TopologyGraph",
    "ManualEdgeCreateRequest",
    "EdgeUpdateRequest",
    "BulkImportItem",
    "BulkImportRequest",
    "BulkImportResult",
    "ConflictResolveRequest",
    "NamingInferenceRule",
    "DiscoveryConfiguration",
    "DiscoveryRunRequest",
    "DiscoveryRunResult",
    "BillingAllocationSyncItem",
    "BillingAllocationSyncRequest",
    "BillingAllocationSyncResult",
    # Engines & Repository
    "DependencyRepository",
    "get_dependency_repository",
    "reset_dependency_repository",
    "EdgeMergeEngine",
    "DependencyDiscoveryEngine",
    "ImpactAnalysisEngine",
    "BulkDependencyImporter",
    # Primary Service Facade
    "DependencyService",
    "get_dependency_service",
    "reset_dependency_service",
]
