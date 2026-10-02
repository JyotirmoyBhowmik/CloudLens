"""CloudLens API Routes Package."""

from api.cloudlens_api.routes.alerts import router as alerts_router
from api.cloudlens_api.routes.attribution import router as attribution_router
from api.cloudlens_api.routes.audit import router as audit_router
from api.cloudlens_api.routes.auth import router as auth_router
from api.cloudlens_api.routes.bootstrap import router as bootstrap_router
from api.cloudlens_api.routes.budgets import router as budgets_router
from api.cloudlens_api.routes.config import router as config_router
from api.cloudlens_api.routes.connectors import router as connectors_router
from api.cloudlens_api.routes.cost import router as cost_router
from api.cloudlens_api.routes.credentials import router as credentials_router
from api.cloudlens_api.routes.demo import router as demo_router
from api.cloudlens_api.routes.demo_mode import router as demo_mode_router
from api.cloudlens_api.routes.dependency import router as dependency_router
from api.cloudlens_api.routes.diagnostics import router as diagnostics_router
from api.cloudlens_api.routes.forecasting import router as forecasting_router
from api.cloudlens_api.routes.health import router as health_router
from api.cloudlens_api.routes.masterdata import router as masterdata_router
from api.cloudlens_api.routes.overrides import router as overrides_router
from api.cloudlens_api.routes.policies import router as policies_router
from api.cloudlens_api.routes.pricing import router as pricing_router
from api.cloudlens_api.routes.quotas import router as quotas_router
from api.cloudlens_api.routes.rbac import router as rbac_router
from api.cloudlens_api.routes.remediation import router as remediation_router
from api.cloudlens_api.routes.runtime import router as runtime_router
from api.cloudlens_api.routes.storage import router as storage_router
from api.cloudlens_api.routes.sync import router as sync_router
from api.cloudlens_api.routes.thresholds import router as thresholds_router
from api.cloudlens_api.routes.topology import router as topology_router
from api.cloudlens_api.routes.usage import router as usage_router
from api.cloudlens_api.routes.wizard import router as wizard_router
from api.cloudlens_api.routes.workflows import router as workflows_router

__all__ = [
    "alerts_router",
    "attribution_router",
    "audit_router",
    "auth_router",
    "bootstrap_router",
    "budgets_router",
    "config_router",
    "connectors_router",
    "cost_router",
    "credentials_router",
    "demo_mode_router",
    "demo_router",
    "dependency_router",
    "diagnostics_router",
    "forecasting_router",
    "health_router",
    "masterdata_router",
    "overrides_router",
    "policies_router",
    "pricing_router",
    "quotas_router",
    "rbac_router",
    "remediation_router",
    "runtime_router",
    "storage_router",
    "sync_router",
    "thresholds_router",
    "topology_router",
    "usage_router",
    "wizard_router",
    "workflows_router",
]
