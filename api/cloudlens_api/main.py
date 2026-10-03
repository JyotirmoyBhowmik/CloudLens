"""CloudLens API - Application Layer."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.cloudlens_api.conventions.exceptions import PublicAPIException
from api.cloudlens_api.conventions.middleware import (
    conventions_dispatch_middleware,
    make_problem_details,
)
from api.cloudlens_api.routes import (
    alerts_router,
    analytics_router,
    attribution_router,
    audit_router,
    auth_router,
    bootstrap_router,
    budgets_router,
    bulk_import_router,
    config_router,
    connectors_router,
    cost_router,
    credentials_router,
    dashboards_router,
    demo_mode_router,
    demo_router,
    dependency_router,
    diagnostics_router,
    forecasting_router,
    health_router,
    hierarchy_router,
    inventory_router,
    masterdata_router,
    overrides_router,
    policies_router,
    pricing_router,
    provisioning_router,
    quotas_router,
    rbac_router,
    remediation_router,
    reports_router,
    roles_router,
    runtime_router,
    scopes_router,
    statements_router,
    storage_router,
    sync_router,
    thresholds_router,
    topology_router,
    usage_router,
    users_router,
    wizard_router,
    workflows_router,
)
from domain.models.exceptions import (
    AlertException,
    AlertNotFoundException,
    AlertValidationException,
    AuditRecordNotFoundException,
    AuditStreamException,
    AuditTamperForbiddenException,
    BudgetApprovalNotAllowedException,
    BudgetException,
    BudgetNotFoundException,
    BudgetPendingApprovalException,
    BudgetTemplateNotFoundException,
    BulkImportException,
    ChannelNotSupportedException,
    CircuitBreakerOpenException,
    ConnectorException,
    ContextualAlertNotFoundException,
    CostException,
    CrossTenantAccessForbiddenException,
    CrossTenantStorageAccessException,
    CurrencyConversionException,
    CustomRoleInvalidException,
    DeliveryFailedException,
    DependencyException,
    DomainModelException,
    DuplicatePolicyException,
    EstimateExpiredException,
    EstimateNotFoundException,
    ExpectationNotFoundException,
    FeatureFlagDisabledException,
    FirstSyncNotFoundException,
    ForecastAccuracyEvaluationException,
    ForecastingException,
    ForecastNotFoundException,
    GraphExportException,
    InsufficientHistoryException,
    InterpolationLabelRequiredException,
    InvalidBudgetAmountException,
    InvalidBudgetDatesException,
    InvalidExemptionException,
    InvalidFreeAllowanceException,
    InvalidPricingTierException,
    InvalidQuotaLimitException,
    InvalidSubscriptionException,
    InvalidTaskTransitionException,
    InvalidTraversalDepthException,
    InvalidWorkflowTransitionException,
    MandatoryReasonException,
    ManualQuotaSourceNoteRequiredException,
    MetricNotApplicableException,
    MissingAlertEvidenceException,
    MonitoringTypeNotFoundException,
    NativeBudgetReadOnlyException,
    NoResolvableApproverException,
    NoResolvableAssigneeException,
    OverrideException,
    OverrideNotFoundException,
    PermanentOverrideNotAllowedException,
    PolicyException,
    PolicyNotFoundException,
    PolicyValidationException,
    PricingException,
    PricingRecordNotFoundException,
    PricingSCDConflictException,
    ProvisioningGateException,
    ProvisioningRequestInvalidStateException,
    ProvisioningRequestNotFoundException,
    QuotaException,
    QuotaExhaustedException,
    QuotaIncreaseRequestNotFoundException,
    QuotaNotFoundException,
    QuotaNotSupportedException,
    RBACException,
    ReconciliationInvestigationNotFoundException,
    ReconciliationReportNotFoundException,
    RemediationException,
    RemediationTaskNotFoundException,
    RestrictedNodeAccessException,
    RootNodeNotFoundException,
    RuntimeException,
    ScheduleBreachValuationException,
    ScheduleNotFoundException,
    SubHourlyCollectionForbiddenException,
    SyncJobNotFoundException,
    TaskAlreadyClosedException,
    TenantContextException,
    ThresholdException,
    ThresholdOverrideExpiredException,
    ThresholdOverrideNotFoundException,
    ThresholdOverrideReasonTooShortException,
    ThresholdPreviewDisabledException,
    ThresholdRuleNotFoundException,
    TopologyException,
    TopologyViewNotFoundException,
    UnapprovedDeploymentException,
    UnauthorizedApproverException,
    UndeclaredCapabilityException,
    UnknownSchemaVersionException,
    UsageException,
    VerificationFailedException,
    WizardSessionNotFoundException,
    WorkflowAlreadyFinalizedException,
    WorkflowApplicationFailedException,
    WorkflowDefinitionNotFoundException,
    WorkflowDelegationExpiredException,
    WorkflowException,
    WorkflowMandatoryCommentException,
    WorkflowNotFoundException,
)
from domain.observability import (
    current_correlation_id,
    current_operation,
    current_tenant_id,
    get_logger,
    metrics,
    setup_tracing,
    trace_api_request,
)

# Initialize OpenTelemetry in-memory / OTLP tracing
setup_tracing(service_name="cloudlens-api", in_memory=True)
logger = get_logger("cloudlens.api")

app = FastAPI(
    title="CloudLens API",
    description="Multi-cloud governance, inventory, pricing, cost, usage, and budgeting API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_and_timing_middleware(request: Request, call_next):
    """Propagate Correlation-ID, execute OpenTelemetry span, and record Prometheus metrics."""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    tenant_id = "global"

    # Derive tenant from authenticated identity if present, never trusting client parameter alone (Item 83)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            from domain.identity.service import get_identity_service

            token_str = auth_header[len("Bearer ") :].strip()
            auth_ctx = get_identity_service().token_engine.extract_auth_context(token_str)
            tenant_id = auth_ctx.tenant_id
        except Exception:
            tenant_id = request.headers.get("X-Tenant-ID", "global")
    else:
        tenant_id = request.headers.get("X-Tenant-ID", "global")

    request.state.correlation_id = correlation_id
    request.state.tenant_id = tenant_id

    current_correlation_id.set(correlation_id)
    current_tenant_id.set(tenant_id)
    current_operation.set(f"{request.method} {request.url.path}")

    start_time = time.perf_counter()

    with trace_api_request(
        endpoint=request.url.path,
        method=request.method,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
    ):
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_s = time.perf_counter() - start_time
            duration_ms = duration_s * 1000.0
            metrics.api_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code="500",
            ).observe(duration_s)
            logger.error(
                "Request failed with unhandled internal server error",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status_code": 500,
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "correlation_id": correlation_id,
                    "message": "An internal server error occurred.",
                },
                headers={
                    "X-Correlation-ID": correlation_id,
                    "X-Response-Time-MS": f"{duration_ms:.2f}",
                },
            )

        duration_s = time.perf_counter() - start_time
        duration_ms = duration_s * 1000.0
        metrics.api_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=str(status_code),
        ).observe(duration_s)

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"
        return response


@app.middleware("http")
async def conventions_middleware(request: Request, call_next):
    """Enforces per-token rate limiting, idempotency keys, and metadata headers (Prompt 34)."""
    return await conventions_dispatch_middleware(request, call_next)


@app.exception_handler(PublicAPIException)
async def standardized_public_api_exception_handler(request: Request, exc: PublicAPIException):
    """Handles standard platform API exceptions formatted as RFC 7807/9457 Problem Details (Prompt 34)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    content = make_problem_details(
        status_code=exc.status_code,
        error_code=exc.error_code,
        detail=exc.message,
        instance=request.url.path,
        correlation_id=correlation_id,
        title=exc.title,
        last_successful_ingestion_at=exc.last_successful_ingestion_at,
        invalid_params=exc.invalid_params,
    )
    headers = {"X-Correlation-ID": correlation_id}
    if exc.status_code == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


