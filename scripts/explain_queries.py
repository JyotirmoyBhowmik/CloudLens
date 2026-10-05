"""EXPLAIN query verification script for Proof E."""

import psycopg2

def main():
    conn = psycopg2.connect("postgresql://cloudlens:cloudlens_dev_password@localhost:5432/cloudlens")
    cur = conn.cursor()

    queries = [
        (
            "Query 1: Audit Event by Tenant and Entity (Tier 1)",
            "EXPLAIN SELECT * FROM audit_event WHERE tenant_id = 't-test' AND entity_type = 'User' AND occurred_at >= NOW() - INTERVAL '30 days';"
        ),
        (
            "Query 2: Active Overrides by Tenant and Status (Tier 1)",
            "EXPLAIN SELECT * FROM overrides WHERE tenant_id = 't-test' AND status = 'ACTIVE';"
        ),
        (
            "Query 3: Notification Logs by Tenant and Channel (Tier 1)",
            "EXPLAIN SELECT * FROM notification_logs WHERE tenant_id = 't-test' AND channel = 'SLACK';"
        ),
    ]

    for title, q in queries:
        print(f"=== {title} ===")
        print(f"SQL: {q}")
        cur.execute(q)
        for row in cur.fetchall():
            print(f"  {row[0]}")
        print()

    conn.close()

if __name__ == "__main__":
    main()
