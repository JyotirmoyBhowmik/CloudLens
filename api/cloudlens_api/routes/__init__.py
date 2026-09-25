"""CloudLens API Routes Package."""

from api.cloudlens_api.routes.config import router as config_router
from api.cloudlens_api.routes.health import router as health_router
from api.cloudlens_api.routes.masterdata import router as masterdata_router

__all__ = ["config_router", "health_router", "masterdata_router"]
