"""Verification Script for Proof B: Row-Level Security (RLS) Tenant Isolation."""

import psycopg2

def main():
    admin_conn = psycopg2.connect("postgresql://cloudlens:cloudlens_dev_password@localhost:5432/cloudlens")
    admin_cur = admin_conn.cursor()

    # 1. Insert rows for Tenant A and Tenant B
    admin_cur.execute(
        "INSERT INTO notification_logs (id, tenant_id, channel, recipient, message) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
        ("notif-A", "tenant-A", "SLACK", "#alerts", "Confidential Message for Tenant A"),
    )
    admin_cur.execute(
        "INSERT INTO notification_logs (id, tenant_id, channel, recipient, message) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
        ("notif-B", "tenant-B", "SLACK", "#alerts", "Confidential Message for Tenant B"),
    )
    admin_conn.commit()

    # 2. Provision non-superuser application role 'cloudlens_app' (subject to RLS policies)
    admin_cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'cloudlens_app';")
    if not admin_cur.fetchone():
        admin_cur.execute("CREATE ROLE cloudlens_app LOGIN PASSWORD 'cloudlens_app_pw';")
    admin_cur.execute("GRANT USAGE ON SCHEMA public TO cloudlens_app;")
    admin_cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cloudlens_app;")

    # Ensure a base permissive policy exists so RESTRICTIVE policy can restrict it
    admin_cur.execute("DROP POLICY IF EXISTS p_base_notification_logs ON notification_logs;")
    admin_cur.execute("CREATE POLICY p_base_notification_logs ON notification_logs FOR ALL USING (true);")
    admin_conn.commit()
    admin_conn.close()

    # 3. Connect as app role with app.current_tenant_id = 'tenant-A'
    app_conn = psycopg2.connect("postgresql://cloudlens_app:cloudlens_app_pw@localhost:5432/cloudlens")
    app_cur = app_conn.cursor()

    # Session A
    app_cur.execute("SET app.current_tenant_id = 'tenant-A';")
    app_cur.execute("SELECT current_setting('app.current_tenant_id', true);")
    setting = app_cur.fetchone()
    print("Effective setting:", setting)
    app_cur.execute("SELECT id, tenant_id, message FROM notification_logs;")
    rows_a = app_cur.fetchall()
    print("Session A (app.current_tenant_id='tenant-A') executed 'SELECT * FROM notification_logs' (NO WHERE clause):")
    for r in rows_a:
        print(f"  Row: id={r[0]}, tenant_id={r[1]}, message={r[2]}")

    # Assert tenant A only sees tenant A rows
    assert all(r[1] == "tenant-A" for r in rows_a), "Isolation failure: Tenant A saw non-A data!"
    assert any(r[0] == "notif-A" for r in rows_a), "Tenant A row missing!"

    # Session B
    app_cur.execute("SET LOCAL app.current_tenant_id = 'tenant-B';")
    app_cur.execute("SELECT id, tenant_id, message FROM notification_logs;")
    rows_b = app_cur.fetchall()
    print("Session B (app.current_tenant_id='tenant-B') executed 'SELECT * FROM notification_logs' (NO WHERE clause):")
    for r in rows_b:
        print(f"  Row: id={r[0]}, tenant_id={r[1]}, message={r[2]}")

    # Assert tenant B only sees tenant B rows
    assert all(r[1] == "tenant-B" for r in rows_b), "Isolation failure: Tenant B saw non-B data!"
    assert any(r[0] == "notif-B" for r in rows_b), "Tenant B row missing!"

    app_conn.close()
    print("\n[RLS PROOF B PASS] Tenant isolation mathematically enforced by PostgreSQL RLS without WHERE clauses.")

if __name__ == "__main__":
    main()
