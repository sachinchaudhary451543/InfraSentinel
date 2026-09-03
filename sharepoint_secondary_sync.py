"""
sharepoint_secondary_sync.py - SharePoint as Secondary Database
=================================================================
Syncs all metrics, servers, and VMs to SharePoint Lists for external dashboards
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SHAREPOINT CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

class SharePointSyncConfig:
    """Configuration for SharePoint secondary database"""
    
    # SharePoint Site
    SITE_URL = os.environ.get("SHAREPOINT_SITE_URL", "")
    
    # List names (will be created if they don't exist)
    LISTS = {
        "ServerMetricsSummary": "Latest server metrics snapshot",
        "ServerMetricsHistory": "Historical metrics for trending",
        "ServerInventory": "Server inventory and details",
        "ServerAlerts": "Alerts and anomalies",
        "AgentStatus": "Agent registration and health",
    }
    
    # Local database
    LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "admin_portal", "admin_portal.db")


class SharePointSecondarySync:
    """Manages syncing data to SharePoint as secondary database"""
    
    def __init__(self, site_url: str, db_path: str, auth_token: str | None = None):
        self.site_url = site_url
        self.db_path = db_path
        self.auth_token = auth_token or self._get_token() or ""
        self.headers = self._build_headers()
        self.last_sync = {}
        
    def _get_token(self) -> str:
        """Get OAuth token for SharePoint (using stored credentials)"""
        try:
            from auth.msal_auth import get_sp_access_token  # type: ignore
            return get_sp_access_token()
        except Exception as e:
            logger.error(f"Failed to get SharePoint token: {e}")
            return ""
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with auth"""
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        return headers
    
    def _get_list_id(self, list_name: str) -> str:
        """Get list ID by name from SharePoint"""
        try:
            url = f"{self.site_url}/_api/web/lists/getByTitle('{list_name}')"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()['Id']
        except Exception as e:
            logger.error(f"Failed to get list ID for {list_name}: {e}")
        return ""
    
    def _create_list_item(self, list_name: str, data: Dict[str, Any]) -> bool:
        """Create or update item in SharePoint list"""
        try:
            list_id = self._get_list_id(list_name)
            if not list_id:
                logger.error(f"List {list_name} not found")
                return False
            
            url = f"{self.site_url}/_api/web/lists('{list_id}')/items"
            
            # Convert data to SharePoint format
            payload = self._convert_to_sharepoint_fields(data)
            
            resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if resp.status_code in [201, 204]:
                logger.info(f"✅ Item added to {list_name}")
                return True
            else:
                logger.error(f"Failed to create item in {list_name}: {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error creating list item in {list_name}: {e}")
            return False
    
    def _convert_to_sharepoint_fields(self, data: Dict) -> Dict[str, Any]:
        """Convert Python dict to SharePoint field format"""
        fields = {}
        for key, value in data.items():
            # Replace underscores with field names SharePoint expects
            sp_key = key.replace('_', '')
            
            # Type conversion
            if isinstance(value, bool):
                fields[sp_key] = value
            elif isinstance(value, (int, float)):
                fields[sp_key] = value
            elif isinstance(value, dict):
                fields[sp_key] = json.dumps(value)
            elif isinstance(value, list):
                fields[sp_key] = ';'.join(str(x) for x in value)
            else:
                fields[sp_key] = str(value)
        
        return {"fields": fields}
    
    def sync_latest_metrics(self):
        """Sync latest metrics snapshot to ServerMetricsSummary list"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get latest metrics for each server
            c.execute("""
                SELECT 
                    s.id, s.name, s.hostname, s.ip, s.status,
                    m.id, m.timestamp, m.cpu_util_percent, m.ram_util_percent, 
                    m.ssd_util_percent, m.total_ram_gb, m.available_ram_gb,
                    m.total_ssd_gb, m.available_ssd_gb
                FROM server s
                LEFT JOIN (
                    SELECT * FROM metric
                    WHERE id IN (
                        SELECT MAX(id) FROM metric GROUP BY server_id
                    )
                ) m ON s.id = m.server_id
                ORDER BY s.name
            """)
            
            metrics_count = 0
            for row in c.fetchall():
                (server_id, server_name, hostname, ip, status, 
                 metric_id, timestamp, cpu, ram, disk, 
                 total_ram, avail_ram, total_disk, avail_disk) = row
                
                # Skip if no metrics yet
                if not metric_id:
                    continue
                
                data = {
                    "Title": hostname or server_name or f"Server-{server_id}",
                    "ServerName": hostname,
                    "Timestamp": timestamp,
                    "AvgCPU": cpu or 0,
                    "AvgDisk": disk or 0,
                    "AvgRAM": ram or 0,
                    "TotalRAM": total_ram or 0,
                    "AvailableRAM": avail_ram or 0,
                    "TotalSSD": total_disk or 0,
                    "AvailableSSD": avail_disk or 0,
                    "Status": status,
                    "ServerIP": ip,
                }
                
                if self._create_list_item("ServerMetricsSummary", data):
                    metrics_count += 1
                    
            logger.info(f"✅ Synced {metrics_count} server metrics to SharePoint")
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error syncing latest metrics: {e}")
            return False
    
    def sync_metrics_history(self, days_back: int = 7):
        """Sync historical metrics for trending"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get metrics from last N days
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_back)
            
            c.execute("""
                SELECT 
                    s.name, s.hostname, m.timestamp, m.cpu_util_percent,
                    m.ram_util_percent, m.ssd_util_percent
                FROM metric m
                JOIN server s ON m.server_id = s.id
                WHERE m.timestamp > ?
                ORDER BY m.timestamp DESC
                LIMIT 5000
            """, (cutoff_time.isoformat(),))
            
            history_count = 0
            for _, hostname, timestamp, cpu, ram, disk in c.fetchall():
                data = {
                    "Title": f"{hostname}-{timestamp}",
                    "ServerName": hostname,
                    "Timestamp": timestamp,
                    "CPU": cpu or 0,
                    "RAM": ram or 0,
                    "Disk": disk or 0,
                }
                
                if self._create_list_item("ServerMetricsHistory", data):
                    history_count += 1
            
            logger.info(f"✅ Synced {history_count} historical metrics to SharePoint")
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error syncing metrics history: {e}")
            return False
    
    def sync_server_inventory(self):
        """Sync server inventory and details"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute("""
                SELECT id, name, hostname, ip, status, os_info, agent_version, last_seen
                FROM server
                ORDER BY name
            """)
            
            inventory_count = 0
            for row in c.fetchall():
                (_, name, hostname, ip, status, 
                 os_info, agent_version, last_seen) = row
                
                data = {
                    "Title": hostname or name,
                    "ServerName": hostname,
                    "IPAddress": ip,
                    "Status": status,
                    "OS": os_info,
                    "AgentVersion": agent_version,
                    "LastSeen": last_seen,
                }
                
                if self._create_list_item("ServerInventory", data):
                    inventory_count += 1
            
            logger.info(f"✅ Synced {inventory_count} servers to SharePoint inventory")
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error syncing server inventory: {e}")
            return False
    
    def sync_agent_status(self):
        """Sync agent registration and health status"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Check agent health (online if seen in last 30 mins)
            c.execute("""
                SELECT id, hostname, ip, agent_version, last_seen, 
                       CASE 
                           WHEN datetime(last_seen) > datetime('now', '-30 minutes') 
                           THEN 'Online'
                           ELSE 'Offline'
                       END as agent_status
                FROM server
                WHERE agent_installed = 1
                ORDER BY hostname
            """)
            
            agent_count = 0
            for row in c.fetchall():
                (_, hostname, ip, version, last_seen, agent_status) = row
                
                data = {
                    "Title": hostname,
                    "ServerName": hostname,
                    "IPAddress": ip,
                    "AgentVersion": version,
                    "Status": agent_status,
                    "LastHeartbeat": last_seen,
                }
                
                if self._create_list_item("AgentStatus", data):
                    agent_count += 1
            
            logger.info(f"✅ Synced {agent_count} agent status entries to SharePoint")
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error syncing agent status: {e}")
            return False
    
    def full_sync(self):
        """Execute full sync of all data"""
        logger.info("🔄 Starting full SharePoint sync...")
        
        results = {
            "metrics": self.sync_latest_metrics(),
            "history": self.sync_metrics_history(),
            "inventory": self.sync_server_inventory(),
            "agents": self.sync_agent_status(),
        }
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"✅ SharePoint sync completed: {success_count}/{len(results)} successful")
        
        return all(results.values())


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED SYNC TASK (for integration with Flask scheduler)
# ─────────────────────────────────────────────────────────────────────────────

def schedule_sharepoint_sync():
    """Called periodically (every hour) to sync to SharePoint"""
    try:
        config = SharePointSyncConfig()
        sync = SharePointSecondarySync(
            site_url=config.SITE_URL,
            db_path=config.LOCAL_DB_PATH
        )
        return sync.full_sync()
    except Exception as e:
        logger.error(f"Scheduled sync failed: {e}")
        return False


if __name__ == "__main__":
    # Test/manual sync
    config = SharePointSyncConfig()
    sync = SharePointSecondarySync(
        site_url=config.SITE_URL,
        db_path=config.LOCAL_DB_PATH
    )
    sync.full_sync()
