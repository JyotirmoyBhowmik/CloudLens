"""Audit Test Proving Domain Services Do Not Rely On In-Memory Dictionaries (Prompt P04).

Enforces:
- Pattern P1 / P3 / P6: Authoritative repository protocols backed by PostgreSQL.
- Zero mutable dictionary singletons acting as sources of truth for Tier-1 entities:
  1. Identity & Users (identity_service._repo is SqlIdentityRepository)
  2. Sessions (identity_service._sessions is a dynamic DB proxy)
  3. User By Email (identity_service._users_by_email is a dynamic DB proxy)
  4. RBAC Scope Grants (rbac_service._repo is SqlRBACRepository)
  5. RBAC Custom Roles (permission_catalogue._repo is SqlRBACRepository)
  6. Credentials (credential_service._repo is SqlCredentialRepository)
  7. Overrides (override_service.repository is SqlOverrideRepository)
  8. Feature Flags (get_feature_flag_repository() is SqlFeatureFlagRepository)
  9. Master Data (get_master_data_repository() is SqlMasterDataRepository)
  10. Audit (get_audit_repository() is SqlAuditRepository)
"""

import pytest

from domain.audit.repository import SqlAuditRepository, get_audit_repository
from domain.audit.service import get_audit_service
from domain.config.feature_flags_repository import SqlFeatureFlagRepository, get_feature_flag_repository
from domain.credentials.repository import SqlCredentialRepository
from domain.credentials.service import get_credential_service
from domain.identity.repository import SqlIdentityRepository
from domain.identity.service import get_identity_service
from domain.overrides.repository import SqlOverrideRepository
from domain.overrides.service import get_override_service
from domain.rbac.catalogue import get_permission_catalogue
from domain.rbac.repository import SqlRBACRepository
from domain.rbac.service import get_rbac_service
from masterdata.repository import SqlMasterDataRepository, get_master_data_repository
from masterdata.service import get_master_data_service

pytestmark = [pytest.mark.realdb]


def test_identity_service_not_in_dict_holder():
    service = get_identity_service()
    repo = service.repository

    # Assert repo is real PostgreSQL repository
    assert isinstance(repo, SqlIdentityRepository), f"Expected SqlIdentityRepository, got {type(repo)}"
    assert repo.is_in_memory is False

    # Assert _users is a proxy, not a standard raw dict singleton
    users_proxy = service._users
    assert type(users_proxy) is not dict, "service._users must be a dynamic DB proxy class, not a raw dict"

    # Assert _users_by_email is a proxy
    email_proxy = service._users_by_email
    assert type(email_proxy) is not dict, "service._users_by_email must be a dynamic DB proxy class, not a raw dict"

    # Assert _sessions is a proxy
    sess_proxy = service._sessions
    assert type(sess_proxy) is not dict, "service._sessions must be a dynamic DB proxy class, not a raw dict"


def test_rbac_services_not_in_dict_holder():
    # RBAC Service
    rbac = get_rbac_service()
    assert isinstance(rbac.repository, SqlRBACRepository), f"Expected SqlRBACRepository, got {type(rbac.repository)}"
    assert rbac.repository.is_in_memory is False

    # Permission Catalogue
    cat = get_permission_catalogue()
    assert isinstance(cat.repository, SqlRBACRepository), f"Expected SqlRBACRepository, got {type(cat.repository)}"
    assert cat.repository.is_in_memory is False


def test_credentials_service_not_in_dict_holder():
    cred_service = get_credential_service()
    assert isinstance(cred_service.repository, SqlCredentialRepository), f"Expected SqlCredentialRepository, got {type(cred_service.repository)}"
    assert cred_service.repository.is_in_memory is False


def test_overrides_service_not_in_dict_holder():
    override_service = get_override_service()
    assert isinstance(override_service.repository, SqlOverrideRepository), f"Expected SqlOverrideRepository, got {type(override_service.repository)}"
    assert override_service.repository.is_in_memory is False


def test_feature_flags_not_in_dict_holder():
    ff_repo = get_feature_flag_repository()
    assert isinstance(ff_repo, SqlFeatureFlagRepository), f"Expected SqlFeatureFlagRepository, got {type(ff_repo)}"
    assert ff_repo.is_in_memory is False


def test_masterdata_service_not_in_dict_holder():
    md_repo = get_master_data_repository()
    assert isinstance(md_repo, SqlMasterDataRepository), f"Expected SqlMasterDataRepository, got {type(md_repo)}"
    assert md_repo.is_in_memory is False


def test_audit_service_not_in_dict_holder():
    audit_repo = get_audit_repository()
    assert isinstance(audit_repo, SqlAuditRepository), f"Expected SqlAuditRepository, got {type(audit_repo)}"
    assert audit_repo.is_in_memory is False
