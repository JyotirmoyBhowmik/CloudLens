"""Dev Proof: Stop API container -> Alert email in Mailpit within 2 min -> Restart -> Resolved email.

Executes and verifies:
1. Stops `cloudlens-api` container.
2. Polls Prometheus alerts / Mailpit until firing ComponentDown email is received.
3. Restarts `cloudlens-api` container.
4. Polls Mailpit until resolved email is received.
"""

import json
import logging
import subprocess
import time
import urllib.request
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MAILPIT_API = "http://localhost:8025/api/v1/messages"
PROMETHEUS_ALERTS = "http://localhost:9090/api/v1/alerts"


def get_mailpit_messages() -> list[dict[str, Any]]:
    try:
        req = urllib.request.Request(MAILPIT_API)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("messages", [])
    except Exception as exc:
        logger.warning("Error fetching Mailpit messages: %s", exc)
        return []


def run_command(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def main():
    logger.info("=== Starting API-Down & Resolved Alert Dev Proof ===")
    initial_msgs = get_mailpit_messages()
    initial_ids = {m["ID"] for m in initial_msgs}
    logger.info("Initial message count in Mailpit: %d", len(initial_ids))

    # 1. Stop API container
    logger.info("Stopping container: cloudlens-api ...")
    run_command(["docker", "stop", "cloudlens-api"])
    stop_time = time.time()
    logger.info("cloudlens-api stopped at %s. Waiting for ComponentDown alert in Mailpit...", time.ctime(stop_time))

    firing_email = None
    # Wait up to 110s for alert (60s evaluation + 15s scrape + Alertmanager group_wait)
    for i in range(24):
        time.sleep(5)
        elapsed = time.time() - stop_time
        msgs = get_mailpit_messages()
        new_msgs = [m for m in msgs if m["ID"] not in initial_ids]
        
        # Look for ComponentDown firing email
        for msg in new_msgs:
            subject = msg.get("Subject", "")
            if "ComponentDown" in subject and "FIRING" in subject.upper():
                firing_email = msg
                break
        
        if firing_email:
            logger.info("Found FIRING alert email in Mailpit after %.1fs! Subject: %s", elapsed, firing_email["Subject"])
            break
        logger.info("Elapsed: %.1fs, waiting for alert email... (current new emails: %d)", elapsed, len(new_msgs))

    assert firing_email is not None, "ComponentDown alert email did not arrive in Mailpit within 120s!"

    # 2. Restart API container
    logger.info("Restarting container: cloudlens-api ...")
    run_command(["docker", "start", "cloudlens-api"])
    restart_time = time.time()
    logger.info("cloudlens-api started at %s. Waiting for RESOLVED email in Mailpit...", time.ctime(restart_time))

    resolved_email = None
    # Wait up to 90s for resolved notification
    for i in range(18):
        time.sleep(5)
        elapsed = time.time() - restart_time
        msgs = get_mailpit_messages()
        new_msgs = [m for m in msgs if m["ID"] not in initial_ids and m["ID"] != firing_email["ID"]]
        
        for msg in new_msgs:
            subject = msg.get("Subject", "")
            if "ComponentDown" in subject and "RESOLVED" in subject.upper():
                resolved_email = msg
                break
        
        if resolved_email:
            logger.info("Found RESOLVED alert email in Mailpit after %.1fs! Subject: %s", elapsed, resolved_email["Subject"])
            break
        logger.info("Elapsed: %.1fs, waiting for resolved email...", elapsed)

    assert resolved_email is not None, "Resolved email did not arrive in Mailpit within 90s!"

    logger.info("\n>>> DEV PROOF COMPLETED SUCCESSFULLY! <<<")
    logger.info("Firing Email Subject:   %s", firing_email["Subject"])
    logger.info("Firing Email To:        %s", [t["Address"] for t in firing_email.get("To", [])])
    logger.info("Resolved Email Subject: %s", resolved_email["Subject"])
    logger.info("Resolved Email To:      %s", [t["Address"] for t in resolved_email.get("To", [])])


if __name__ == "__main__":
    main()
