"""Comprehensive Unit Tests for Usage Telemetry, Monitoring Types, Expectations, and Ingestion (Prompt 25).

Enforces:
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Per-resource assignment and override with audit.
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
  "A storage resource collects storage metrics and not compute metrics."
  "Do not collect metrics a monitoring type does not require."
- Prompt 25: Coarse granularity (hourly or daily) - sub-hourly collection is strictly forbidden.
- Prompt 25: Pre-aggregated storage with recorded aggregation method.
- Prompt 25: Explicit gap recording as 'No Data' (never assumed zero).
- Prompt 25: Labeled interpolation only - silent interpolation is forbidden.
- Prompt 25: Expectation model with inheritance across 4 levels (RESOURCE, SERVICE, SCOPE, TENANT).
- Prompt 25: Call-volume estimator and cost-materiality filter.
- Acceptance criteria: AC-051, AC-052, AC-053.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.service import get_audit_service, reset_audit_service
from domain.models.enums import AuditEventType, ProviderType, SystemRole
from domain.models.exceptions import (
    InterpolationLabelRequiredException,
    MetricNotApplicableException,
    MonitoringTypeNotFoundException,
    OverrideValidationException,
    SubHourlyCollectionForbiddenException,
)
from domain.models.measures import QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.collector import UsageCollector
from domain.usage.estimator import CallVolumeEstimator
from domain.usage.materiality import CostMaterialityFilter
from domain.usage.models import (
    AggregationMethod,
    CallVolumeEstimateRequest,
    CardinalityRisk,
    CollectionGranularity,
    ExpectationLevel,
    ExpectationStatus,
    MaterialityFilterConfig,
    MonitoringType,
    SpikeStatus,
    UsageExpectation,
    UsageIngestRequest,
)
from domain.usage.registry import (
    get_allowable_metrics,
    get_default_monitoring_type_for_resource,
    get_monitoring_type_definition,
    list_monitoring_types,
)
from domain.usage.service import get_usage_service, reset_usage_service


@pytest.fixture(autouse=True)
def setup_services():
    """Resets audit and usage singletons before each test."""
    reset_audit_service()
    reset_usage_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Fixture providing standard tenant context."""
    return TenantContext(
        tenant_id="tenant-usage-alpha",
        user_id="finops-lead@enterprise.com",
        roles=[SystemRole.FINOPS_ADMIN],
        correlation_id="corr-test-usage-1234",
    )


# ==============================================================================
# 1. Fourteen Monitoring Types & Catalogue Tests (BBP Section 19)
# ==============================================================================


def test_fourteen_monitoring_types_completeness():
    """Verifies that all 14 core monitoring types (+ 15th Quota Headroom) are registered."""
    all_types = list_monitoring_types()
    assert len(all_types) == 15

    codes = {t.code for t in all_types}
    for i in range(1, 16):
        expected_code = f"MT-{i:02d}"
        assert expected_code in codes

    # Core types present
    enum_members = {t.type_name for t in all_types}
    assert MonitoringType.RUNTIME_BASED in enum_members
    assert MonitoringType.VOLUME_BASED in enum_members
    assert MonitoringType.TRANSACTION_BASED in enum_members
    assert MonitoringType.REQUEST_BASED in enum_members
    assert MonitoringType.STORAGE_BASED in enum_members
    assert MonitoringType.DATA_TRANSFER_BASED in enum_members
    assert MonitoringType.USER_BASED in enum_members
    assert MonitoringType.LICENCE_BASED in enum_members
    assert MonitoringType.API_CALL_BASED in enum_members
    assert MonitoringType.SCHEDULE_BASED in enum_members
    assert MonitoringType.SEASONAL in enum_members
    assert MonitoringType.RESERVED_COMMITTED_USAGE in enum_members
    assert MonitoringType.PROVIDER_SPECIFIC_DIMENSION in enum_members
    assert MonitoringType.NOT_APPLICABLE in enum_members
    assert MonitoringType.QUOTA_HEADROOM in enum_members


