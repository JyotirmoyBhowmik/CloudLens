import os
import sys
sys.path.insert(0, os.getcwd())

from domain.control_tower.service import get_control_tower_service

def compare_tiles_to_sql():
    svc = get_control_tower_service()
    overview = svc.get_overview()
    panels_by_id = {p.id: p for p in overview.panels}

    # Execute SQL via the unified synchronous bridge
    sql_tenants = svc._execute_sql("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE type = 'DEMO') AS demo FROM tenants;")[0]
    sql_connectors = svc._execute_sql("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE lifecycle_state = 'ACTIVE') AS healthy, COUNT(*) FILTER (WHERE lifecycle_state = 'FAILED') AS failed FROM connectors;")[0]
    sql_jobs = svc._execute_sql("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'FAILED') AS failed FROM sync_jobs;")[0]
    sql_cost = svc._execute_sql("SELECT COALESCE(SUM(billed_cost), 0.0) FROM cost_fact;")[0][0]

    print("=== TILES VS SQL VERIFICATION ===")
    print("1. Tenants:")
    print(f"   SQL: total={sql_tenants[0]}, demo={sql_tenants[1]}")
    t_m = panels_by_id['tenants'].metrics
    print(f"   Tile metrics: active_tenants={t_m['active_tenants']}, demo_tenants={t_m['demo_tenants']}")
    assert sql_tenants[0] == t_m['active_tenants']
    assert sql_tenants[1] == t_m['demo_tenants']

    print("2. Connectors:")
    print(f"   SQL: total={sql_connectors[0]}, healthy={sql_connectors[1]}, failed={sql_connectors[2]}")
    c_m = panels_by_id['connectors'].metrics
    print(f"   Tile metrics: total_connectors={c_m['total_connectors']}, healthy_connectors={c_m['healthy_connectors']}")
    assert sql_connectors[0] == c_m['total_connectors']
    assert sql_connectors[1] == c_m['healthy_connectors']

    print("3. Jobs:")
    print(f"   SQL: total={sql_jobs[0]}, failed={sql_jobs[1]}")
    j_m = panels_by_id['jobs'].metrics
    print(f"   Tile metrics: total_recent_jobs={j_m['total_recent_jobs']}, failed_jobs={j_m['failed_jobs']}")
    assert sql_jobs[0] == j_m['total_recent_jobs']
    assert sql_jobs[1] == j_m['failed_jobs']

    print("4. Collection Cost:")
    cost_val = round(float(sql_cost), 2)
    cost_m = panels_by_id['collection_cost'].metrics
    print(f"   SQL: billed_cost_sum={cost_val}")
    print(f"   Tile metrics: daily_collection_cost_usd={cost_m['daily_collection_cost_usd']}")
    assert cost_val == cost_m['daily_collection_cost_usd']

    print("MATCH CONFIRMED: 100% exact match between SQL rows and Control Tower live tiles.")

if __name__ == '__main__':
    compare_tiles_to_sql()
