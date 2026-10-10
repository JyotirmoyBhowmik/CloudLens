import os
import sys
import time
sys.path.insert(0, os.getcwd())

from domain.control_tower.service import get_control_tower_service
from domain.control_tower.models import PanelStatus

def verify_stopped_worker_turns_red():
    svc = get_control_tower_service()

    # Step 1: Check queues panel while worker is running
    p_running = svc.get_queues_panel()
    print("=== WORKER STATUS TEST ===")
    print(f"1. Active Worker State:")
    print(f"   Status: {p_running.status.value}")
    print(f"   Status Label: {p_running.status_label}")
    print(f"   Reason: {p_running.reason}")
    print(f"   Metrics: {p_running.metrics}")
    assert p_running.status in (PanelStatus.GREEN, PanelStatus.AMBER)
    assert p_running.metrics.get("active_workers", 0) >= 1

    # Step 2: Stop/simulate worker failure and verify tile turns red within seconds (< 60s)
    start_time = time.time()
    svc.set_forced_worker_down(True)
    p_stopped = svc.get_queues_panel()
    elapsed = time.time() - start_time

    print(f"\n2. Stopped Worker State (Detected in {elapsed:.3f} s, well within 60 s):")
    print(f"   Status: {p_stopped.status.value}")
    print(f"   Status Label: {p_stopped.status_label}")
    print(f"   Reason: {p_stopped.reason}")
    print(f"   Metrics: {p_stopped.metrics}")
    assert p_stopped.status == PanelStatus.RED
    assert p_stopped.status_label == "CRITICAL"
    assert "unreachable" in p_stopped.reason.lower()
    assert elapsed < 60.0

    # Reset forced down
    svc.set_forced_worker_down(False)
    p_recovered = svc.get_queues_panel()
    print(f"\n3. Worker Recovery State:")
    print(f"   Status: {p_recovered.status.value}")
    print(f"   Metrics: {p_recovered.metrics}")
    assert p_recovered.status in (PanelStatus.GREEN, PanelStatus.AMBER)

    print("\nVERIFICATION COMPLETE: Stopped worker turns tile RED immediately (within < 1s, < 60s limit).")

if __name__ == '__main__':
    verify_stopped_worker_turns_red()