def test_not_applicable_monitoring_type_has_zero_metrics():
    """Cardinality discipline: NOT_APPLICABLE must have zero permissible metrics."""
    definition = get_monitoring_type_definition(MonitoringType.NOT_APPLICABLE)
    assert definition.code == "MT-14"
    assert definition.allowable_metrics == []
    assert len(get_allowable_metrics(MonitoringType.NOT_APPLICABLE)) == 0


def test_invalid_monitoring_type_raises_exception():
    """Verifies that querying an unknown monitoring type raises MonitoringTypeNotFoundException."""
    with pytest.raises(MonitoringTypeNotFoundException):
        get_monitoring_type_definition("INVALID_TYPE_XYZ")


# ==============================================================================
# 2. Resource-to-Monitoring-Type Mapping & Per-Resource Override with Audit
# ==============================================================================


def test_default_monitoring_type_mapping():
    """Verifies default monitoring type derivation from resource type catalogue."""
    assert (
        get_default_monitoring_type_for_resource("AWS::EC2::Instance")
        == MonitoringType.RUNTIME_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::S3::Bucket") == MonitoringType.STORAGE_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::EC2::Volume") == MonitoringType.VOLUME_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::RDS::DBInstance")
        == MonitoringType.TRANSACTION_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::Lambda::Function")
        == MonitoringType.REQUEST_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::ApiGateway::RestApi")
        == MonitoringType.API_CALL_BASED
    )
    assert (
        get_default_monitoring_type_for_resource("AWS::CloudFormation::Stack")
        == MonitoringType.NOT_APPLICABLE
    )


def test_per_resource_override_with_audit(tenant_ctx: TenantContext):
    """Verifies per-resource override, audit logging, and dynamic metric change on next cycle.

    'Changing a monitoring type is audited and changes which metrics are collected on the next cycle.'
    """
    service = get_usage_service()
    res_id = "res-ec2-custom-01"

    # 1. Default before override: RUNTIME_BASED
    res_default = service.resolve_monitoring_type(
        resource_id=res_id,
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )
    assert res_default.monitoring_type == MonitoringType.RUNTIME_BASED
    assert res_default.is_overridden is False
    assert res_default.source == "CATALOGUE_DEFAULT"
    assert "cpu_utilization_avg" in res_default.allowable_metrics

    # 2. Apply override to SCHEDULE_BASED with valid rationale
    override = service.override_monitoring_type(
        resource_id=res_id,
        new_monitoring_type=MonitoringType.SCHEDULE_BASED,
        who=tenant_ctx.user_id,
        why="Workload is non-production developer testbed restricted to 9-to-5 weekday schedule.",
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )
    assert override.resource_id == res_id
    assert override.monitoring_type == MonitoringType.SCHEDULE_BASED
    assert override.previous_monitoring_type == MonitoringType.RUNTIME_BASED

    # 3. Next cycle resolution reflects override
    res_overridden = service.resolve_monitoring_type(
        resource_id=res_id,
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )
    assert res_overridden.monitoring_type == MonitoringType.SCHEDULE_BASED
    assert res_overridden.is_overridden is True
    assert res_overridden.source == "RESOURCE_OVERRIDE"
    assert "scheduled_hours_active" in res_overridden.allowable_metrics

    # 4. Audit trail verification: AuditEvent was appended to immutable stream
    audit_events = get_audit_service().list_events(tenant_context=tenant_ctx)
    override_events = [
        e for e in audit_events if e.event_type == AuditEventType.MONITORING_TYPE_OVERRIDDEN
    ]
    assert len(override_events) == 1
    assert override_events[0].resource_id == res_id
    assert override_events[0].details["new_monitoring_type"] == MonitoringType.SCHEDULE_BASED


def test_override_rationale_validation_fails_on_short_why(tenant_ctx: TenantContext):
    """Verifies that an override with a rationale under 20 characters is rejected."""
    service = get_usage_service()
    with pytest.raises(OverrideValidationException):
        service.override_monitoring_type(
            resource_id="res-fail-01",
            new_monitoring_type=MonitoringType.STORAGE_BASED,
            who=tenant_ctx.user_id,
            why="too short",  # < 20 chars
            tenant_context=tenant_ctx,
        )


