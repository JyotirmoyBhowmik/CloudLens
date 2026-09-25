"""Unit Tests for Append-Only Audit Event Enforcement.

Acceptance Criteria:
- An attempt to delete an audit row fails at the database level.
- An attempt to update an audit row fails at the database level.
"""

from typing import Any

from db.schema.triggers import (
    AUDIT_APPEND_ONLY_FUNCTION_SQL,
    AUDIT_NO_DELETE_TRIGGER_SQL,
    AUDIT_NO_UPDATE_TRIGGER_SQL,
    apply_audit_append_only_triggers,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.executed_statements: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> Any:
        _ = params
        sql = str(statement)
        self.executed_statements.append(sql)
        return None


def test_append_only_trigger_installation():
    """Verify triggers forbidding UPDATE and DELETE on audit_event are generated and applied."""
    conn = RecordingConnection()
    apply_audit_append_only_triggers(conn=conn)  # type: ignore[arg-type]

    # Verify function definition
    assert any("enforce_audit_event_append_only()" in s for s in conn.executed_statements)
    assert any(
        "audit_event table is append-only at the database level" in s
        for s in conn.executed_statements
    )

    # Verify triggers
    assert any("CREATE TRIGGER trg_audit_event_no_update" in s for s in conn.executed_statements)
    assert any("CREATE TRIGGER trg_audit_event_no_delete" in s for s in conn.executed_statements)
    assert any(
        "REVOKE UPDATE, DELETE, TRUNCATE ON audit_event" in s for s in conn.executed_statements
    )


def test_audit_append_only_ddl_syntax():
    """Verify trigger syntax contains explicit RAISE EXCEPTION on mutation."""
    assert "BEFORE UPDATE ON audit_event" in AUDIT_NO_UPDATE_TRIGGER_SQL
    assert "BEFORE DELETE ON audit_event" in AUDIT_NO_DELETE_TRIGGER_SQL
    assert (
        "RAISE EXCEPTION 'PERMISSION_DENIED: audit_event table is append-only"
        in AUDIT_APPEND_ONLY_FUNCTION_SQL
    )
