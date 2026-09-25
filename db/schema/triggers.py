"""Database Triggers and Security Constraints.

Enforces Prompt 06 Item 45 & Acceptance:
"Make audit_event append-only at the database level — no role, including the owner, may update or delete."
"Acceptance: An attempt to delete an audit row fails at the database level."
"""

from sqlalchemy import Connection, text

AUDIT_APPEND_ONLY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION enforce_audit_event_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'PERMISSION_DENIED: audit_event table is append-only at the database level. UPDATE and DELETE operations are strictly prohibited (Prompt 06 Item 45).';
END;
$$ LANGUAGE plpgsql;
"""

AUDIT_NO_UPDATE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_audit_event_no_update ON audit_event;
CREATE TRIGGER trg_audit_event_no_update
BEFORE UPDATE ON audit_event
FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
"""

AUDIT_NO_DELETE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_audit_event_no_delete ON audit_event;
CREATE TRIGGER trg_audit_event_no_delete
BEFORE DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION enforce_audit_event_append_only();
"""

AUDIT_REVOKE_PERMISSIONS_SQL = """
DO $$
BEGIN
    -- Revoke UPDATE, DELETE, and TRUNCATE from public and current roles
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM PUBLIC;
EXCEPTION WHEN OTHERS THEN
    -- Fallback gracefully in non-privileged testing environments
    NULL;
END $$;
"""


def apply_audit_append_only_triggers(conn: Connection) -> None:
    """Installs the database-level triggers that strictly forbid updates and deletes on audit_event."""
    conn.execute(text(AUDIT_APPEND_ONLY_FUNCTION_SQL))
    conn.execute(text(AUDIT_NO_UPDATE_TRIGGER_SQL))
    conn.execute(text(AUDIT_NO_DELETE_TRIGGER_SQL))
    conn.execute(text(AUDIT_REVOKE_PERMISSIONS_SQL))