# ==============================================================================
# 3. Cardinality Discipline & Permissible Metrics
# ==============================================================================


def test_cardinality_discipline_storage_resource_collects_storage_not_compute(
    tenant_ctx: TenantContext,
):
    """Acceptance criterion: 'A storage resource collects storage metrics and not compute metrics.'

    'Do not collect metrics a monitoring type does not require.'
    """
    service = get_usage_service()
    storage_res_id = "res-s3-prod-bucket-01"

    now = datetime.now(UTC)
    interval_start = now - timedelta(hours=1)

    # 1. Permitted storage metric succeeds
    storage_req = UsageIngestRequest(
        resource_id=storage_res_id,
        scope_id="scope-aws-01",
        metric_name="storage_allocated_bytes",
        interval_start=interval_start,
        interval_end=now,
        granularity=CollectionGranularity.HOURLY,
        aggregation_method=AggregationMethod.SUM,
        quantity=Decimal("5000000000"),
        unit="Bytes",
        strict_cardinality=True,
    )
    record = service.ingest_usage(
        request=storage_req,
        native_type_name="AWS::S3::Bucket",
        tenant_context=tenant_ctx,
    )
    assert record.resource_id == storage_res_id
    assert record.metric_name == "storage_allocated_bytes"
    assert record.usage_quantity.value == Decimal("5000000000")

    # 2. Attempting to collect compute metric on storage resource fails with MetricNotApplicableException
    compute_on_storage_req = UsageIngestRequest(
        resource_id=storage_res_id,
        scope_id="scope-aws-01",
        metric_name="cpu_utilization_avg",  # FORBIDDEN ON STORAGE_BASED
        interval_start=interval_start,
        interval_end=now,
        granularity=CollectionGranularity.HOURLY,
        aggregation_method=AggregationMethod.AVERAGE,
        quantity=Decimal("45.5"),
        unit="Percent",
        strict_cardinality=True,
    )
    with pytest.raises(MetricNotApplicableException) as exc_info:
        service.ingest_usage(
            request=compute_on_storage_req,
            native_type_name="AWS::S3::Bucket",
            tenant_context=tenant_ctx,
        )
    assert exc_info.value.metric_name == "cpu_utilization_avg"
    assert exc_info.value.monitoring_type == MonitoringType.STORAGE_BASED


def test_not_applicable_resource_rejects_all_metrics(tenant_ctx: TenantContext):
    """NOT_APPLICABLE resource strictly rejects any metric ingestion."""
    service = get_usage_service()
    rg_id = "res-rg-governance-01"

    req = UsageIngestRequest(
        resource_id=rg_id,
        scope_id="scope-azure-01",
        metric_name="cpu_utilization_avg",
        interval_start=datetime.now(UTC) - timedelta(hours=1),
        interval_end=datetime.now(UTC),
        quantity=Decimal("10.0"),
        unit="Percent",
        strict_cardinality=True,
    )
    with pytest.raises(MetricNotApplicableException):
        service.ingest_usage(
            request=req,
            native_type_name="Microsoft.Resources/resourceGroups",
            tenant_context=tenant_ctx,
        )


# ==============================================================================
# 4. Granularity Discipline & Sub-Hourly Prohibition
# ==============================================================================


