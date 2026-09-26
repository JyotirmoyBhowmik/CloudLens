"""CloudLens API Routes Package."""

from api.cloudlens_api.routes.attribution import router as attribution_router
from api.cloudlens_api.routes.auth import router as auth_router
from api.cloudlens_api.routes.bootstrap import router as bootstrap_router
from api.cloudlens_api.routes.config import router as config_router
from api.cloudlens_api.routes.demo import router as demo_router
from api.cloudlens_api.routes.demo_mode import router as demo_mode_router
from api.cloudlens_api.routes.health import router as health_router
from api.cloudlens_api.routes.masterdata import router as masterdata_router

__all__ = [
    "attribution_router",
    "auth_router",
    "bootstrap_router",
    "config_router",
    "demo_mode_router",
    "demo_router",
    "health_router",
    "masterdata_router",
]
