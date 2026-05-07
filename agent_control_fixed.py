"""
agent_control.py – Database-Backed Agent Control
==================================================

FIXED: Now uses database (AgentControlCommand model) instead of SharePoint.
Polling mechanism with automatic retry and error recovery.

This poller:
  ✓ Polls database every 2 minutes for pending commands
  ✓ Executes commands (restart, disable, install, etc.)
  ✓ Updates status in database
  ✓ Handles errors gracefully
  ✓ Never blocks main process
  ✓ Self-healing retry logic
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Tuple

logger = logging.getLogger("[AGENT-CONTROL]")
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(asctime)s %(levelname)s: %(message)s",
)

POLL_INTERVAL = 120  # 2 minutes
HOSTNAME = socket.gethostname().upper()


class AgentControlPoller:
    """
    Polls database for pending agent control commands and executes them.
    All operations target the local database, not SharePoint.
    Runs in a daemon thread; all errors are logged and handled gracefully.
    """

    def __init__(self, tenant_id: str = ""):
        """Initialize poller with optional tenant_id."""
        self.tenant_id = tenant_id
        self._running = True
        logger.info(f"AgentControlPoller initialized for hostname={HOSTNAME}, tenant={tenant_id}")

    def start_polling(self):
        """Start the polling loop (blocks until stop called)."""
        logger.info(f"Starting agent control polling loop (interval={POLL_INTERVAL}s)")
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"Polling iteration failed: {e}", exc_info=True)
            
            # Sleep in small chunks so we can stop quickly
            for _ in range(POLL_INTERVAL):
                if not self._running:
                    break
                time.sleep(1)

    def stop_polling(self):
        """Signal poller to stop."""
        logger.info("Stopping agent control polling")
        self._running = False

    def _poll_once(self) -> None:
        """Single polling iteration: fetch pending commands and execute them."""
        try:
            # Ensure we have Flask app context for database operations
            from web.app import app
            
            with app.app_context():
                pending = self._get_pending_commands()
                if not pending:
                    return  # No commands, continue
                
                logger.info(f"Found {len(pending)} pending commands for {HOSTNAME}")
                
                for command in pending:
                    try:
                        self._execute_command(command)
                    except Exception as e:
                        logger.error(f"Command execution failed: {e}", exc_info=True)
                        self._update_command_status(
                            command["id"],
                            "Failed",
                            f"Execution error: {str(e)[:500]}"
                        )
        except Exception as e:
            logger.error(f"Polling cycle failed: {e}", exc_info=True)

    # ──────────────────────────────────────────────────────────────────────
    # DATABASE OPERATIONS
    # ──────────────────────────────────────────────────────────────────────

    def _get_pending_commands(self) -> list:
        """Fetch all pending commands from database for this hostname."""
        try:
            from web.models import db, AgentControlCommand
            
            query = AgentControlCommand.query.filter_by(
                hostname=HOSTNAME,
                status="Pending"
            )
            
            if self.tenant_id:
                query = query.filter_by(tenant_id=self.tenant_id)
            
            commands = query.all()
            return [
                {
                    "id": cmd.id,
                    "hostname": cmd.hostname,
                    "action": cmd.action,
                    "payload": cmd.payload or "",
                    "status": cmd.status,
                    "tenant_id": cmd.tenant_id,
                }
                for cmd in commands
            ]
        except Exception as e:
            logger.error(f"Failed to fetch pending commands: {e}")
            return []

    def _update_command_status(self, cmd_id: int, status: str, message: str = "") -> bool:
        """Update command status and result in database."""
        try:
            from web.models import db, AgentControlCommand
            
            cmd = AgentControlCommand.query.get(cmd_id)
            if not cmd:
                logger.warning(f"Command {cmd_id} not found for update")
                return False
            
            cmd.status = status
            if message:
                cmd.result_message = message[:500]
            cmd.executed_at = datetime.now(timezone.utc)
            
            db.session.commit()
            logger.info(f"Command {cmd_id} status updated to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update command {cmd_id}: {e}")
            try:
                from web.models import db
                db.session.rollback()
            except:
                pass
            return False

    # ──────────────────────────────────────────────────────────────────────
    # ACTION EXECUTION
    # ──────────────────────────────────────────────────────────────────────

    def _execute_command(self, command: dict) -> None:
        """Execute a pending command by action type."""
        cmd_id = command["id"]
        action = command["action"].lower()
        payload = command.get("payload", "")
        
        logger.info(f"Executing command {cmd_id}: {action}")
        
        # Update status to InProgress
        self._update_command_status(cmd_id, "InProgress", "Execution started")
        
        success, message = False, "Unknown action"
        
        if action == "restartagent":
            success, message = self._restart_agent()
        elif action == "disableagent":
            success, message = self._disable_agent()
        elif action == "installsoftware":
            success, message = self._install_software(payload)
        elif action == "restart":
            success, message = self._restart_computer()
        elif action == "shutdown":
            success, message = self._shutdown_computer()
        else:
            message = f"Unknown action: {action}"
        
        # Update final status
        final_status = "Done" if success else "Failed"
        self._update_command_status(cmd_id, final_status, message)
        logger.info(f"Command {cmd_id} finished: {final_status} - {message}")

    def _restart_agent(self) -> Tuple[bool, str]:
        """Restart the ServerMonitor agent process."""
        try:
            # Try Windows Service first
            result = subprocess.run(
                ["powershell", "-Command",
                 "Restart-Service -Name 'ServerMonitor' -ErrorAction Stop"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, "Service restarted successfully."
        except Exception:
            pass

        # Fall back to process restart
        try:
            import sys
            subprocess.Popen([sys.executable] + sys.argv)
            threading.Timer(5, lambda: os._exit(0)).start()
            return True, "Process restarting in 5 seconds."
        except Exception as e:
            return False, f"Restart failed: {e}"

    def _disable_agent(self) -> Tuple[bool, str]:
        """Disable the agent by setting agent_enabled=False."""
        try:
            from auth.msal_auth import decrypt_config, encrypt_config
            config = decrypt_config() or {}
            config["agent_enabled"] = False
            encrypt_config(config)
            threading.Timer(5, lambda: os._exit(0)).start()
            return True, "Agent disabled. Process exiting in 5 seconds."
        except Exception as e:
            return False, f"Disable failed: {e}"

    def _install_software(self, payload: str) -> Tuple[bool, str]:
        """Install software via PowerShell."""
        try:
            if not payload:
                return False, "No installation payload provided"
            
            # Parse payload (expected to be JSON with 'installer_url' or 'software_name')
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                # Treat as raw PowerShell script
                data = {"script": payload}
            
            # Execute installation
            script = data.get("script") or f"choco install {data.get('software_name', 'curl')} -y"
            
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode == 0:
                return True, "Software installed successfully."
            else:
                return False, f"Installation failed: {result.stderr[:200]}"
        except Exception as e:
            return False, f"Installation error: {e}"

    def _restart_computer(self) -> Tuple[bool, str]:
        """Restart the computer."""
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Restart-Computer -Force"],
                capture_output=True,
                timeout=10,
            )
            return True, "Restart command sent. Computer restarting..."
        except Exception as e:
            return False, f"Restart failed: {e}"

    def _shutdown_computer(self) -> Tuple[bool, str]:
        """Shutdown the computer."""
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Stop-Computer -Force"],
                capture_output=True,
                timeout=10,
            )
            return True, "Shutdown command sent. Computer shutting down..."
        except Exception as e:
            return False, f"Shutdown failed: {e}"


def start_agent_control_poller(tenant_id: str = "") -> threading.Thread:
    """
    Start agent control polling in a background daemon thread.
    
    Args:
        tenant_id: Optional tenant ID for multi-tenant filtering
    
    Returns:
        Thread object (already started, daemon=True)
    """
    poller = AgentControlPoller(tenant_id=tenant_id)
    thread = threading.Thread(
        target=poller.start_polling,
        daemon=True,
        name="AgentControlPoller"
    )
    thread.start()
    return thread