def test_sub_hourly_collection_is_strictly_forbidden(tenant_ctx: TenantContext):
    """Negative constraint: 'Do not implement sub-hourly collection.'

    'Sub-hourly collection is out of scope and must not be implemented.'
    """
    service = get_usage_service()
    res_id = "res-vm-01"

    for forbidden_gran in ["5m", "15m", "sub_hourly", "minute"]:
        req = UsageIngestRequest(
            resource_id=res_id,
            scope_id="scope-01",
            metric_name="cpu_utilization_avg",
            interval_start=datetime.now(UTC) - timedelta(minutes=5),
            interval_end=datetime.now(UTC),
            granularity=forbidden_gran,  # type: ignore[arg-type]
            quantity=Decimal("20.0"),
            unit="Percent",
        )
        with pytest.raises(SubHourlyCollectionForbiddenException):
            service.ingest_usage(
                request=req,
                native_type_name="AWS::EC2::Instance",
                tenant_context=tenant_ctx,
            )

    # Hourly and Daily must succeed
    assert UsageCollector.validate_granularity("HOURLY") == CollectionGranularity.HOURLY
    assert UsageCollector.validate_granularity("DAILY") == CollectionGranularity.DAILY
    assert UsageCollector.validate_granularity(3600) == CollectionGranularity.HOURLY
    assert UsageCollector.validate_granularity(86400) == CollectionGranularity.DAILY


# ==============================================================================
# 5. Explicit Gap Recording & Labeled Interpolation
# ==============================================================================


def test_explicit_telemetry_gap_renders_no_data_never_zero(tenant_ctx: TenantContext):
    """Acceptance criterion AC-053: Metric telemetry gap is displayed explicitly as 'No Data' and never as zero usage."""
    service = get_usage_service()
    res_id = "res-vm-gap-01"

    now = datetime.now(UTC)
    req = UsageIngestRequest(
        resource_id=res_id,
        scope_id="scope-01",
        metric_name="cpu_utilization_avg",
        interval_start=now - timedelta(hours=1),
        interval_end=now,
        granularity=CollectionGranularity.HOURLY,
        quantity=None,  # Telemetry gap
        unit="Percent",
        is_gap=True,
    )
    record = service.ingest_usage(
        request=req,
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )

    assert record.is_gap is True
    assert record.usage_quantity.is_null is True
    assert record.usage_quantity.render() == "NO_DATA"

    # Evaluated against expectation, gap MUST produce NO_DATA status and render 'No Data'
    eval_result = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id="svc-ec2",
        scope_id="scope-01",
        metric_name="cpu_utilization_avg",
        observed_quantity=record.usage_quantity,
        observed_unit="Percent",
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )
    assert eval_result.status == ExpectationStatus.NO_DATA
    assert eval_result.actual_value_display == "No Data"
    assert eval_result.is_gap is True
    assert "never as zero usage" in eval_result.explanation


def test_interpolation_requires_mandatory_label(tenant_ctx: TenantContext):
    """Negative constraint: 'Do not interpolate a gap without labelling it.'"""
    service = get_usage_service()
    res_id = "res-vm-interp-01"

    # 1. Unlabeled interpolation raises InterpolationLabelRequiredException
    unlabeled_req = UsageIngestRequest(
        resource_id=res_id,
        scope_id="scope-01",
        metric_name="cpu_utilization_avg",
        interval_start=datetime.now(UTC) - timedelta(hours=1),
        interval_end=datetime.now(UTC),
        quantity=None,
        unit="Percent",
        is_gap=True,
        interpolate=True,
        interpolation_label=None,  # Forbidden: missing label
    )
    with pytest.raises(InterpolationLabelRequiredException):
        service.ingest_usage(
            request=unlabeled_req,
            native_type_name="AWS::EC2::Instance",
            tenant_context=tenant_ctx,
        )

    # 2. Labeled interpolation succeeds and retains label
    labeled_req = UsageIngestRequest(
        resource_id=res_id,
        scope_id="scope-01",
        metric_name="cpu_utilization_avg",
        interval_start=datetime.now(UTC) - timedelta(hours=1),
        interval_end=datetime.now(UTC),
        quantity=Decimal("35.0"),
        unit="Percent",
        is_gap=True,
        interpolate=True,
        interpolation_label="INTERPOLATED: LINEAR",
    )
    interp_rec = service.ingest_usage(
        request=labeled_req,
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )
    assert interp_rec.is_interpolated is True
    assert interp_rec.interpolation_label == "INTERPOLATED: LINEAR"
    assert interp_rec.usage_quantity.value == Decimal("35.0")


