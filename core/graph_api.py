"""
core/graph_api.py - Microsoft Graph API Integration
====================================================

Replaces SharePoint REST API with Graph API for all operations.
All SharePoint list operations now use Microsoft Graph endpoints.
"""

import logging
from typing import Dict, List, Optional
import requests

logger = logging.getLogger("[GRAPH-API]")


class GraphAPIClient:
    """Microsoft Graph API client for SharePoint lists and items."""
    
    def __init__(self, access_token: str, tenant_id: str = ""):
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.base_url = "https://graph.microsoft.com/v1.0"
    
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
    
    # ──────────────────────────────────────────────────────────────────────
    # AGENT CONTROL OPERATIONS (DB-backed fallback only)
    # ──────────────────────────────────────────────────────────────────────
    
    def get_pending_commands(self, hostname: str) -> List[Dict]:
        """
        Get pending agent control commands from database.
        NOTE: This now uses database fallback, not SharePoint.
        """
        from web.models import db, AgentControlCommand
        try:
            commands = AgentControlCommand.query.filter_by(
                hostname=hostname,
                status="Pending"
            ).all()
            return [
                {
                    "id": cmd.id,
                    "hostname": cmd.hostname,
                    "action": cmd.action,
                    "payload": cmd.payload,
                    "status": cmd.status,
                } for cmd in commands
            ]
        except Exception as e:
            logger.error(f"Failed to get commands: {e}")
            return []
    
    def update_command_status(
        self,
        command_id: int,
        status: str,
        message: str = ""
    ) -> bool:
        """Update command status in database."""
        from web.models import db, AgentControlCommand
        from datetime import datetime
        try:
            cmd = AgentControlCommand.query.get(command_id)
            if cmd:
                cmd.status = status
                cmd.result_message = message[:500] if message else ""
                cmd.executed_at = datetime.utcnow()
                db.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update command: {e}")
            db.session.rollback()
            return False
    
    # ──────────────────────────────────────────────────────────────────────
    # DOMAIN DISCOVERY (DB-backed fallback)
    # ──────────────────────────────────────────────────────────────────────
    
    def get_devices_from_graph(self) -> List[Dict]:
        """
        Fetch devices from Microsoft Graph (Azure AD devices).
        Falls back to database if Graph call fails.
        """
        try:
            # Try Graph API first
            url = f"{self.base_url}/devices"
            params = {"$select": "id,displayName,operatingSystem,deviceId"}
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            
            if resp.status_code == 200:
                devices = resp.json().get("value", [])
                logger.info(f"✓ Got {len(devices)} devices from Graph API")
                return devices
            else:
                logger.warning(f"Graph API returned {resp.status_code}. Using DB fallback.")
        except Exception as e:
            logger.warning(f"Graph API failed: {e}. Using DB fallback.")
        
        # Fallback to database
        from web.models import Server, VM
        try:
            servers = Server.query.all()
            vms = VM.query.all()
            
            devices = []
            for s in servers:
                devices.append({
                    "id": f"server-{s.id}",
                    "displayName": s.hostname,
                    "operatingSystem": s.os,
                    "deviceId": s.id,
                    "source": "database",
                })
            
            for v in vms:
                devices.append({
                    "id": f"vm-{v.id}",
                    "displayName": v.name,
                    "operatingSystem": "Virtual Machine",
                    "deviceId": v.id,
                    "source": "database",
                })
            
            logger.info(f"✓ Got {len(devices)} devices from database")
            return devices
        except Exception as e:
            logger.error(f"Database fallback also failed: {e}")
            return []
    
    def get_users_from_graph(self) -> List[Dict]:
        """
        Fetch users from Microsoft Graph.
        Falls back to database if Graph call fails.
        """
        try:
            # Try Graph API first
            url = f"{self.base_url}/users"
            params = {
                "$select": "id,displayName,mail,jobTitle,department",
                "$top": 999
            }
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            
            if resp.status_code == 200:
                users = resp.json().get("value", [])
                logger.info(f"✓ Got {len(users)} users from Graph API")
                return users
            else:
                logger.warning(f"Graph API returned {resp.status_code}. Using DB fallback.")
        except Exception as e:
            logger.warning(f"Graph API failed: {e}. Using DB fallback.")
        
        # Fallback to database
        from web.models import db
        try:
            # Using raw SQL or ORM to get unique users
            result = db.session.execute('''
                SELECT DISTINCT login, login as mail
                FROM employee_asset_log
                WHERE login IS NOT NULL
            ''')
            
            users = [
                {
                    "id": login,
                    "displayName": login.split("@")[0].title(),
                    "mail": login,
                    "jobTitle": "Employee",
                    "department": "IT",
                    "source": "database",
                }
                for (login,) in result
            ]
            
            logger.info(f"✓ Got {len(users)} users from database")
            return users
        except Exception as e:
            logger.error(f"Database fallback also failed: {e}")
            return []


def get_graph_client(access_token: str, tenant_id: str = "") -> GraphAPIClient:
    """Factory function to create Graph API client."""
    return GraphAPIClient(access_token, tenant_id)
