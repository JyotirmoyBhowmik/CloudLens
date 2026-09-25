"""CloudLens API Routes Package."""

from api.cloudlens_api.routes.config import router as config_router
from api.cloudlens_api.routes.health import router as health_router

__all__ = ["config_router", "health_router"]