# ==============================================================================
# 6. Expectation Model & 4-Level Inheritance Tests
# ==============================================================================


def test_expectation_four_level_inheritance(tenant_ctx: TenantContext):
    """Verifies expectation resolution walking RESOURCE -> SERVICE -> SCOPE -> TENANT."""
    service = get_usage_service()
    res_id = "res-db-order-01"
    svc_id = "svc-rds"
    scope_id = "scope-prod"

    # Define baseline TENANT expectation: 100 requests
    exp_tenant = UsageExpectation(
        id="exp-tenant-01",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.TENANT,
        target_id=tenant_ctx.tenant_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        expected_requests=Decimal("100"),
        created_by="admin",
    )
    service.save_expectation(exp_tenant, tenant_context=tenant_ctx)

    # Define SCOPE expectation: 500 requests
    exp_scope = UsageExpectation(
        id="exp-scope-01",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.SCOPE,
        target_id=scope_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        expected_requests=Decimal("500"),
        created_by="admin",
    )
    service.save_expectation(exp_scope, tenant_context=tenant_ctx)

    # Define SERVICE expectation: 1,000 requests
    exp_service = UsageExpectation(
        id="exp-svc-01",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.SERVICE,
        target_id=svc_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        expected_requests=Decimal("1000"),
        created_by="admin",
    )
    service.save_expectation(exp_service, tenant_context=tenant_ctx)

    # Resolution without resource override: SERVICE wins (1,000) over SCOPE (500) and TENANT (100)
    resolved_1 = service.expectation_engine.resolve_expectation(
        resource_id=res_id,
        service_id=svc_id,
        scope_id=scope_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        tenant_context=tenant_ctx,
    )
    assert resolved_1 is not None
    assert resolved_1.source_level == ExpectationLevel.SERVICE
    assert resolved_1.effective_expectation.expected_requests == Decimal("1000")
    assert resolved_1.is_inherited is True
    assert resolved_1.is_overridden is False

    # Now define explicit RESOURCE expectation: 5,000 requests
    exp_resource = UsageExpectation(
        id="exp-res-01",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.RESOURCE,
        target_id=res_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        expected_requests=Decimal("5000"),
        created_by="admin",
    )
    service.save_expectation(exp_resource, tenant_context=tenant_ctx)

    # Resolution with resource override: RESOURCE wins (5,000)
    resolved_2 = service.expectation_engine.resolve_expectation(
        resource_id=res_id,
        service_id=svc_id,
        scope_id=scope_id,
        monitoring_type=MonitoringType.TRANSACTION_BASED,
        tenant_context=tenant_ctx,
    )
    assert resolved_2 is not None
    assert resolved_2.source_level == ExpectationLevel.RESOURCE
    assert resolved_2.effective_expectation.expected_requests == Decimal("5000")
    assert resolved_2.is_inherited is False
    assert resolved_2.is_overridden is True


# ==============================================================================
# 7. Acceptance Criteria: AC-051 and AC-052
# ==============================================================================


