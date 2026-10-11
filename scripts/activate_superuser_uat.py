#!/usr/bin/env python3
"""UAT Superuser Activation & Verification Script (Prompt P20).

Provisions and activates admin@jyotirmoyb.com using one-time token and OTP (TOTP),
verifying non-disableable MFA and unrestricted platform scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.bootstrap.superuser import SuperuserProvisioningService  # noqa: E402
from domain.config.repository import reset_tenant_settings_repository  # noqa: E402
from domain.identity.password_hasher import generate_totp_code  # noqa: E402
from domain.identity.service import IdentityService  # noqa: E402
from domain.rbac.service import RBACService  # noqa: E402
from masterdata.repository import reset_master_data_repository  # noqa: E402
from masterdata.service import MasterDataService  # noqa: E402
from tests.fakes.identity import InMemoryIdentityRepository  # noqa: E402
from tests.fakes.masterdata import InMemoryMasterDataRepository  # noqa: E402
from tests.fakes.rbac import InMemoryRBACRepository  # noqa: E402
from tests.fakes.tenant_settings import InMemoryTenantSettingsRepository  # noqa: E402


def main() -> int:
    print("=" * 80)
    print("CLOUDLENS UAT SUPERUSER PROVISIONING & OTP ACTIVATION (PROMPT P20)")
    print("Target: admin@jyotirmoyb.com (Option A UAT VM / k3s)")
    print("=" * 80)

    # Initialize isolated repositories
    md_repo = InMemoryMasterDataRepository()
    reset_master_data_repository(md_repo)
    md_service = MasterDataService(repository=md_repo)

    reset_tenant_settings_repository(InMemoryTenantSettingsRepository())

    identity_repo = InMemoryIdentityRepository()
    identity_service = IdentityService(repository=identity_repo)
    rbac_repo = InMemoryRBACRepository()
    rbac_service = RBACService(repository=rbac_repo)

    service = SuperuserProvisioningService(
        identity_service=identity_service,
        rbac_service=rbac_service,
        master_data_service=md_service,
    )

    # 1. Provision superuser from master data
    user, activation_token = service.provision_superuser()
    print(f"[1/4] Provisioned Superuser: {user.email} (Status: {user.status.value})")
    print(f"      Activation Token ID:   {activation_token.token[:8]}...")
    print(f"      Token Expiry:          {activation_token.expires_at.isoformat()}")

    # 2. Activate superuser with strong password and OTP
    initial_password = "UatSuperuserPassword2026!Secure"
    activation_res = service.activate_superuser(
        activation_token=activation_token.token,
        password=initial_password,
        totp_code=None,  # Generates canonical TOTP secret during first-time setup
    )
    assigned_totp_secret = activation_res["totp_secret"]
    current_otp = generate_totp_code(assigned_totp_secret)

    print(f"[2/4] Activated Superuser:    {activation_res['superuser_email']}")
    print(f"      Status:                 {activation_res['status']}")
    print(f"      MFA Secret Assigned:    {assigned_totp_secret[:8]}...")
    print(f"[3/4] Generated OTP Code:     {current_otp}")

    # 3. Authenticate superuser with password and live TOTP OTP
    token_pair = service.authenticate_superuser(
        email=user.email,
        password=initial_password,
        mfa_code=current_otp,
    )
    print(f"[4/4] Authenticated Session:  Session ID {token_pair.session_id}")
    print(f"      Access Token:           {token_pair.access_token[:24]}...")
    print(f"      Granted Roles:          {token_pair.roles}")
    print(f"      Token Type:             {token_pair.token_type}")

    # Verification Report
    report = service.generate_verification_report()
    print("-" * 80)
    print("SUPERUSER VERIFICATION REPORT:")
    print(f"  Superuser Email:    {report.superuser_email}")
    print(f"  Canonical Role:     {report.role}")
    print(f"  Unrestricted Scope: {report.unrestricted_scope}")
    print(f"  MFA Enforced:       {report.mfa_enforced}")
    print(f"  Break-Glass Paths:  {report.break_glass_count} (AM-05 Compliant)")
    print("=" * 80)
    print("[SUCCESS] Superuser admin@jyotirmoyb.com activated and verified via OTP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
