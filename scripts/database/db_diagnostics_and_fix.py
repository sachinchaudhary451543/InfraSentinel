"""
db_diagnostics_and_fix.py - Database Schema Verification & Repair
==================================================================
Checks and fixes all database tables, indexes, and constraints
"""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE PATHS
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_DB = os.path.join(BASE_DIR, "admin_portal", "admin_portal.db")
CENTRAL_DB = os.path.join(BASE_DIR, "data", "central.db")

# Ensure directories exist
os.makedirs(os.path.dirname(ADMIN_DB), exist_ok=True)
os.makedirs(os.path.dirname(CENTRAL_DB), exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_PORTAL_SCHEMA = """
-- Tenant Management
CREATE TABLE IF NOT EXISTS tenant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Server/Agent Registration
CREATE TABLE IF NOT EXISTS server (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    name TEXT,
    hostname TEXT UNIQUE,
    ip TEXT,
    os_info TEXT,
    status TEXT DEFAULT 'offline',
    agent_installed BOOLEAN DEFAULT 0,
    agent_version TEXT,
    monitoring_active BOOLEAN DEFAULT 0,
    is_hyperv_host BOOLEAN DEFAULT 0,
    server_type TEXT DEFAULT 'Endpoint',
    api_key TEXT UNIQUE,
    last_seen DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    screenshot_enabled BOOLEAN DEFAULT 0,
    screenshot_interval_minutes INTEGER DEFAULT 10,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- System Metrics (Core Storage)
CREATE TABLE IF NOT EXISTS metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    timestamp DATETIME NOT NULL,
    
    -- CPU
    virtual_cores INTEGER,
    cpu_util_percent REAL,
    
    -- RAM
    total_ram_gb REAL,
    available_ram_gb REAL,
    used_ram_gb REAL,
    ram_util_percent REAL,
    
    -- Disk
    total_ssd_gb REAL,
    available_ssd_gb REAL,
    used_ssd_gb REAL,
    ssd_util_percent REAL,
    
    -- Drive Details
    drive_letters_checked TEXT,
    drives_details TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE
);

-- Virtual Machines (Hyper-V)
CREATE TABLE IF NOT EXISTS vm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    server_id INTEGER,
    vm_name TEXT,
    state TEXT,
    cpu_usage REAL,
    memory_assigned REAL,
    uptime TEXT,
    path TEXT,
    host_ip TEXT,
    host_os TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Agent API Keys
CREATE TABLE IF NOT EXISTS agent_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    tenant_id INTEGER,
    key_name TEXT,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Screenshots
CREATE TABLE IF NOT EXISTS screenshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    image_data BLOB,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    user TEXT,
    action TEXT,
    resource TEXT,
    details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Remote Commands
CREATE TABLE IF NOT EXISTS remote_command (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER,
    command TEXT,
    parameters TEXT,
    status TEXT DEFAULT 'pending',
    output TEXT,
    executed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE
);

-- Deployment Jobs
CREATE TABLE IF NOT EXISTS deployment_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    server_id INTEGER,
    job_type TEXT,
    status TEXT DEFAULT 'pending',
    agent_key TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Employee Asset Logs (For tracking who used which device)
CREATE TABLE IF NOT EXISTS employee_asset_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    server_id INTEGER,
    employee_id TEXT,
    employee_email TEXT,
    hostname TEXT,
    ip_address TEXT,
    os_info TEXT,
    device_type TEXT,
    login_timestamp DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Alerts
CREATE TABLE IF NOT EXISTS alert (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    server_id INTEGER,
    alert_type TEXT,
    severity TEXT,
    message TEXT,
    is_resolved BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    FOREIGN KEY(server_id) REFERENCES server(id) ON DELETE CASCADE,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_metric_server_timestamp ON metric(server_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_metric_timestamp ON metric(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_server_tenant_hostname ON server(tenant_id, hostname);
CREATE INDEX IF NOT EXISTS idx_server_api_key ON server(api_key);
CREATE INDEX IF NOT EXISTS idx_vm_server ON vm(server_id);
CREATE INDEX IF NOT EXISTS idx_screenshot_server_timestamp ON screenshot(server_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_timestamp ON audit_log(tenant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_employee_asset_log_tenant_email ON employee_asset_log(tenant_id, employee_email);
CREATE INDEX IF NOT EXISTS idx_remote_command_server_status ON remote_command(server_id, status);
CREATE INDEX IF NOT EXISTS idx_alert_server_tenant ON alert(server_id, tenant_id, created_at DESC);
"""


class DatabaseDiagnostics:
    """Diagnostic and repair utilities for databases"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.issues = []
        self.fixes_applied = []
    
    def connect(self):
        """Connect to database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def check_tables(self) -> bool:
        """Check if all required tables exist"""
        conn = self.connect()
        c = conn.cursor()
        
        required_tables = [
            'server', 'metric', 'vm', 'agent_key', 'screenshot',
            'audit_log', 'remote_command', 'deployment_job'
        ]
        
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in c.fetchall()]
        
        missing_tables = [t for t in required_tables if t not in existing_tables]
        
        if missing_tables:
            self.issues.append(f"Missing tables: {', '.join(missing_tables)}")
        
        conn.close()
        return len(missing_tables) == 0
    
    def check_data_integrity(self) -> int:
        """Check for orphaned records and foreign key violations"""
        conn = self.connect()
        c = conn.cursor()
        
        violations = 0
        
        # Check metrics with non-existent servers
        c.execute("""
            SELECT COUNT(*) FROM metric 
            WHERE server_id NOT IN (SELECT id FROM server)
        """)
        orphaned_metrics = c.fetchone()[0]
        if orphaned_metrics > 0:
            self.issues.append(f"Found {orphaned_metrics} orphaned metric records")
            violations += orphaned_metrics
        
        # Check VMs with non-existent servers
        c.execute("""
            SELECT COUNT(*) FROM vm 
            WHERE server_id NOT IN (SELECT id FROM server)
        """)
        orphaned_vms = c.fetchone()[0]
        if orphaned_vms > 0:
            self.issues.append(f"Found {orphaned_vms} orphaned VM records")
            violations += orphaned_vms
        
        conn.close()
        return violations
    
    def check_data_volume(self) -> dict:
        """Check amount of data stored"""
        conn = self.connect()
        c = conn.cursor()
        
        stats = {}
        
        tables = ['server', 'metric', 'vm', 'screenshot', 'audit_log']
        for table in tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                stats[table] = count
            except:
                stats[table] = 0
        
        conn.close()
        return stats
    
    def initialize_schema(self) -> bool:
        """Create or update database schema"""
        try:
            conn = self.connect()
            c = conn.cursor()
            
            # Execute schema creation
            for statement in ADMIN_PORTAL_SCHEMA.split(';'):
                if statement.strip():
                    c.execute(statement)
            
            conn.commit()
            self.fixes_applied.append("Schema initialized/updated")
            logger.info(f"✅ Database schema initialized: {self.db_path}")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            return False
    
    def clean_orphaned_records(self) -> int:
        """Remove orphaned records"""
        try:
            conn = self.connect()
            c = conn.cursor()
            
            deleted_count = 0
            
            # Delete orphaned metrics
            c.execute("""
                DELETE FROM metric 
                WHERE server_id NOT IN (SELECT id FROM server)
            """)
            deleted_count += c.rowcount
            
            # Delete orphaned VMs
            c.execute("""
                DELETE FROM vm 
                WHERE server_id NOT IN (SELECT id FROM server)
            """)
            deleted_count += c.rowcount
            
            conn.commit()
            
            if deleted_count > 0:
                self.fixes_applied.append(f"Deleted {deleted_count} orphaned records")
                logger.info(f"✅ Cleaned {deleted_count} orphaned records")
            
            conn.close()
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to clean orphaned records: {e}")
            return 0
    
    def verify_constraints(self) -> bool:
        """Verify database integrity"""
        try:
            conn = self.connect()
            c = conn.cursor()
            c.execute("PRAGMA integrity_check")
            result = c.fetchone()
            conn.close()
            
            if result and result[0] == 'ok':
                logger.info("✅ Database integrity check passed")
                return True
            else:
                msg = result[0] if result else "Unknown error"
                self.issues.append(f"Integrity check failed: {msg}")
                logger.error(f"Database integrity issue: {msg}")
                return False
        except Exception as e:
            logger.error(f"Failed to run integrity check: {e}")
            return False
    
    def run_full_diagnostics(self) -> dict:
        """Run complete database diagnostics"""
        logger.info(f"\n🔍 Running diagnostics on {self.db_path}...")
        
        results = {
            "db_path": self.db_path,
            "exists": os.path.exists(self.db_path),
            "tables_ok": self.check_tables(),
            "integrity_ok": self.verify_constraints(),
            "orphaned_records": self.check_data_integrity(),
            "data_volume": self.check_data_volume(),
            "issues": self.issues,
            "fixes_applied": self.fixes_applied
        }
        
        return results
    
    def run_full_repair(self) -> dict:
        """Run complete database repair"""
        logger.info(f"\n🔧 Running repairs on {self.db_path}...")
        
        # Initialize schema
        self.initialize_schema()
        
        # Clean orphaned records
        self.clean_orphaned_records()
        
        # Run diagnostics
        results = self.run_full_diagnostics()
        
        return results
    
    def print_report(self, results: dict):
        """Print diagnostics report"""
        print("\n" + "="*70)
        print("DATABASE DIAGNOSTICS REPORT")
        print("="*70)
        print(f"Database: {results['db_path']}")
        print(f"Exists: {'✅ Yes' if results['exists'] else '❌ No'}")
        print(f"Tables OK: {'✅ Yes' if results['tables_ok'] else '❌ No'}")
        print(f"Integrity OK: {'✅ Yes' if results['integrity_ok'] else '❌ No'}")
        print(f"Orphaned Records: {results['orphaned_records']}")
        
        print("\nData Volume:")
        for table, count in results['data_volume'].items():
            print(f"  {table:20} → {count:6} records")
        
        if results['issues']:
            print("\n⚠️ Issues Found:")
            for issue in results['issues']:
                print(f"  • {issue}")
        
        if results['fixes_applied']:
            print("\n✅ Fixes Applied:")
            for fix in results['fixes_applied']:
                print(f"  • {fix}")
        
        print("="*70 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Run diagnostics and repairs on all databases"""
    databases = [
        ("Admin Portal", ADMIN_DB),
        ("Central DB", CENTRAL_DB),
    ]
    
    all_results = {}
    
    for db_name, db_path in databases:
        logger.info(f"\n{'='*70}")
        logger.info(f"Processing: {db_name}")
        logger.info('='*70)
        
        diag = DatabaseDiagnostics(db_path)
        
        # Run repair
        results = diag.run_full_repair()
        all_results[db_name] = results
        
        # Print report
        diag.print_report(results)
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    for db_name, results in all_results.items():
        status = "✅ HEALTHY" if (results['tables_ok'] and results['integrity_ok']) else "⚠️ NEEDS ATTENTION"
        print(f"{db_name:20} {status}")
    
    print("="*70 + "\n")
    
    logger.info("✅ Database diagnostics and repairs completed!")


if __name__ == "__main__":
    main()