@app.exception_handler(HTTPException)
async def standardized_http_exception_handler(request: Request, exc: HTTPException):
    """Sanitized and standardized error response formatted as RFC 7807 Problem Details (Rule 2.4 / Prompt 34)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    status_to_code = {
        400: "INVALID_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        412: "PRECONDITION_FAILED",
        422: "INVALID_REQUEST",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "DATA_UNAVAILABLE",
    }
    code_val = status_to_code.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://api.cloudlens.io/errors/{code_val}",
            "title": exc.detail if isinstance(exc.detail, str) else "Error",
            "status": exc.status_code,
            "status_code": exc.status_code,
            "detail": str(exc.detail),
            "message": str(exc.detail),
            "instance": request.url.path,
            "code": code_val,
            "error_code": "HTTP_ERROR",
            "correlation_id": correlation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(DomainModelException)
async def standardized_domain_exception_handler(request: Request, exc: DomainModelException):
    """Global domain model exception handler mapping business errors to sanitized JSON (Rule 2.3 & 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": 422,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(RBACException)
async def standardized_rbac_exception_handler(request: Request, exc: RBACException):
    """RBAC exception handler mapping permission and scope denials to HTTP 403 (Rule 2.3 & 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    status_code = (
        status.HTTP_422_UNPROCESSABLE_ENTITY
        if isinstance(exc, CustomRoleInvalidException)
        else status.HTTP_403_FORBIDDEN
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(TenantContextException)
async def standardized_tenant_context_exception_handler(
    request: Request, exc: TenantContextException
):
    """Tenant isolation and context exception handler (Prompt 13 Items 83-85)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    status_code = (
        status.HTTP_403_FORBIDDEN
        if isinstance(exc, (CrossTenantAccessForbiddenException, CrossTenantStorageAccessException))
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(AuditStreamException)
async def standardized_audit_stream_exception_handler(request: Request, exc: AuditStreamException):
    """Append-only audit stream exception handler (Prompt 13 Item 86)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, AuditTamperForbiddenException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, AuditRecordNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(OverrideException)
async def standardized_override_exception_handler(request: Request, exc: OverrideException):
    """Operational override exception handler (Prompt 13 Item 87)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, PermanentOverrideNotAllowedException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, OverrideNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(ConnectorException)
async def standardized_connector_exception_handler(request: Request, exc: ConnectorException):
    """Connector and capability exception handler (Prompt 14 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, UndeclaredCapabilityException):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, CircuitBreakerOpenException):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, QuotaExhaustedException):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(
        exc, (SyncJobNotFoundException, WizardSessionNotFoundException, FirstSyncNotFoundException)
    ):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(PricingException)
async def standardized_pricing_exception_handler(request: Request, exc: PricingException):
    """Pricing catalogue exception handler (Prompt 20 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, PricingRecordNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc,
        (InvalidPricingTierException, InvalidFreeAllowanceException, PricingSCDConflictException),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(CostException)
async def standardized_cost_exception_handler(request: Request, exc: CostException):
    """Cost ingestion and normalisation exception handler (Prompt 22 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (UnknownSchemaVersionException, CurrencyConversionException)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(
        exc, (ReconciliationReportNotFoundException, ReconciliationInvestigationNotFoundException)
    ):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(UsageException)
async def standardized_usage_exception_handler(request: Request, exc: UsageException):
    """Usage telemetry and monitoring exception handler (Prompt 25 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(
        exc,
        (
            SubHourlyCollectionForbiddenException,
            MetricNotApplicableException,
            InterpolationLabelRequiredException,
        ),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, (ExpectationNotFoundException, MonitoringTypeNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(RuntimeException)
async def standardized_runtime_exception_handler(request: Request, exc: RuntimeException):
    """Runtime model, schedule adherence, and exemption exception handler (Prompt 26 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, ScheduleNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (ScheduleBreachValuationException,)):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(ThresholdException)
async def standardized_threshold_exception_handler(request: Request, exc: ThresholdException):
    """Threshold engine, band validation, override, and preview exception handler (Prompt 27 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (ThresholdRuleNotFoundException, ThresholdOverrideNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ThresholdPreviewDisabledException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ThresholdOverrideExpiredException):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, (ThresholdOverrideReasonTooShortException,)):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(QuotaException)
async def standardized_quota_exception_handler(request: Request, exc: QuotaException):
    """Quota, service limits, and headroom tracking exception handler (Prompt 54 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (QuotaNotFoundException, QuotaIncreaseRequestNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (ManualQuotaSourceNoteRequiredException, InvalidQuotaLimitException)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, QuotaExhaustedException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, QuotaNotSupportedException):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(BudgetException)
async def standardized_budget_exception_handler(request: Request, exc: BudgetException):
    """Budget and allocation exception handler (Prompt 28 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (BudgetNotFoundException, BudgetTemplateNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (InvalidBudgetAmountException, InvalidBudgetDatesException)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, BudgetPendingApprovalException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, BudgetApprovalNotAllowedException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, NativeBudgetReadOnlyException):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(ForecastingException)
async def standardized_forecasting_exception_handler(request: Request, exc: ForecastingException):
    """Forecasting engine exception handler (Prompt 29 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, ForecastNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, FeatureFlagDisabledException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ForecastAccuracyEvaluationException):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, InsufficientHistoryException):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(PolicyException)
async def standardized_policy_exception_handler(request: Request, exc: PolicyException):
    """Policy engine exception handler (Prompt 30 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, PolicyNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DuplicatePolicyException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (InvalidExemptionException, PolicyValidationException)):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(AlertException)
async def standardized_alert_exception_handler(request: Request, exc: AlertException):
    """Alerting and notification exception handler (Prompt 31 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (AlertNotFoundException, ContextualAlertNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc,
        (
            MissingAlertEvidenceException,
            ChannelNotSupportedException,
            InvalidSubscriptionException,
            AlertValidationException,
        ),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, DeliveryFailedException):
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(WorkflowException)
async def workflow_exception_handler(request: Request, exc: WorkflowException) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (WorkflowNotFoundException, WorkflowDefinitionNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, UnauthorizedApproverException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(
        exc,
        (
            WorkflowMandatoryCommentException,
            InvalidWorkflowTransitionException,
            WorkflowDelegationExpiredException,
            WorkflowAlreadyFinalizedException,
        ),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, NoResolvableApproverException):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, WorkflowApplicationFailedException):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = status.HTTP_400_BAD_REQUEST

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(RemediationException)
async def standardized_remediation_exception_handler(request: Request, exc: RemediationException):
    """Remediation and accountability exception handler (Prompt 51 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, RemediationTaskNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, TaskAlreadyClosedException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (InvalidTaskTransitionException, MandatoryReasonException)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, (NoResolvableAssigneeException, VerificationFailedException)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_400_BAD_REQUEST

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(DependencyException)
async def dependency_exception_handler(request: Request, exc: DependencyException):
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    status_code = status.HTTP_400_BAD_REQUEST
    if "NOT_FOUND" in exc.error_code:
        status_code = status.HTTP_404_NOT_FOUND
    elif "CONFLICT" in exc.error_code or "PROTECTED" in exc.error_code:
        status_code = status.HTTP_409_CONFLICT
    elif "CYCLIC" in exc.error_code:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(TopologyException)
async def topology_exception_handler(request: Request, exc: TopologyException):
    """Standardized exception handler for Cost-Aware Topology (Prompt 33 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (TopologyViewNotFoundException, RootNodeNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, RestrictedNodeAccessException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (InvalidTraversalDepthException, GraphExportException)):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(ProvisioningGateException)
async def provisioning_gate_exception_handler(request: Request, exc: ProvisioningGateException):
    """Standardized exception handler for Cost-Aware Provisioning Gate (Prompt 55 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    if isinstance(exc, (EstimateNotFoundException, ProvisioningRequestNotFoundException)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ProvisioningRequestInvalidStateException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (EstimateExpiredException, UnapprovedDeploymentException)):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(BulkImportException)
async def bulk_import_exception_handler(request: Request, exc: BulkImportException):
    """Standardized exception handler for Bulk Import and Onboarding (Prompt 53 / Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)

    return JSONResponse(
        status_code=status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": status_code,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


app.include_router(alerts_router)
app.include_router(config_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(scopes_router)
app.include_router(inventory_router)
app.include_router(reports_router)
app.include_router(analytics_router)
app.include_router(rbac_router)
app.include_router(health_router)
app.include_router(masterdata_router)
app.include_router(bootstrap_router)
app.include_router(attribution_router)
app.include_router(demo_router)
app.include_router(demo_mode_router)
app.include_router(credentials_router)
app.include_router(connectors_router)
app.include_router(audit_router)
app.include_router(overrides_router)
app.include_router(storage_router)
app.include_router(sync_router)
app.include_router(wizard_router)
app.include_router(diagnostics_router)
app.include_router(pricing_router)
app.include_router(cost_router)
app.include_router(usage_router)
app.include_router(runtime_router)
app.include_router(thresholds_router)
app.include_router(quotas_router)
app.include_router(budgets_router)
app.include_router(forecasting_router)
app.include_router(policies_router)
app.include_router(workflows_router)
app.include_router(remediation_router)
app.include_router(dependency_router)
app.include_router(topology_router)
app.include_router(statements_router)
app.include_router(provisioning_router)
app.include_router(bulk_import_router)
app.include_router(dashboards_router)
app.include_router(hierarchy_router)


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Service health status")
    service: str = Field(default="cloudlens-api", description="Service identifier")
    version: str = Field(default="0.1.0", description="API version")
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    correlation_id: str = Field(description="Request trace correlation ID")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint for liveness and readiness monitoring."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return {
        "status": "healthy",
        "service": "cloudlens-api",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
    }


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root redirect / index information."""
    return {
        "message": "Welcome to CloudLens API. Visit /docs for OpenAPI documentation.",
        "status": "operational",
    }
