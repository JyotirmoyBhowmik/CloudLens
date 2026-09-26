"""Unit and Integration Tests for CloudLens Observability Skeleton.

Verifies:
1. Acceptance: A single API request produces one trace spanning API, database and queued work, joined by one correlation identifier.
2. Acceptance: An attempt to log a secret value results in a redacted log line, verified by test.
3. Acceptance: Readiness fails when the database is stopped and recovers when it returns.
4. Metric registry: All 12 Prometheus metrics are registered and scrapable via /metrics.
"""

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.observability import (
    METRIC_DEFINITIONS,
    CloudLensJsonFormatter,
    clear_in_memory_spans,
    get_in_memory_spans,
    health_probe,
    redact_text,
    redact_value,
    trace_api_request,
    trace_database_query,
    trace_queued_job,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_observability():
    clear_in_memory_spans()
    health_probe.reset_overrides()
    yield
    clear_in_memory_spans()
    health_probe.reset_overrides()


# --- Acceptance Criterion 1: Unified Tracing Joined by Correlation ID ---


def test_single_trace_spans_api_database_and_queued_work():
    """Acceptance: A single API request produces one trace spanning API, database

    and any queued work, joined by one correlation identifier.
    """
    test_correlation_id = "corr-test-trace-uuid-1234"

    # Simulate an end-to-end request flow: API -> Database -> Queued task
    with trace_api_request("/api/v1/resources", "GET", correlation_id=test_correlation_id):
        # 1. Database execution inside request
        with trace_database_query(
            "SELECT_RESOURCES", "SELECT * FROM resources WHERE tenant_id = 't1'"
        ):
            pass

        # 2. Queued worker job dispatched from request
        with trace_queued_job("cloudlens.sync.tenant", correlation_id=test_correlation_id):
            pass

    spans = get_in_memory_spans()
    assert len(spans) == 3

    span_names = {s.name for s in spans}
    assert "HTTP GET /api/v1/resources" in span_names
    assert "DB SELECT_RESOURCES" in span_names
    assert "CeleryTask cloudlens.sync.tenant" in span_names

    # Verify all spans are joined by the exact same correlation identifier
    for s in spans:
        span_attrs = dict(s.attributes)
        assert span_attrs.get("cloudlens.correlation_id") == test_correlation_id


# --- Acceptance Criterion 2: Secret & PII Redaction in Logging ---


def test_secret_redaction_engine_masks_sensitive_patterns():
    """Unit test for redaction functions on strings and nested data structures."""
    # Password assignment
    raw_str = "Connecting with user=admin and password=super_secret_password_123 to database"
    redacted_str = redact_text(raw_str)
    assert "super_secret_password_123" not in redacted_str
    assert "password=[REDACTED]" in redacted_str

    # JWT Token
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert "[REDACTED_JWT]" in redact_text(f"Token received: {jwt}")
    assert jwt not in redact_text(f"Token received: {jwt}")

    # Bearer token
    bearer_str = "Authorization: Bearer secret_api_token_xyz"
    assert "secret_api_token_xyz" not in redact_text(bearer_str)
    assert "Bearer [REDACTED_TOKEN]" in redact_text(bearer_str)

    # AWS Key
    aws_str = "AWS Key AKIAIOSFODNN7EXAMPLE used"
    assert "AKIAIOSFODNN7EXAMPLE" not in redact_text(aws_str)
    assert "[REDACTED_AWS_KEY]" in redact_text(aws_str)

    # Nested dictionary
    raw_dict = {
        "user": "alice",
        "api_key": "secret_key_val",
        "nested": {"token": "top_secret_token", "normal_field": "ok"},
    }
    redacted_dict = redact_value(raw_dict)
    assert redacted_dict["user"] == "alice"
    assert redacted_dict["api_key"] == "[REDACTED]"
    assert redacted_dict["nested"]["token"] == "[REDACTED]"
    assert redacted_dict["nested"]["normal_field"] == "ok"


def test_attempt_to_log_secret_produces_redacted_log_line():
    """Acceptance: An attempt to log a secret value results in a redacted log line, verified by test."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    formatter = CloudLensJsonFormatter(service_name="cloudlens-test")
    handler.setFormatter(formatter)

    test_logger = logging.getLogger("test.redaction.logger")
    test_logger.handlers = [handler]
    test_logger.setLevel(logging.INFO)

    secret_password = "MyHighlyConfidentialDbPassword!987"
    secret_token = "Bearer secret_bearer_token_abc123"

    # Attempt to log secrets
    test_logger.info(
        "User authentication failed for user=admin with password=%s and token=%s",
        secret_password,
        secret_token,
    )

    log_output = stream.getvalue()

    # Assert secret values are NOT in the emitted log
    assert secret_password not in log_output
    assert "secret_bearer_token_abc123" not in log_output

    # Assert log is valid structured JSON containing redacted text
    parsed = json.loads(log_output.strip())
    assert parsed["level"] == "INFO"
    assert "password=[REDACTED]" in parsed["message"]
    assert "Bearer [REDACTED_TOKEN]" in parsed["message"]


# --- Acceptance Criterion 3: Readiness Fails and Recovers ---


def test_readiness_probe_fails_when_db_down_and_recovers_when_db_returns(client: TestClient):
    """Acceptance: Readiness fails when the database is stopped and recovers when it returns."""
    # 1. Initial state: all dependencies healthy -> 200 OK
    res_initial = client.get("/api/v1/health/readiness")
    assert res_initial.status_code == 200
    assert res_initial.json()["status"] == "ready"
    assert res_initial.json()["dependencies"]["database"]["status"] == "healthy"

    # 2. Simulate database down / stopped
    health_probe.set_override("database", False)

    res_down = client.get("/api/v1/health/readiness")
    assert res_down.status_code == 503
    down_json = res_down.json()
    # The standardized exception handler returns the detail in "message"
    assert down_json["status_code"] == 503
    assert down_json["error_code"] == "HTTP_ERROR"

    # 3. Simulate database recovery
    health_probe.set_override("database", True)

    res_recovered = client.get("/api/v1/health/readiness")
    assert res_recovered.status_code == 200
    assert res_recovered.json()["status"] == "ready"
    assert res_recovered.json()["dependencies"]["database"]["status"] == "healthy"


# --- Metrics Registry & Scraping Verification ---


def test_all_12_canonical_metrics_registered_and_scrapable(client: TestClient):
    """Verify all 12 platform metrics required by Prompt 03 Item 21 are exposed via /metrics."""
    # Check definition catalogue
    expected_metrics = [
        "api_request_duration_seconds",
        "api_error_rate",
        "sync_job_duration_seconds",
        "sync_job_outcome_total",
        "connector_freshness_seconds",
        "ingestion_rows_total",
        "reconciliation_variance_ratio",
        "queue_depth",
        "worker_saturation",
        "db_replication_lag_seconds",
        "threshold_evaluation_duration_seconds",
        "notification_delivery_failures_total",
    ]

    for metric_name in expected_metrics:
        assert metric_name in METRIC_DEFINITIONS
        assert METRIC_DEFINITIONS[metric_name].alert_condition != ""
        assert METRIC_DEFINITIONS[metric_name].slo_target != ""

    # Call /metrics endpoint
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    metrics_text = res.text

    for metric_name in expected_metrics:
        assert metric_name in metrics_text, (
            f"Metric {metric_name} was not found in /metrics scrape output!"
        )
