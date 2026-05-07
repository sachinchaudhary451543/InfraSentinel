"""
ISV-Grade System Management Module
- Bulk system operations
- Health monitoring and alerts
- Deployment tracking
- Licensing and metering
"""
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from enum import Enum

logging.basicConfig(level=logging.INFO, format='[SYSTEM_MGMT] %(asctime)s %(levelname)s: %(message)s')

# Database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_DB = os.path.join(BASE_DIR, "admin_portal", "admin_portal.db")

class SystemStatus(Enum):
    """System health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"

class SystemManager:
    """ISV-grade system management"""
    
    def __init__(self, db_path=ADMIN_DB):
        self.db_path = db_path
    
    def get_system_health(self, server_id):
        """Get system health status and metrics"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Get latest metrics
        c.execute("""
            SELECT hostname, last_seen, os_info
            FROM server
            WHERE id = ?
        """, (server_id,))
        
        result = c.fetchone()
        if not result:
            conn.close()
            return None
        
        hostname, last_seen, os_info = result
        
        # Check if agent is responding (last seen within 30 mins)
        if last_seen:
            last_seen_time = datetime.fromisoformat(last_seen)
            if datetime.utcnow() - last_seen_time > timedelta(minutes=30):
                status = SystemStatus.OFFLINE.value
            else:
                status = SystemStatus.HEALTHY.value
        else:
            status = SystemStatus.UNKNOWN.value
        
        health = {
            "server_id": server_id,
            "hostname": hostname,
            "status": status,
            "last_seen": last_seen,
            "os": os_info
        }
        
        conn.close()
        return health
    
    def bulk_operation(self, tenant_id, operation, server_ids=None):
        """
        Execute bulk operation on systems
        Operations: enable, disable, update_agent, deploy_agent, delete
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # FIX #2: Validate server_ids are integers (SQL injection prevention)
        if server_ids:
            try:
                validated_ids = [int(id) for id in server_ids]
            except (ValueError, TypeError):
                logging.error(f"Invalid server_ids format: {server_ids}")
                return [{"status": "error", "message": "Invalid server ID format"}]
        
        # Get target servers
        if server_ids:
            placeholders = ','.join('?' * len(validated_ids))
            query = f"SELECT id, hostname FROM server WHERE tenant_id = ? AND id IN ({placeholders})"
            c.execute(query, [tenant_id] + validated_ids)
        else:
            c.execute("SELECT id, hostname FROM server WHERE tenant_id = ?", (tenant_id,))
        
        servers = c.fetchall()
        results = []
        
        for server_id, hostname in servers:
            try:
                if operation == "enable":
                    # Create enable job
                    c.execute("""
                        INSERT INTO deployment_job (tenant_id, server_id, job_type, status)
                        VALUES (?, ?, 'enable', 'pending')
                    """, (tenant_id, server_id))
                    results.append({"server_id": server_id, "hostname": hostname, "result": "scheduled"})
                
                elif operation == "disable":
                    c.execute("""
                        INSERT INTO deployment_job (tenant_id, server_id, job_type, status)
                        VALUES (?, ?, 'disable', 'pending')
                    """, (tenant_id, server_id))
                    results.append({"server_id": server_id, "hostname": hostname, "result": "scheduled"})
                
                elif operation == "update_agent":
                    c.execute("""
                        INSERT INTO deployment_job (tenant_id, server_id, job_type, status)
                        VALUES (?, ?, 'update', 'pending')
                    """, (tenant_id, server_id))
                    results.append({"server_id": server_id, "hostname": hostname, "result": "scheduled"})
                
                elif operation == "deploy_agent":
                    # Get or create agent key
                    c.execute("""
                        SELECT key FROM agent_key 
                        WHERE tenant_id = ? AND is_active = 1 
                        LIMIT 1
                    """, (tenant_id,))
                    key_row = c.fetchone()
                    key = key_row[0] if key_row else None
                    
                    c.execute("""
                        INSERT INTO deployment_job (tenant_id, server_id, agent_key, job_type, status)
                        VALUES (?, ?, ?, 'deploy', 'pending')
                    """, (tenant_id, server_id, key))
                    results.append({"server_id": server_id, "hostname": hostname, "result": "deployment_scheduled"})
                
                elif operation == "delete":
                    # Mark as deleted but keep history
                    c.execute("""
                        UPDATE server SET deleted_at = datetime('now')
                        WHERE id = ?
                    """, (server_id,))
                    results.append({"server_id": server_id, "hostname": hostname, "result": "deleted"})
            
            except Exception as e:
                logging.error(f"Error in {operation} for {hostname}: {e}")
                results.append({"server_id": server_id, "hostname": hostname, "result": f"error: {str(e)}"})
        
        conn.commit()
        conn.close()
        
        return {
            "operation": operation,
            "total": len(servers),
            "results": results
        }
    
    def get_deployment_jobs(self, tenant_id, status=None):
        """Get deployment jobs for tenant"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if status:
            c.execute("""
                SELECT dj.id, s.hostname, dj.job_type, dj.status, dj.created_at, dj.completed_at
                FROM deployment_job dj
                JOIN server s ON dj.server_id = s.id
                WHERE dj.tenant_id = ? AND dj.status = ?
                ORDER BY dj.created_at DESC
                LIMIT 100
            """, (tenant_id, status))
        else:
            c.execute("""
                SELECT dj.id, s.hostname, dj.job_type, dj.status, dj.created_at, dj.completed_at
                FROM deployment_job dj
                JOIN server s ON dj.server_id = s.id
                WHERE dj.tenant_id = ?
                ORDER BY dj.created_at DESC
                LIMIT 100
            """, (tenant_id,))
        
        jobs = [{
            "id": row[0],
            "hostname": row[1],
            "job_type": row[2],
            "status": row[3],
            "created_at": row[4],
            "completed_at": row[5]
        } for row in c.fetchall()]
        
        conn.close()
        return jobs
    
    def get_tenant_metrics(self, tenant_id):
        """Get aggregated metrics for entire tenant"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            SELECT 
                COUNT(*) as total_systems,
                SUM(CASE WHEN last_seen IS NULL OR 
                    datetime(last_seen) < datetime('now', '-30 minutes') 
                    THEN 1 ELSE 0 END) as offline_systems,
                SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END) as active_systems
            FROM server
            WHERE tenant_id = ?
        """, (tenant_id,))
        
        row = c.fetchone()
        
        # Get agent count
        c.execute("""
            SELECT COUNT(*) FROM agent_key WHERE tenant_id = ? AND is_active = 1
        """, (tenant_id,))
        
        agent_count = c.fetchone()[0]
        
        metrics = {
            "total_systems": row[0] or 0,
            "offline_systems": row[1] or 0,
            "active_systems": row[2] or 0,
            "active_agents": agent_count,
            "health_score": 100 - (((row[1] or 0) / (row[0] or 1)) * 100)
        }
        
        conn.close()
        return metrics
    
    def create_alert(self, server_id, alert_type, severity="warning", message=None):
        """Create system health alert"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute("""
                INSERT INTO system_alert (server_id, alert_type, severity, message)
                VALUES (?, ?, ?, ?)
            """, (server_id, alert_type, severity, message))
            
            conn.commit()
            logging.info(f"Alert created: {alert_type} for server {server_id}")
            return True
        except Exception as e:
            logging.error(f"Error creating alert: {e}")
            return False
        finally:
            conn.close()
    
    def export_system_report(self, tenant_id, format="json"):
        """Export system inventory and status report"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            SELECT 
                id, hostname, ip, os_info, discovered_at, deleted_at
            FROM server
            WHERE tenant_id = ?
            ORDER BY hostname
        """, (tenant_id,))
        
        systems = [{
            "id": row[0],
            "hostname": row[1],
            "ip": row[2],
            "os": row[3],
            "discovered_at": row[4],
            "deleted": row[5] is not None
        } for row in c.fetchall()]
        
        report = {
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "total_systems": len(systems),
            "systems": systems,
            "metrics": self.get_tenant_metrics(tenant_id)
        }
        
        conn.close()
        
        if format == "json":
            return json.dumps(report, indent=2)
        elif format == "csv":
            output = "Hostname,IP,OS,Status\n"
            for sys in systems:
                output += f"{sys['hostname']},{sys['ip']},{sys['os']},{'deleted' if sys['deleted'] else 'active'}\n"
            return output
        
        return report

if __name__ == "__main__":
    mgr = SystemManager()
    
    # Example: Get tenant metrics
    metrics = mgr.get_tenant_metrics(tenant_id=1)
    print(f"Tenant Metrics: {metrics}")
    
    # Example: Bulk operation
    result = mgr.bulk_operation(tenant_id=1, operation="enable")
    print(f"Bulk Enable Result: {result}")
