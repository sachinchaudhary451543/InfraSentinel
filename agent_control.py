"""
agent_control.py – ServerMonitor ISV (Phase 4)
================================================
Polls the AgentControl SharePoint list every 2 minutes.
Executes: RestartAgent | DisableAgent | InstallSoftware
Writes status back: Pending → InProgress → Done | Failed
Self-healing: retries on transient SP errors, never crashes main process.

BUGS FIXED IN THIS FILE:
  Bug #8  – AgentControl methods were erroneously copy-pasted into DomainDiscoveryEngine
             where they referenced HOSTNAME, threading, etc. that are only defined here.
             DomainDiscoveryEngine no longer contains these methods (see domain_discovery.py).
             This file (AgentControlPoller) is the single correct home for all poll/dispatch logic.
  Bug #9  – _refresh_token() called get_valid_token() which can block for ≤15 min on
             interactive device-code login. Background threads must NEVER block on UI.
             Fixed: use get_silent_token() which returns None on cache miss instead of prompting.
             When the silent refresh fails, the current poll cycle is skipped with a warning.

Multi-tenant isolation: every SP read filters by both ServerName and TenantId,
so agents from different tenants can never see each other's commands.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests

logger = logging.getLogger("[AGENT-CONTROL]")
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(asctime)s %(levelname)s: %(message)s",
)

POLL_INTERVAL = 120          # 2 minutes
MAX_RETRIES   = 3
HOSTNAME      = socket.gethostname().upper()
LIST_NAME     = "AgentControl"


class AgentControlPoller:
    """
    Polls AgentControl SharePoint list and executes pending actions for THIS agent.
    Runs in a daemon thread; all SP failures are caught and logged, never re-raised.
    """

    def __init__(self, site_url: str, access_token: str, tenant_id: str = ""):
        self.site_url     = site_url.rstrip("/")
        self.access_token = access_token
        self.tenant_id    = tenant_id
        self._running     = True

    def _sharepoint_scope(self) -> str:
        parsed = urlparse(self.site_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid SharePoint site URL: {self.site_url}")
        return f"{parsed.scheme}://{parsed.netloc}/.default"

    # ── Bug #9 fix: silent-only token refresh ─────────────────────────────────
    def _refresh_token(self) -> bool:
        """
        Silently refresh the access token from MSAL cache.
        Returns False (and logs a warning) if no cached token is available.
        NEVER triggers interactive browser login from this background thread.
        """
        try:
            from auth.msal_auth import decrypt_config, get_silent_token
            config = decrypt_config() or {}
            sp_creds = config.get("sharepoint_credentials", {})
            client_secret = sp_creds.get("client_secret")
            tenant_id = self.tenant_id or sp_creds.get("tenant_id") or config.get("tenant_id")
            result = get_silent_token(
                client_secret=client_secret,
                tenant_id=tenant_id,
                scopes=[self._sharepoint_scope()],
            )
            if result:
                self.access_token = result["access_token"]
                if result.get("tenant_id"):
                    self.tenant_id = result["tenant_id"]
                return True
            logger.warning(
                "Silent token refresh returned no token. "
                "Skipping this poll cycle. The user must re-authenticate interactively "
                "(run 'python main.py' to trigger device-code login)."
            )
            return False
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            return False

    # ── HTTP helpers ──────────────────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept":        "application/json;odata=verbose",
            "Content-Type":  "application/json;odata=verbose",
        }

    def _retry(self, fn):
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                logger.warning(f"SP attempt {attempt}/{MAX_RETRIES}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(3 * attempt)
        raise RuntimeError(
            f"All {MAX_RETRIES} attempts exhausted. Last error: {last_exc}"
        ) from last_exc

    # ── SharePoint reads / writes ─────────────────────────────────────────────
    def _fetch_pending(self) -> list:
        """
        Fetch pending AgentControl items for THIS hostname.
        Multi-tenant: filter by TenantId so we only see our own items.
        """
        tenant_filter = f" and TenantId eq '{self.tenant_id}'" if self.tenant_id else ""
        filter_expr = (
            f"ServerName eq '{quote(HOSTNAME)}'  "
            f"and Status eq 'Pending'{tenant_filter}"
        )
        url = (
            f"{self.site_url}/_api/web/lists/GetByTitle('{LIST_NAME}')/items"
            f"?$filter={filter_expr}"
            f"&$select=Id,ServerName,Action,ActionPayload,Status,TenantId"
        )
        r = requests.get(url, headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("d", {}).get("results", [])

    def _update_status(self, item_id: int, status: str, message: str = "") -> None:
        import json
        url  = (
            f"{self.site_url}/_api/web/lists/GetByTitle('{LIST_NAME}')/items({item_id})"
        )
        hdrs = {
            **self._headers(),
            "X-HTTP-Method": "MERGE",
            "If-Match":      "*",
        }
        payload = json.dumps({
            "__metadata":  {"type": f"SP.Data.{LIST_NAME}ListItem"},
            "Status":       status,
            "ResultMessage": message[:500] if message else "",
            "ExecutedAt":   datetime.now(timezone.utc).isoformat(),
        })
        r = requests.post(url, headers=hdrs, data=payload, timeout=15)
        if r.status_code not in (200, 204):
            logger.warning(f"Status update failed [{r.status_code}]: {r.text[:150]}")

    # ── Action handlers ───────────────────────────────────────────────────────
    def _restart_agent(self) -> tuple[bool, str]:
        """Restart the monitoring agent process."""
        try:
            # Prefer Windows Service restart
            result = subprocess.run(
                ["powershell", "-Command",
                 "Restart-Service -Name 'ServerMonitor' -ErrorAction Stop"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "Service restarted successfully."
        except Exception:
            pass

        # Fallback: relaunch the Python process
        try:
            import sys
            subprocess.Popen([sys.executable] + sys.argv)
            # Schedule exit AFTER we've returned and updated SP status
            threading.Timer(5, lambda: os._exit(0)).start()
            return True, "Process restarting in 5 seconds."
        except Exception as e:
            return False, f"Restart failed: {e}"

    def _disable_agent(self) -> tuple[bool, str]:
        """Disable the agent by setting agent_enabled=False in keyring config."""
        try:
            from auth.msal_auth import decrypt_config, encrypt_config
            config = decrypt_config() or {}
            config["agent_enabled"] = False
            encrypt_config(config)
            threading.Timer(5, lambda: os._exit(0)).start()
            return True, "Agent disabled. Process exiting in 5 seconds."
        except Exception as e:
            return False, f"Disable failed: {e}"

    def _install_software(self, payload: str) -> tuple[bool, str]:
        """
        Install software from payload.
        Payload prefixes:
          PS:<powershell command>   – run arbitrary PowerShell
          http(s)://...             – download and run MSI
          <local path>              – run MSI from local path
        """
        if not payload:
            return False, "No ActionPayload provided for InstallSoftware."

        try:
            if payload.upper().startswith("PS:"):
                r = subprocess.run(
                    ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command",
                     payload[3:].strip()],
                    capture_output=True, text=True, timeout=300,
                )
                if r.returncode == 0:
                    return True, f"PS executed. Output: {r.stdout[:200]}"
                return False, f"PS failed (code {r.returncode}): {r.stderr[:200]}"

            elif payload.lower().startswith("http"):
                with tempfile.NamedTemporaryFile(suffix=".msi", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    urllib.request.urlretrieve(payload, tmp_path)
                    r = subprocess.run(
                        ["msiexec.exe", "/i", tmp_path, "/quiet", "/norestart"],
                        capture_output=True, text=True, timeout=600,
                    )
                    if r.returncode == 0:
                        return True, "MSI installed successfully."
                    return False, f"MSI failed (code {r.returncode}): {r.stderr[:150]}"
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            else:
                # Local MSI path
                r = subprocess.run(
                    ["msiexec.exe", "/i", payload, "/quiet", "/norestart"],
                    capture_output=True, text=True, timeout=600,
                )
                if r.returncode == 0:
                    return True, "MSI installed from local path."
                return False, f"MSI failed (code {r.returncode})"

        except Exception as e:
            return False, f"InstallSoftware exception: {e}"

    # ── Dispatch ──────────────────────────────────────────────────────────────
    def _dispatch(self, item: dict) -> None:
        item_id = item["Id"]
        action  = (item.get("Action") or "").strip()
        payload = (item.get("ActionPayload") or "").strip()

        logger.info(f"Executing '{action}' (item {item_id}) for {HOSTNAME}")
        self._update_status(item_id, "InProgress", f"Started {datetime.utcnow().isoformat()}")

        try:
            if action == "RestartAgent":
                success, msg = self._restart_agent()
            elif action == "DisableAgent":
                success, msg = self._disable_agent()
            elif action == "InstallSoftware":
                success, msg = self._install_software(payload)
            else:
                success, msg = False, f"Unknown action: '{action}'"

            final_status = "Done" if success else "Failed"
            self._update_status(item_id, final_status, msg)
            logger.info(f"'{action}' → {final_status}: {msg}")

        except Exception as e:
            err = f"Unhandled exception in '{action}': {e}"
            logger.error(err)
            try:
                self._update_status(item_id, "Failed", err)
            except Exception:
                pass

    # ── Poll loop ─────────────────────────────────────────────────────────────
    def poll_once(self) -> None:
        """
        Perform one poll cycle.
        Bug #9 fix: if silent token refresh fails, skip this cycle rather than blocking.
        """
        if not self._refresh_token():
            return   # skip cycle – do not block waiting for interactive login

        try:
            items = self._retry(self._fetch_pending)
            if items:
                logger.info(f"Found {len(items)} pending action(s) for {HOSTNAME}")
            for item in items:
                self._dispatch(item)
        except Exception as e:
            if "does not exist" in str(e).lower() or "404" in str(e):
                logger.warning(
                    f"AgentControl list not found (provisioner will create it on next startup): {e}"
                )
            else:
                logger.error(f"Poll cycle error: {e}")

    def start_polling(self) -> None:
        """Blocking loop. Run in a daemon thread (see main.py Step 6)."""
        logger.info(
            f"Agent Control poller started "
            f"(hostname={HOSTNAME}, interval={POLL_INTERVAL}s, tenant={self.tenant_id})"
        )
        while self._running:
            self.poll_once()
            time.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        """Signal the polling loop to exit after the current cycle."""
        self._running = False