def test_acceptance_ac_051_storage_resource_amber_and_red_thresholds(
    tenant_ctx: TenantContext,
):
    """Acceptance criterion AC-051: Storage resource with 5 TB expectation shows Amber above 80% and Red above 100%."""
    service = get_usage_service()
    res_id = "res-s3-ac051-storage"

    # Configure 5 TB expectation with standard 80% warning (4 TB) and 100% critical (5 TB)
    exp = UsageExpectation(
        id="exp-ac051",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.RESOURCE,
        target_id=res_id,
        monitoring_type=MonitoringType.STORAGE_BASED,
        expected_capacity=Decimal("5"),
        expected_capacity_unit="TB",
        warning_threshold_pct=Decimal("80.0"),
        critical_threshold_pct=Decimal("100.0"),
        created_by="finops-lead",
    )
    service.save_expectation(exp, tenant_context=tenant_ctx)

    # Case 1: 3.5 TB (70%) -> NORMAL (Green)
    res_normal = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id="svc-s3",
        scope_id="scope-01",
        metric_name="storage_allocated_bytes",
        observed_quantity=QuantityMeasure.of(Decimal("3.5")),
        observed_unit="TB",
        native_type_name="AWS::S3::Bucket",
        tenant_context=tenant_ctx,
    )
    assert res_normal.status == ExpectationStatus.NORMAL
    assert res_normal.utilisation_percentage == Decimal("70.0")

    # Case 2: 4.2 TB (84%) -> AMBER (> 80%)
    res_amber = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id="svc-s3",
        scope_id="scope-01",
        metric_name="storage_allocated_bytes",
        observed_quantity=QuantityMeasure.of(Decimal("4.2")),
        observed_unit="TB",
        native_type_name="AWS::S3::Bucket",
        tenant_context=tenant_ctx,
    )
    assert res_amber.status == ExpectationStatus.AMBER
    assert res_amber.utilisation_percentage == Decimal("84.0")

    # Case 3: 5.5 TB (110%) -> RED (> 100%)
    res_red = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id="svc-s3",
        scope_id="scope-01",
        metric_name="storage_allocated_bytes",
        observed_quantity=QuantityMeasure.of(Decimal("5.5")),
        observed_unit="TB",
        native_type_name="AWS::S3::Bucket",
        tenant_context=tenant_ctx,
    )
    assert res_red.status == ExpectationStatus.RED
    assert res_red.utilisation_percentage == Decimal("110.0")


def test_acceptance_ac_052_api_service_amber_and_red_thresholds(
    tenant_ctx: TenantContext,
):
    """Acceptance criterion AC-052: API service with 10M call expectation shows Amber above 8M and Red above 10M."""
    service = get_usage_service()
    svc_id = "svc-apigateway-checkout"
    res_id = "res-api-checkout-prod"

    # Configure 10,000,000 call expectation at SERVICE level
    exp = UsageExpectation(
        id="exp-ac052",
        tenant_id=tenant_ctx.tenant_id,
        level=ExpectationLevel.SERVICE,
        target_id=svc_id,
        monitoring_type=MonitoringType.API_CALL_BASED,
        expected_requests=Decimal("10000000"),
        warning_threshold_pct=Decimal("80.0"),  # Amber at 8M
        critical_threshold_pct=Decimal("100.0"),  # Red at 10M
        created_by="api-architect",
    )
    service.save_expectation(exp, tenant_context=tenant_ctx)

    # Case 1: 7,500,000 calls (75%) -> NORMAL
    res_normal = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id=svc_id,
        scope_id="scope-01",
        metric_name="api_call_count",
        observed_quantity=QuantityMeasure.of(Decimal("7500000")),
        observed_unit="Requests",
        native_type_name="AWS::ApiGateway::RestApi",
        tenant_context=tenant_ctx,
    )
    assert res_normal.status == ExpectationStatus.NORMAL
    assert res_normal.utilisation_percentage == Decimal("75.0")

    # Case 2: 8,500,000 calls (85%) -> AMBER (> 8M)
    res_amber = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id=svc_id,
        scope_id="scope-01",
        metric_name="api_call_count",
        observed_quantity=QuantityMeasure.of(Decimal("8500000")),
        observed_unit="Requests",
        native_type_name="AWS::ApiGateway::RestApi",
        tenant_context=tenant_ctx,
    )
    assert res_amber.status == ExpectationStatus.AMBER
    assert res_amber.utilisation_percentage == Decimal("85.0")

    # Case 3: 10,500,000 calls (105%) -> RED (> 10M)
    res_red = service.evaluate_resource_usage(
        resource_id=res_id,
        service_id=svc_id,
        scope_id="scope-01",
        metric_name="api_call_count",
        observed_quantity=QuantityMeasure.of(Decimal("10500000")),
        observed_unit="Requests",
        native_type_name="AWS::ApiGateway::RestApi",
        tenant_context=tenant_ctx,
    )
    assert res_red.status == ExpectationStatus.RED
    assert res_red.utilisation_percentage == Decimal("105.0")


