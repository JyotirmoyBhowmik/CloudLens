"""CloudLens System Bootstrap REST API Endpoints (Prompt 49A).

Enforces:
- POST /api/v1/system/bootstrap/pre-identity: Executes pre-identity bootstrap.
- GET /api/v1/system/bootstrap/pre-identity/status: Retrieves verification report.
"""

from fastapi import APIRouter, Header, Query

from domain.bootstrap import (
    PreIdentityVerificationReport,
    get_pre_identity_bootstrap_service,
)

router = APIRouter(prefix="/api/v1/system/bootstrap", tags=["System Bootstrap"])


@router.post("/pre-identity", response_model=PreIdentityVerificationReport)
def run_pre_identity_bootstrap(
    dry_run: bool = Query(default=False, description="Dry-run simulation mode"),
    x_correlation_id: str | None = Header(default=None),
) -> PreIdentityVerificationReport:
    """Executes the pre-identity system bootstrap sequence.

    Seeds all master data, creates the system tenant, registers built-in roles,
    and initialises the audit stream. Zero user identities or credentials are created.
    """
    service = get_pre_identity_bootstrap_service()
    return service.bootstrap(dry_run=dry_run, correlation_id=x_correlation_id)


@router.get("/pre-identity/status", response_model=PreIdentityVerificationReport | dict)
def get_pre_identity_bootstrap_status() -> PreIdentityVerificationReport | dict:
    """Retrieves current pre-identity bootstrap verification report."""
    service = get_pre_identity_bootstrap_service()
    report = service.get_verification_report()
    if report is None:
        if service.is_initialised():
            report = service.bootstrap(dry_run=True)
        else:
            return {
                "status": "NOT_INITIALISED",
                "is_already_initialized": False,
                "is_interactively_usable": False,
                "message": "Pre-identity bootstrap has not yet been executed.",
            }
    return report
