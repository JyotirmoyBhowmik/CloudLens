"""CloudLens Structured JSON Logging & Context Propagation.

Produces JSON logs with contextual attributes:
level, timestamp, service, correlation_id, tenant_id, actor, operation, and message.
Enforces redaction of confidential credentials and PII prior to emission.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from domain.observability.redaction import redact_text, redact_value

# Context variables for tracing and multi-tenant context propagation
current_correlation_id: ContextVar[str] = ContextVar("current_correlation_id", default="")
current_tenant_id: ContextVar[str] = ContextVar("current_tenant_id", default="")
current_actor: ContextVar[str] = ContextVar("current_actor", default="anonymous")
current_operation: ContextVar[str] = ContextVar("current_operation", default="")


class CloudLensJsonFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON with redaction."""

    def __init__(self, service_name: str = "cloudlens-platform") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Base message formatting
        raw_msg = record.getMessage()
        sanitized_msg = redact_text(raw_msg)

        # Retrieve contextual attributes from record or ContextVars
        corr_id = getattr(record, "correlation_id", None) or current_correlation_id.get() or "none"
        tenant_id = getattr(record, "tenant_id", None) or current_tenant_id.get() or "none"
        actor = getattr(record, "actor", None) or current_actor.get() or "system"
        operation = getattr(record, "operation", None) or current_operation.get() or record.funcName

        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "correlation_id": corr_id,
            "tenant_id": tenant_id,
            "actor": actor,
            "operation": operation,
            "logger_name": record.name,
            "message": sanitized_msg,
        }

        # Include custom extra fields if present
        extra_fields = {}
        for key, val in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "correlation_id",
                "tenant_id",
                "actor",
                "operation",
            ):
                extra_fields[key] = redact_value(val)

        if extra_fields:
            log_payload["extra"] = extra_fields

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


class RedactionFilter(logging.Filter):
    """Logging filter ensuring that record messages and args are redacted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_value(record.args)
            elif isinstance(record.args, list | tuple):
                record.args = tuple(redact_value(a) for a in record.args)
        return True


def setup_structured_logging(service_name: str = "cloudlens-platform", level: str = "INFO") -> None:
    """Configure root logger with CloudLens JSON formatting and redaction."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CloudLensJsonFormatter(service_name=service_name))
    handler.addFilter(RedactionFilter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Create a named logger."""
    return logging.getLogger(name)
