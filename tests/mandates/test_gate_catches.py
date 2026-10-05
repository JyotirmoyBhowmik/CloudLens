"""Self-test suite for extended Hard-Coding Quality Gate (Prompt R-QUAL Items 4 & 6).

Feeds the AST gate synthetic bad code files for each rule 4.1-4.5 and asserts that
every violation is accurately detected and classified.
"""

from __future__ import annotations

from scripts.check_no_hardcoded_constants import scan_code


def test_gate_catches_rule_4_1_email_literals():
    """Rule 4.1: Gate must catch hardcoded email literals in application modules."""
    bad_code = '''
def send_notification():
    recipient = "finops-lead@enterprise-cloud.org"
    return f"Dispatching alert to {recipient}"
'''
    violations, _ = scan_code(bad_code, rel_path="api/cloudlens_api/notifications.py")
    assert any(v.target_master == "RULE_4_1_EMAIL_LITERAL" for v in violations)
    email_violation = next(v for v in violations if v.target_master == "RULE_4_1_EMAIL_LITERAL")
    assert "finops-lead@enterprise-cloud.org" in email_violation.literal_value


def test_gate_catches_rule_4_2_identity_attribute_comparisons():
    """Rule 4.2: Gate must catch comparisons between identity attributes and string literals."""
    bad_code = '''
def check_access(auth_context):
    if auth_context.role == "GLOBAL_ADMIN":
        return True
    if auth_context.email == "root@system.internal":
        return True
    return False
'''
    violations, _ = scan_code(bad_code, rel_path="domain/identity/guards.py")
    assert any(v.target_master == "RULE_4_2_IDENTITY_COMPARISON" for v in violations)
    matched = [v for v in violations if v.target_master == "RULE_4_2_IDENTITY_COMPARISON"]
    assert len(matched) >= 2


def test_gate_catches_rule_4_3_secret_defaults():
    """Rule 4.3: Gate must catch secret/credential function defaults and Field(default=...) literals."""
    bad_code = '''
from pydantic import BaseModel, Field

def authenticate_client(api_key: str = "hardcoded-secret-key-xyz"):
    pass

class ProviderConfig(BaseModel):
    vault_token: str = Field(default="dev-vault-token-cloudlens")
'''
    violations, _ = scan_code(bad_code, rel_path="domain/credentials/config.py")
    assert any(v.target_master == "RULE_4_3_SECRET_DEFAULT" for v in violations)
    secret_violations = [v for v in violations if v.target_master == "RULE_4_3_SECRET_DEFAULT"]
    assert len(secret_violations) >= 2


def test_gate_catches_rule_4_4_numeric_comparisons_in_financial_domains():
    """Rule 4.4: Gate must catch Decimal and numeric literals in comparison inside reconciliation/statements/thresholds."""
    bad_code = '''
from decimal import Decimal

def evaluate_tolerance(diff: Decimal) -> bool:
    if diff > Decimal("25.00"):
        return False
    if diff > 10.5:
        return False
    return True
'''
    violations, _ = scan_code(bad_code, rel_path="domain/cost/reconciliation/evaluator.py")
    assert any(v.target_master == "RULE_4_4_NUMERIC_COMPARISON" for v in violations)
    num_violations = [v for v in violations if v.target_master == "RULE_4_4_NUMERIC_COMPARISON"]
    assert len(num_violations) >= 2


def test_gate_catches_rule_4_5_hardcoded_fixture_dicts():
    """Rule 4.5: Gate must catch modules with >3 hardcoded people/resource fixture dicts."""
    bad_code = '''
# Non-test, non-synthetic production module with hardcoded fixture dictionaries
item_one = {"owner_email": "alice@cloud.corp", "department": "Core Banking"}
item_two = {"actor": "bob@cloud.corp", "role": "engineer"}
item_three = {"author": "charlie@cloud.corp", "title": "architect"}
item_four = {"creator": "dave@cloud.corp", "team": "devops"}
'''
    violations, _ = scan_code(bad_code, rel_path="domain/inventory/roster.py")
    assert any(v.target_master == "RULE_4_5_FIXTURE_DICTS" for v in violations)
    fixture_violations = [v for v in violations if v.target_master == "RULE_4_5_FIXTURE_DICTS"]
    assert len(fixture_violations) >= 4