# ==============================================================================
# 8. Sizing Estimator & Cost-Materiality Filter Tests
# ==============================================================================


def test_call_volume_estimator_cardinality_risk_and_recommendations():
    """Acceptance criterion: 'The call-volume estimate appears before a high-cardinality configuration is enabled.'"""
    # 1. Modest estate: 50 resources, HOURLY
    modest_req = CallVolumeEstimateRequest(
        resource_count=50,
        granularity=CollectionGranularity.HOURLY,
        monitoring_types=[MonitoringType.RUNTIME_BASED, MonitoringType.STORAGE_BASED],
        provider=ProviderType.AWS,
    )
    modest_est = CallVolumeEstimator.estimate(modest_req)
    assert modest_est.resource_count == 50
    assert modest_est.daily_api_calls > 0
    assert modest_est.cardinality_risk in (CardinalityRisk.LOW, CardinalityRisk.MEDIUM)

    # 2. Huge estate: 10,000 resources, HOURLY -> triggers HIGH or CRITICAL
    huge_req = CallVolumeEstimateRequest(
        resource_count=10000,
        granularity=CollectionGranularity.HOURLY,
        monitoring_types=[
            MonitoringType.RUNTIME_BASED,
            MonitoringType.STORAGE_BASED,
            MonitoringType.VOLUME_BASED,
            MonitoringType.TRANSACTION_BASED,
        ],
        provider=ProviderType.AWS,
    )
    huge_est = CallVolumeEstimator.estimate(huge_req)
    assert huge_est.cardinality_risk in (CardinalityRisk.HIGH, CardinalityRisk.CRITICAL)
    assert len(huge_est.warnings) > 0
    assert len(huge_est.recommendations) > 0


def test_cost_materiality_filter():
    """Cost-threshold filter limits collection to resources above configurable materiality."""
    candidates = [
        {"resource_id": "res-prod-db", "monthly_cost": Decimal("250.00")},
        {"resource_id": "res-app-server", "monthly_cost": Decimal("75.00")},
        {"resource_id": "res-micro-idle-vm", "monthly_cost": Decimal("1.25")},  # Low spend
        {"resource_id": "res-orphan-disk", "monthly_cost": Decimal("0.80")},  # Low spend
    ]

    # Filter with $5.00 threshold
    cfg = MaterialityFilterConfig(min_monthly_cost_threshold=Decimal("5.00"), enabled=True)
    result = CostMaterialityFilter.filter_resources(candidates, cfg)

    assert result.candidate_count == 4
    assert result.included_count == 2
    assert result.excluded_count == 2
    assert "res-prod-db" in result.included_resource_ids
    assert "res-app-server" in result.included_resource_ids
    assert "res-micro-idle-vm" in result.excluded_resource_ids
    assert "res-orphan-disk" in result.excluded_resource_ids
    assert result.estimated_monthly_api_calls_saved > 0
    assert result.estimated_monthly_cost_savings_usd > Decimal("0.00")


# ==============================================================================
# 9. Downsampling Rollup & Statistical Spike Detection Tests
# ==============================================================================


def test_downsampling_hourly_to_daily_rollup(tenant_ctx: TenantContext):
    """Verifies rollup of 24 hourly metrics into a single daily record retaining aggregation method."""
    service = get_usage_service()
    res_id = "res-rollup-vm-01"
    base_date = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)

    # Ingest 24 hourly samples of 10.0 runtime hours / units
    for h in range(24):
        req = UsageIngestRequest(
            resource_id=res_id,
            scope_id="scope-01",
            metric_name="runtime_hours",
            interval_start=base_date + timedelta(hours=h),
            interval_end=base_date + timedelta(hours=h + 1),
            granularity=CollectionGranularity.HOURLY,
            aggregation_method=AggregationMethod.SUM,
            quantity=Decimal("1.0"),
            unit="Hours",
        )
        service.ingest_usage(
            request=req,
            native_type_name="AWS::EC2::Instance",
            tenant_context=tenant_ctx,
        )

    # Execute daily rollup
    daily_rec = service.collector.roll_up_to_daily(
        resource_id=res_id,
        metric_name="runtime_hours",
        target_date=base_date,
        tenant_context=tenant_ctx,
    )
    assert daily_rec is not None
    assert daily_rec.granularity == CollectionGranularity.DAILY
    assert daily_rec.aggregation_method == AggregationMethod.SUM
    assert daily_rec.usage_quantity.value == Decimal("24.0")


