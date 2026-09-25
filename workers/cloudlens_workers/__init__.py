"""CloudLens asynchronous workers package."""

from workers.cloudlens_workers.celery_app import celery_app

__all__ = ["celery_app"]
