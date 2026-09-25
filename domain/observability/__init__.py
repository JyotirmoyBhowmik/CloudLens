"""CloudLens Observability Domain Package."""

from domain.observability.health import DependencyHealthProbe, health_probe
from domain.observability.logging import (
    CloudLensJsonFormatter,
    RedactionFilter,
    current_actor,
    current_correlation_id,
    current_operation,
    current_tenant_id,
    get_logger,
    setup_structured_logging,
)
from domain.observability.metrics import (
    METRIC_DEFINITIONS,
    CloudLensMetrics,
    MetricDefinition,
    metrics,
)
from domain.observability.redaction import redact_text, redact_value
from domain.observability.tracing import (
    clear_in_memory_spans,
    get_in_memory_spans,
    get_tracer,
    setup_tracing,
    trace_api_request,
    trace_database_query,
    trace_queued_job,
)

__all__ = [
    "CloudLensJsonFormatter",
    "CloudLensMetrics",
    "DependencyHealthProbe",
    "METRIC_DEFINITIONS",
    "MetricDefinition",
    "RedactionFilter",
    "clear_in_memory_spans",
    "current_actor",
    "current_correlation_id",
    "current_operation",
    "current_tenant_id",
    "get_in_memory_spans",
    "get_logger",
    "get_tracer",
    "health_probe",
    "metrics",
    "redact_text",
    "redact_value",
    "setup_structured_logging",
    "setup_tracing",
    "trace_api_request",
    "trace_database_query",
    "trace_queued_job",
]