def test_statistical_consumption_spike_detection():
    """Verifies USE-007 / FR-246 baseline standard deviation spike detection."""
    # Baseline: 10, 10, 10, 10, 10 (mean = 10, std_dev = ~0.0)
    baseline = [Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), Decimal("10")]

    # Normal observation: 11
    eval_normal = UsageCollector.evaluate_consumption_spike(
        resource_id="res-01",
        metric_name="transaction_count",
        observed_value=Decimal("11"),
        baseline_history=baseline,
        sigma_threshold=Decimal("3.0"),
    )
    assert eval_normal.status == SpikeStatus.NORMAL

    # Spike observation: 100 (> 3 sigma)
    eval_spike = UsageCollector.evaluate_consumption_spike(
        resource_id="res-01",
        metric_name="transaction_count",
        observed_value=Decimal("100"),
        baseline_history=baseline,
        sigma_threshold=Decimal("3.0"),
    )
    assert eval_spike.status == SpikeStatus.ANOMALOUS_SPIKE
    assert eval_spike.z_score > Decimal("3.0")


# ==============================================================================
# 10. API Route Contract Tests (API-031)
# ==============================================================================


def test_api_usage_metrics_query_contract(tenant_ctx: TenantContext):
    """Verifies GET /api/v1/usage/metrics endpoint (API-031)."""
    service = get_usage_service()
    res_id = "res-api-metric-01"

    service.ingest_usage(
        request=UsageIngestRequest(
            resource_id=res_id,
            scope_id="scope-01",
            metric_name="cpu_utilization_avg",
            interval_start=datetime.now(UTC) - timedelta(hours=1),
            interval_end=datetime.now(UTC),
            granularity=CollectionGranularity.HOURLY,
            quantity=Decimal("50.0"),
            unit="Percent",
        ),
        native_type_name="AWS::EC2::Instance",
        tenant_context=tenant_ctx,
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/usage/metrics",
        headers={
            "X-Tenant-ID": tenant_ctx.tenant_id,
            "X-User-ID": tenant_ctx.user_id,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1
    assert data["items"][0]["resource_id"] == res_id


def test_api_monitoring_types_list_contract():
    """Verifies GET /api/v1/usage/monitoring-types endpoint."""
    client = TestClient(app)
    response = client.get("/api/v1/usage/monitoring-types")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 15
    codes = [d["code"] for d in data]
    assert "MT-01" in codes
    assert "MT-14" in codes
    assert "MT-15" in codes


def test_api_call_volume_estimate_contract():
    """Verifies POST /api/v1/usage/call-volume-estimate endpoint."""
    client = TestClient(app)
    payload = {
        "resource_count": 100,
        "granularity": "HOURLY",
        "monitoring_types": ["RUNTIME_BASED", "STORAGE_BASED"],
        "provider": "aws",
    }
    response = client.post("/api/v1/usage/call-volume-estimate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["resource_count"] == 100
    assert data["monthly_api_calls"] > 0
    assert "cardinality_risk" in data


def test_api_materiality_filter_contract():
    """Verifies POST /api/v1/usage/materiality-filter endpoint."""
    client = TestClient(app)
    payload = {
        "candidates": [
            {"resource_id": "r-1", "monthly_cost": "100.00"},
            {"resource_id": "r-2", "monthly_cost": "1.00"},
        ],
        "config": {"min_monthly_cost_threshold": "5.00", "enabled": True},
    }
    response = client.post("/api/v1/usage/materiality-filter", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["included_count"] == 1
    assert data["excluded_count"] == 1
    assert "r-1" in data["included_resource_ids"]
