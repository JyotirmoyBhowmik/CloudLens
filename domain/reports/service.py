"""Unified Report Domain Service Facade (Prompt 35 / BBP Section 36).

Coordinates:
- 14 MVP reports + 5 pricing reports + 2 Phase 2 flag-gated reports.
- Comprehensive parameterisation and mandatory provenance footers.
- Strict RBAC scope-grant evaluation with filtering disclosure.
- Asynchronous generation with time-limited download links and audit tracking.
- Dual audit trail logging for generation and download.
- Phase 2 recurring report scheduling.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import uuid

from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    DownloadLinkExpiredException,
    InvalidDownloadTokenException,
    ReportJobNotFoundException,
    ReportTemplateNotFoundException,
    UnsupportedReportFormatException,
)
from domain.reports.catalogue import (
    MASTER_REPORT_CATALOGUE,
    get_report_definition,
)
from domain.reports.exporters import ReportExportEngine
from domain.reports.generators import ReportGenerationEngine
from domain.reports.models import (
    ExportFormat,
    ReportDefinition,
    ReportJob,
    ReportParameters,
    ScheduledReport,
)
from domain.reports.repository import ReportRepository, get_report_repository
from domain.reports.scheduling import ReportSchedulingEngine
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class ReportService:
    """Enterprise domain service facade for platform reporting and exports."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        generator_engine: ReportGenerationEngine | None = None,
        export_engine: ReportExportEngine | None = None,
        scheduling_engine: ReportSchedulingEngine | None = None,
        audit_service: AuditService | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> None:
        self.repository = repository or get_report_repository()
        self.generator_engine = generator_engine or ReportGenerationEngine(
            feature_flags=feature_flags
        )
        self.export_engine = export_engine or ReportExportEngine()
        self.scheduling_engine = scheduling_engine or ReportSchedulingEngine(
            repository=self.repository, feature_flags=feature_flags
        )
        self.audit_service = audit_service or get_audit_service()

    # ==========================================================================
    # 1. Report Template Catalogue
    # ==========================================================================

    def list_templates(
        self,
        *,
        category: str | None = None,
        include_phase2: bool = False,
        tenant_context: TenantContext | None = None,
    ) -> list[ReportDefinition]:
        """Lists available report templates filtered by category and phase."""
        _ = tenant_context
        results: list[ReportDefinition] = []
        for defn in MASTER_REPORT_CATALOGUE:
            if not include_phase2 and defn.is_phase_2:
                continue
            if category and defn.category.value.lower() != category.lower():
                continue
            results.append(defn)
        return results

    def get_template(self, template_id: str) -> ReportDefinition:
        """Retrieves a specific report definition by ID or canonical code."""
        defn = get_report_definition(template_id)
        if not defn:
            raise ReportTemplateNotFoundException(template_id)
        return defn

    # ==========================================================================
    # 2. Synchronous & Asynchronous Report Generation
    # ==========================================================================

    def generate_report(
        self,
        template_id: str,
        parameters: ReportParameters,
        format_type: ExportFormat,
        *,
        async_generation: bool = False,
        tenant_context: TenantContext,
    ) -> tuple[ReportJob, bytes | None]:
        """Generates report data, applies RBAC scope masking, exports to format, and audits generation."""
        tc = require_tenant_context(tenant_context)
        defn = self.get_template(template_id)

        # Validate format is supported
        if format_type not in defn.supported_formats:
            raise UnsupportedReportFormatException(
                f"Format '{format_type.value}' is not supported by template '{defn.id}'. "
                f"Supported: {[f.value for f in defn.supported_formats]}"
            )

        # 1. Generate Report Data with RBAC scope evaluation & Provenance Footer
        report_data = self.generator_engine.generate(defn, parameters, tc)

        # 2. Serialize to Requested Format
        content_bytes = self.export_engine.export(report_data, format_type)

        # 3. Create ReportJob and Token-Limited Artifact
        job_id = f"job-exp-{uuid.uuid4().hex[:12]}"
        report_id = f"rep-{uuid.uuid4().hex[:12]}"
        download_token = f"tok-dl-{uuid.uuid4().hex[:16]}"
        now = dt.datetime.now(dt.UTC)
        ttl_seconds = 3600  # 1 hour download validity
        expires_at = now + dt.timedelta(seconds=ttl_seconds)

        file_ext = format_type.value.lower()
        filename = f"{defn.id}_{parameters.period or now.strftime('%Y%m')}.{file_ext}"

        # Save artifact bytes
        self.repository.save_artifact(report_id, content_bytes, tenant_context=tc)

        # Save job record
        job = ReportJob(
            id=job_id,
            tenant_id=tc.tenant_id,
            template_id=defn.id,
            format=format_type,
            parameters=parameters,
            status="COMPLETED",
            created_at=now,
            completed_at=now,
            download_token=download_token,
            download_url=f"/api/v1/reports/downloads/{report_id}?token={download_token}",
            expires_at=expires_at,
            row_count=report_data.row_count,
            file_size_bytes=len(content_bytes),
            output_filename=filename,
            provenance=report_data.provenance,
        )
        saved_job = self.repository.save_job(job, tenant_context=tc)

        # 4. Mandatory Audit Trail Logging for Report Generation
        self.audit_service.append_event(
            tenant_context=tc,
            event_in=AuditEventCreate(
                event_type=AuditEventType.REPORT_GENERATED,
                actor_id=tc.email or tc.user_id or "anonymous",
                actor_roles=tc.roles,
                action="REPORT_GENERATED",
                resource_type="REPORT_JOB",
                resource_id=job_id,
                details={
                    "report_id": report_id,
                    "template_id": defn.id,
                    "report_code": defn.code.value,
                    "format": format_type.value,
                    "period": report_data.period,
                    "cost_basis": report_data.provenance.cost_basis,
                    "currency": parameters.currency,
                    "row_count": report_data.row_count,
                    "access_filtering_occurred": report_data.provenance.access_filtering_occurred,
                    "scope_id": parameters.scope_id,
                    "file_size_bytes": len(content_bytes),
                },
                correlation_id=tc.correlation_id,
            ),
        )

        logger.info(
            "Generated report '%s' (ID: %s) in format %s for tenant %s [Rows: %d, Filtered: %s]",
            defn.name,
            report_id,
            format_type.value,
            tc.tenant_id,
            report_data.row_count,
            report_data.provenance.access_filtering_occurred,
        )

        return saved_job, (None if async_generation else content_bytes)

    # ==========================================================================
    # 3. Report Job Lookup & Time-Limited Download
    # ==========================================================================

    def get_report_job(self, job_id: str, *, tenant_context: TenantContext) -> ReportJob:
        """Retrieves asynchronous generation job status."""
        tc = require_tenant_context(tenant_context)
        job = self.repository.get_job(job_id, tenant_context=tc)
        if not job:
            raise ReportJobNotFoundException(job_id)
        return job

    def list_report_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[ReportJob]:
        """Lists generated report jobs for caller's tenant."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list_jobs(tenant_context=tc, limit=limit, offset=offset)

    def download_report(
        self,
        report_id: str,
        token: str,
        *,
        tenant_context: TenantContext,
    ) -> tuple[bytes, ReportJob]:
        """Validates security token, checks link expiry, records download audit, and returns bytes."""
        tc = require_tenant_context(tenant_context)

        # 1. Find job corresponding to report_id
        jobs = self.repository.list_jobs(tenant_context=tc, limit=500)
        target_job = next((j for j in jobs if j.download_url and report_id in j.download_url), None)
        if not target_job:
            raise ReportJobNotFoundException(f"No generation job found for report '{report_id}'.")

        # 2. Validate Security Token
        if not token or token != target_job.download_token:
            raise InvalidDownloadTokenException("Invalid or missing download security token.")

        # 3. Validate Time-Limited Expiration
        now = dt.datetime.now(dt.UTC)
        if target_job.expires_at and now > target_job.expires_at:
            raise DownloadLinkExpiredException(
                f"The download link for report '{report_id}' expired at {target_job.expires_at.isoformat()}."
            )

        # 4. Retrieve Artifact Bytes
        content = self.repository.get_artifact(report_id, tenant_context=tc)
        if not content:
            raise ReportJobNotFoundException(
                f"Report artifact '{report_id}' has been purged or is missing."
            )

        # 5. Mandatory Audit Trail Logging for Report Download
        self.audit_service.append_event(
            tenant_context=tc,
            event_in=AuditEventCreate(
                event_type=AuditEventType.REPORT_DOWNLOADED,
                actor_id=tc.email or tc.user_id or "anonymous",
                actor_roles=tc.roles,
                action="REPORT_DOWNLOADED",
                resource_type="REPORT_ARTIFACT",
                resource_id=report_id,
                details={
                    "job_id": target_job.id,
                    "template_id": target_job.template_id,
                    "format": target_job.format.value,
                    "filename": target_job.output_filename,
                    "file_size_bytes": len(content),
                    "token_validated": True,
                },
                correlation_id=tc.correlation_id,
            ),
        )

        logger.info(
            "Audited download of report '%s' (Job: %s) by %s in tenant %s",
            report_id,
            target_job.id,
            tc.email or tc.user_id,
            tc.tenant_id,
        )

        return content, target_job

    # ==========================================================================
    # 4. Phase 2 Flag-Gated Recurring Report Scheduling
    # ==========================================================================

    def create_schedule(
        self,
        template_id: str,
        parameters: ReportParameters,
        format_type: ExportFormat,
        cron_expression: str,
        recipients: list[str],
        storage_destination: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ScheduledReport:
        """Creates a recurring report schedule (Phase 2 capability)."""
        defn = self.get_template(template_id)
        if format_type not in defn.supported_formats:
            raise UnsupportedReportFormatException(
                f"Format '{format_type.value}' is not supported by template '{defn.id}'."
            )
        return self.scheduling_engine.create_schedule(
            template_id=defn.id,
            parameters=parameters,
            format_type=format_type,
            cron_expression=cron_expression,
            recipients=recipients,
            storage_destination=storage_destination,
            tenant_context=tenant_context,
        )

    def list_schedules(self, *, tenant_context: TenantContext) -> list[ScheduledReport]:
        """Lists recurring report schedules (Phase 2 capability)."""
        return self.scheduling_engine.list_schedules(tenant_context=tenant_context)


_global_report_service: ReportService | None = None
_service_lock = threading.Lock()


def get_report_service() -> ReportService:
    """Returns the singleton instance of ReportService."""
    global _global_report_service
    if _global_report_service is None:
        with _service_lock:
            if _global_report_service is None:
                _global_report_service = ReportService()
    return _global_report_service
