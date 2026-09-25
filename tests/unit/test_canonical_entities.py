"""Unit Tests for Canonical Entities, Native Payload Retention, and Governance."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from domain.models.base import ProvenanceRecord
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    BudgetPeriod,
    DependencyDirection,
    DependencyType,
    MeasureNullState,
    NotificationChannel,
    NotificationStatus,
    OriginType,
    PolicySeverity,
    PolicyStatus,
    PricingModel,
    PricingStatus,
    ProviderType,
    RuntimeStatus,
    ScopeRole,
    ServiceCategory,
    SyncJobStatus,
)
from domain.models.exceptions import InvalidScopeHierarchyException
from domain.models.facts import PricingDimension, PricingRecord, RuntimeState, UsageFact
from domain.models.governance import (
    Alert,
    AuditEvent,
    Budget,
    Dependency,
    Forecast,
    Notification,
    Override,
    Policy,
    PolicyFinding,
    SyncJob,
    ThresholdSet,
    ThresholdState,
)
from domain.models.inventory import (
    Application,
    AvailabilityZone,
    BusinessUnit,
    CostCenter,
    Environment,
    Owner,
    Project,
    Region,
    Resource,
    ResourceType,
    Service,
    Tag,
)
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.models.scope import Scope, ScopeTree
from domain.rules.thresholds import ThresholdBand


def test_resource_native_payload_retention():
    """Verify Resource entity preserves raw provider payload and provenance verbatim."""
    raw_payload = {
        "InstanceId": "i-0123456789abcdef0",
        "InstanceType": "m5.large",
        "State": {"Code": 16, "Name": "running"},
        "NetworkInterfaces": [{"SubnetId": "subnet-0123", "PrivateIp": "10.0.1.5"}],
        "CustomProviderMetric": 99.8,
    }

    res = Resource(
        tenant_id="tenant-1",
        scope_id="scope-acc-1",
        native_id="arn:aws:ec2:us-east-1:111122223333:instance/i-0123456789abcdef0",
        name="api-gateway-node-1",
        provider=ProviderType.AWS,
        service_id="service-ec2",
        resource_type_id="type-ec2-instance",
        region_id="us-east-1",
        availability_zone="us-east-1a",
        pricing_status=PricingStatus.PAID,
        tags=[Tag(key="Environment", value="Production", inherited=False, source="native")],
        provider_native=raw_payload,
        source_provenance=ProvenanceRecord(
            source_system="aws-ec2-api",
            origin_type=OriginType.DISCOVERED,
            survives_rediscovery=True,
        ),
    )

    assert res.provider_native == raw_payload
    assert res.provider_native["CustomProviderMetric"] == 99.8
    assert res.source_provenance.origin_type == OriginType.DISCOVERED


def test_inventory_structural_entities():
    """Verify Application, Environment, Owner, CostCenter, BusinessUnit, Project, Region, Service, ResourceType."""
    owner = Owner(name="Jane Doe", email="jane@example.com", department="FinOps")
    bu = BusinessUnit(code="BU-RETAIL", name="Retail Banking")
    cc = CostCenter(code="CC-1042", name="Platform Engineering", business_unit_id=bu.id)
    proj = Project(code="PRJ-CLOUD", name="Cloud Modernization", cost_center_id=cc.id)
    app = Application(
        code="APP-CORE",
        name="Core Banking Service",
        criticality="MISSION_CRITICAL",
        owner_id=owner.id,
    )
    env = Environment(name="Production", category="PRODUCTION")

    region = Region(
        provider=ProviderType.AWS,
        native_name="us-east-1",
        display_name="US East (N. Virginia)",
        geography="North America",
        is_multi_az=True,
    )
    az = AvailabilityZone(
        region_id=region.id, provider=ProviderType.AWS, native_zone_id="us-east-1a"
    )
    service = Service(
        provider=ProviderType.AWS,
        service_code="AmazonEC2",
        name="Elastic Compute Cloud",
        category=ServiceCategory.COMPUTE,
    )
    res_type = ResourceType(
        provider=ProviderType.AWS,
        service_id=service.id,
        native_type_name="AWS::EC2::Instance",
        canonical_type="compute/virtual-machine",
        service_category=ServiceCategory.COMPUTE,
    )

    assert owner.email == "jane@example.com"
    assert bu.code == "BU-RETAIL"
    assert cc.business_unit_id == bu.id
    assert proj.cost_center_id == cc.id
    assert app.criticality == "MISSION_CRITICAL"
    assert env.category == "PRODUCTION"
    assert region.is_multi_az is True
    assert az.native_zone_id == "us-east-1a"
    assert res_type.canonical_type == "compute/virtual-machine"


def test_usage_and_pricing_facts():
    """Verify UsageFact, PricingDimension, and PricingRecord entities."""
    now = datetime.now(UTC)

    usage = UsageFact(
        tenant_id="tenant-acme",
        scope_id="scope-1",
        resource_id="res-1",
        period_start=now,
        period_end=now,
        metric_name="ComputeHours",
        usage_quantity=QuantityMeasure.of(Decimal("744.0")),
        usage_unit="Hours",
    )
    assert usage.usage_quantity.value == Decimal("744.0")

    dim = PricingDimension(
        dimension_name="vCPU-Hours",
        unit="Hours",
        description="Billed per allocated vCPU per elapsed hour",
        tier_minimum=Decimal("0.0"),
    )
    assert dim.dimension_name == "vCPU-Hours"

    record = PricingRecord(
        service_id="svc-1",
        resource_type_id="type-1",
        pricing_dimension_name=dim.dimension_name,
        rate=FinancialMeasure.of(Decimal("0.096")),
        currency="USD",
        pricing_model=PricingModel.ON_DEMAND,
        effective_date=now,
    )
    assert record.rate.value == Decimal("0.096")


def test_runtime_state_cpu_memory_measures():
    """Verify RuntimeState captures utilization via 4-state null discipline measures."""
    now = datetime.now(UTC)

    state_active = RuntimeState(
        resource_id="res-vm-01",
        status=RuntimeStatus.RUNNING,
        cpu_utilization_avg=QuantityMeasure.of(Decimal("42.5")),
        memory_utilization_avg=QuantityMeasure.of(Decimal("68.0")),
        observed_at=now,
        is_idle=False,
    )
    assert state_active.cpu_utilization_avg.value == Decimal("42.5")
    assert state_active.memory_utilization_avg.value == Decimal("68.0")
    assert state_active.is_idle is False

    state_serverless = RuntimeState(
        resource_id="res-s3-bucket",
        status=RuntimeStatus.RUNNING,
        cpu_utilization_avg=QuantityMeasure.not_applicable(),
        memory_utilization_avg=QuantityMeasure.not_applicable(),
        observed_at=now,
        is_idle=None,
    )
    assert state_serverless.cpu_utilization_avg.null_state == MeasureNullState.NOT_APPLICABLE
    assert state_serverless.memory_utilization_avg.render() == "NOT_APPLICABLE"


def test_governance_budget_forecast_policy_and_audit():
    """Verify Budget, Forecast, Policy, PolicyFinding, Dependency, Alert, Notification, SyncJob, AuditEvent, Override."""
    now = datetime.now(UTC)

    tset = ThresholdSet(
        name="Production Conservative Set",
        amber_percentage=Decimal("75.0"),
        red_percentage=Decimal("85.0"),
        critical_percentage=Decimal("100.0"),
    )

    budget = Budget(
        tenant_id="tenant-acme",
        scope_id="scope-sub-1",
        name="Q1 Engineering Budget",
        amount=FinancialMeasure.of(Decimal("100000.00")),
        period=BudgetPeriod.QUARTERLY,
        start_date=date(2026, 1, 1),
        threshold_set_id=tset.id,
    )

    state = ThresholdState(
        budget_id=budget.id,
        current_spend=FinancialMeasure.of(Decimal("87500.00")),
        current_band=ThresholdBand.RED,
        evaluated_at=now,
    )

    forecast = Forecast(
        budget_id=budget.id,
        scope_id="scope-sub-1",
        forecast_period_start=now,
        forecast_period_end=now,
        projected_amount=FinancialMeasure.of(Decimal("92000.00")),
        confidence_score=0.92,
        forecast_model="ENSEMBLE",
    )

    policy = Policy(
        name="Mandatory CostCenter Tag",
        rule_type="TAG_COMPLIANCE",
        severity=PolicySeverity.HIGH,
        parameters={"required_tags": ["CostCenter", "Environment"]},
    )

    finding = PolicyFinding(
        policy_id=policy.id,
        resource_id="res-01",
        status=PolicyStatus.OPEN,
        details="Missing required tag 'CostCenter'",
        detected_at=now,
    )

    dep = Dependency(
        source_resource_id="res-app-server",
        target_resource_id="res-db-server",
        dependency_type=DependencyType.DATABASE_CLIENT,
        direction=DependencyDirection.OUTBOUND,
    )

    alert = Alert(
        tenant_id="tenant-acme",
        alert_type="BUDGET_BREACH",
        severity=AlertSeverity.CRITICAL,
        message="Scope exceeded red threshold band",
        status=AlertStatus.ACTIVE,
        triggered_at=now,
    )

    notification = Notification(
        alert_id=alert.id,
        channel=NotificationChannel.SLACK,
        recipient="#finops-alerts",
        status=NotificationStatus.SENT,
        sent_at=now,
    )

    job = SyncJob(
        connector_type=ProviderType.AWS,
        scope_id="scope-sub-1",
        status=SyncJobStatus.COMPLETED,
        started_at=now,
        completed_at=now,
        rows_ingested=1250,
    )

    audit = AuditEvent(
        tenant_id="tenant-acme",
        actor_id="user-finops-lead@example.com",
        action="BUDGET_UPDATED",
        entity_type="Budget",
        entity_id=budget.id,
        timestamp=now,
        correlation_id="corr-audit-01",
    )

    override = Override(
        entity_type="CostFact",
        entity_id="fact-01",
        field_name="effective_cost",
        override_value="5000.00",
        reason="Manual adjustment for agreed vendor SLA rebate",
        created_by="admin@example.com",
    )

    assert budget.amount.value == Decimal("100000.00")
    assert state.current_band == ThresholdBand.RED
    assert forecast.projected_amount.value == Decimal("92000.00")
    assert finding.status == PolicyStatus.OPEN
    assert dep.dependency_type == DependencyType.DATABASE_CLIENT
    assert alert.severity == AlertSeverity.CRITICAL
    assert notification.status == NotificationStatus.SENT
    assert job.rows_ingested == 1250
    assert audit.action == "BUDGET_UPDATED"
    assert override.override_value == "5000.00"


def test_circular_reparenting_raises_domain_exception():
    """Verify circular reparenting attempt raises InvalidScopeHierarchyException."""
    tree = ScopeTree()
    s1 = tree.add_scope(
        Scope(
            id="s1",
            tenant_id="t1",
            name="S1",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="mg1",
        )
    )
    s2 = tree.add_scope(
        Scope(
            id="s2",
            tenant_id="t1",
            parent_id="s1",
            name="S2",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="mg2",
        )
    )

    with pytest.raises(InvalidScopeHierarchyException) as exc_info:
        tree.reparent_scope(scope_id=s1.id, new_parent_id=s2.id, effective_time=datetime.now(UTC))
    assert "circular dependency" in str(exc_info.value)
