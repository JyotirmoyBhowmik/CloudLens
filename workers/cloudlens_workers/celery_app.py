"""CloudLens Celery application and worker configuration."""

import os
import uuid
from typing import Any, cast

from celery import Celery

from domain.models.exceptions import MissingTenantContextException
from domain.observability import current_correlation_id, current_tenant_id
from domain.tenant.context import TenantContext

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "cloudlens_workers",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="cloudlens.health")
def worker_health_task():
    """Worker liveness task."""
    return {"status": "healthy", "worker": "celery-worker"}


def execute_tenant_job(
    tenant_context_payload: dict[str, Any] | None, job_func, *args, **kwargs
) -> Any:
    """Executes a worker job requiring and activating an explicit TenantContext (Prompt 13 Item 85).

    Carries explicit tenant context into background job execution, configuring correlation ID
    and tenant contextvars for structured logging, storage access, and audit.
    """
    if not tenant_context_payload or not isinstance(tenant_context_payload, dict):
        raise MissingTenantContextException(
            "Background job dispatched without mandatory tenant context payload."
        )

    tenant_id = tenant_context_payload.get("tenant_id")
    if not tenant_id or not str(tenant_id).strip():
        raise MissingTenantContextException(
            "Background job tenant context payload missing valid non-empty tenant_id."
        )

    correlation_id = tenant_context_payload.get("correlation_id") or str(uuid.uuid4())
    tc = TenantContext(
        tenant_id=str(tenant_id).strip(),
        user_id=tenant_context_payload.get("user_id", "background-worker"),
        roles=tenant_context_payload.get("roles", ["SYSTEM"]),
        correlation_id=correlation_id,
        is_system=True,
    )

    current_tenant_id.set(tc.tenant_id)
    current_correlation_id.set(tc.correlation_id or "")

    return job_func(tc, *args, **kwargs)


@celery_app.task(name="cloudlens.overrides.revert_expired")
def revert_expired_overrides_task(tenant_context_payload: dict[str, Any]) -> dict[str, Any]:
    """Background task reverting expired overrides for a tenant (Prompt 13 Item 87)."""
    from domain.overrides.service import get_override_service

    def _run(tc: TenantContext) -> dict[str, Any]:
        svc = get_override_service()
        reverted = svc.revert_expired_overrides(tenant_context=tc)
        return {
            "status": "COMPLETED",
            "tenant_id": tc.tenant_id,
            "reverted_count": len(reverted),
            "reverted_ids": [r.id for r in reverted],
        }

    return cast(dict[str, Any], execute_tenant_job(tenant_context_payload, _run))
