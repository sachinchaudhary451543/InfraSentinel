"""
sharepoint_server_control.py – ServerMonitor ISV
=================================================
COMPLETE DROP-IN REPLACEMENT.
Replaces the original 15-line stub with a full implementation.

Original stub preserved as comments at top for reference.
All original constants (SP_LIST, DB_PATH) kept.

New: ServerControlMonitor class that polls AgentControl list every 2 min,
dispatches to AgentControlPoller, and provides legacy check methods.
"""

# ── Original stub content (preserved as reference) ────────────────────────────
"""
SharePoint ServerControl Feature
- Checks ServerControl list for agent status/action
- If Status=Disabled, stops data push
- If Action=Delete, clears DB and stops service
"""

import os
import logging
import time
import sqlite3
import requests

# ── ORIGINAL constants ─────────────────────────────────────────────────────────
SP_LIST = "AgentControl"      # renamed from "ServerControl" for ISV; kept as var
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "ServerMetrics.db")

logging.basicConfig(
    level=logging.INFO,
    format='[SERVERCONTROL] %(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger("[SERVERCONTROL]")

POLL_INTERVAL = 120   # 2 minutes


class ServerControlMonitor:
    """
    Full implementation of the original stub's intent.
    Polls the AgentControl SharePoint list and dispatches control commands
    to the local agent via AgentControlPoller.
    """

    def __init__(self, site_url: str, access_token: str):
        self.site_url     = site_url.rstrip("/")
        self.access_token = access_token
        self._running     = True

        # Delegate actual execution to the full AgentControlPoller
        from agent_control import AgentControlPoller
        self._poller = AgentControlPoller(site_url, access_token)

    def check_once(self):
        """Single poll cycle."""
        self._poller.poll_once()

    def start(self):
        """Blocking poll loop. Run in a daemon thread from main.py."""
        logger.info(f"ServerControlMonitor started. Polling '{SP_LIST}' every {POLL_INTERVAL}s")
        while self._running:
            try:
                self.check_once()
            except Exception as e:
                logger.error(f"Control check error: {e}")
            time.sleep(POLL_INTERVAL)

    def stop(self):
        self._running = False
        self._poller.stop()

    # ── Legacy methods (original stub implied these) ──────────────────────

    def check_agent_status(self) -> str:
        """
        Returns 'active', 'disabled', or 'unknown'.
        Checks if this agent's Status == 'Disabled' in SharePoint.
        """
        import socket
        hostname = socket.gethostname().upper()
        try:
            url = (
                f"{self.site_url}/_api/web/lists/GetByTitle('{SP_LIST}')/items"
                f"?$filter=ServerName eq '{hostname}'"
                f"&$select=Status,Action&$top=1"
            )
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept":        "application/json;odata=verbose",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                items = r.json().get("d", {}).get("results", [])
                if items:
                    status = items[0].get("Status", "").lower()
                    return "disabled" if status == "disabled" else "active"
        except Exception as e:
            logger.warning(f"Agent status check failed: {e}")
        return "unknown"

    def delete_local_data(self):
        """
        Wipes local SQLite metrics DB.
        Called when Action=Delete is received.
        """
        try:
            if os.path.exists(DB_PATH):
                conn = sqlite3.connect(DB_PATH)
                c    = conn.cursor()
                c.execute("DELETE FROM metrics")
                c.execute("DELETE FROM vms")
                conn.commit()
                conn.close()
                logger.info("Local metrics DB wiped per Delete command.")
        except Exception as e:
            logger.error(f"Failed to wipe DB: {e}")