"""CloudLens OpenTelemetry Tracing & Distributed Context Propagation.

Wires OpenTelemetry across:
1. API request lifecycle
2. Database queries
3. Queued worker jobs (Celery)
All spans are joined by a common correlation identifier (Enterprise Rule 4.2 / Prompt 03 Item 20).
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from domain.observability.logging import (
    current_correlation_id,
    current_operation,
    current_tenant_id,
)

# Global test/inspection exporter
_in_memory_exporter: InMemorySpanExporter | None = None
_tracer_provider: TracerProvider | None = None


def setup_tracing(
    service_name: str = "cloudlens-platform", in_memory: bool = True
) -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider."""
    global _in_memory_exporter, _tracer_provider

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
            "deployment.environment": "development",
        }
    )

    provider = TracerProvider(resource=resource)
    if in_memory:
        _in_memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    return provider


def get_in_memory_spans() -> list[Any]:
    """Retrieve captured spans for testing and trace verification."""
    if _in_memory_exporter is not None:
        return list(_in_memory_exporter.get_finished_spans())
    return []


def clear_in_memory_spans() -> None:
    """Clear memory exporter buffer."""
    if _in_memory_exporter is not None:
        _in_memory_exporter.clear()


def get_tracer(name: str = "cloudlens") -> trace.Tracer:
    """Get named OpenTelemetry tracer."""
    return trace.get_tracer(name)


@contextmanager
def trace_api_request(
    endpoint: str,
    method: str,
    correlation_id: str | None = None,
    tenant_id: str | None = None,
) -> Generator[Span, None, None]:
    """Create root or child span for an API request joined by correlation identifier."""
    tracer = get_tracer("cloudlens.api")
    corr_id = correlation_id or str(uuid.uuid4())
    current_correlation_id.set(corr_id)
    if tenant_id:
        current_tenant_id.set(tenant_id)
    current_operation.set(f"{method} {endpoint}")

    with tracer.start_as_current_span(
        f"HTTP {method} {endpoint}",
        kind=SpanKind.SERVER,
        attributes={
            "http.method": method,
            "http.target": endpoint,
            "cloudlens.correlation_id": corr_id,
            "cloudlens.tenant_id": tenant_id or "global",
        },
    ) as span:
        yield span


@contextmanager
def trace_database_query(
    operation: str,
    statement: str = "",
    correlation_id: str | None = None,
) -> Generator[Span, None, None]:
    """Create child span for a database execution joined by correlation identifier."""
    tracer = get_tracer("cloudlens.database")
    corr_id = correlation_id or current_correlation_id.get() or str(uuid.uuid4())

    with tracer.start_as_current_span(
        f"DB {operation}",
        kind=SpanKind.CLIENT,
        attributes={
            "db.system": "postgresql",
            "db.operation": operation,
            "db.statement": statement,
            "cloudlens.correlation_id": corr_id,
        },
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise


@contextmanager
def trace_queued_job(
    task_name: str,
    correlation_id: str | None = None,
    tenant_id: str | None = None,
) -> Generator[Span, None, None]:
    """Create child span for background worker task joined by correlation identifier."""
    tracer = get_tracer("cloudlens.worker")
    corr_id = correlation_id or current_correlation_id.get() or str(uuid.uuid4())

    with tracer.start_as_current_span(
        f"CeleryTask {task_name}",
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "celery",
            "messaging.destination": task_name,
            "cloudlens.correlation_id": corr_id,
            "cloudlens.tenant_id": tenant_id or "global",
        },
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise
