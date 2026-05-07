#!/usr/bin/env python
"""
Initialize all databases for the ServerMonitor system.
Run this ONCE before starting the application.
"""

import os
import sys
import sqlite3
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def init_admin_portal_db():
    """Initialize admin portal database."""
    print("\n[1/3] Initializing Admin Portal Database...")
    
    try:
        # Add admin_portal to path
        admin_portal_path = os.path.join(os.path.dirname(__file__), 'admin_portal')
        sys.path.insert(0, admin_portal_path)
        
        # Import from init_db
        from init_db import init_database
        init_database()
        
        print("✅ Admin Portal Database initialized")
        return True
    except Exception as e:
        print(f"⚠️  Admin Portal DB - Skipping (already initialized or error): {e}")
        # Check if database exists anyway
        if os.path.exists(os.path.join(os.path.dirname(__file__), 'admin_portal', 'admin_portal.db')):
            print("   ✓ Database file exists, initialization may have been done previously")
            return True
        return False

def init_metrics_db():
    """Initialize metrics database."""
    print("\n[2/3] Initializing Metrics Database...")
    
    try:
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        db_path = os.path.join(data_dir, 'ServerMetrics.db')
        
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create metrics table
        c.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Timestamp TEXT NOT NULL,
                Hostname TEXT NOT NULL,
                CPU_Util_Percent REAL,
                RAMUtil_Percent REAL,
                SSDUtil_Percent REAL,
                Error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster queries
        c.execute('CREATE INDEX IF NOT EXISTS idx_hostname_timestamp ON metrics(Hostname, Timestamp)')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Metrics Database initialized at {db_path}")
        return True
    except Exception as e:
        print(f"❌ Metrics DB initialization failed: {e}")
        return False

def init_agents_db():
    """Initialize agents database."""
    print("\n[3/3] Initializing Central Agents Database...")
    
    try:
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        db_path = os.path.join(data_dir, 'central_agents.db')
        
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create agents table
        c.execute('''
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT NOT NULL,
                ip TEXT,
                os TEXT,
                domain TEXT,
                agent_version TEXT,
                last_seen DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Agents Database initialized at {db_path}")
        return True
    except Exception as e:
        print(f"❌ Agents DB initialization failed: {e}")
        return False

def init_web_credentials():
    """Initialize web dashboard credentials file."""
    print("\n[*] Setting up Web Dashboard Credentials...")
    
    try:
        web_dir = os.path.join(os.path.dirname(__file__), 'web')
        config_dir = os.path.join(web_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)
        
        creds_file = os.path.join(config_dir, 'credentials.json')
        
        if os.path.exists(creds_file):
            print("   Credentials file already exists, skipping...")
            return True
        
        # Default credentials
        credentials = {
            "admin": {
                "username": "admin",
                "password": "admin123"
            },
            "user": {
                "username": "user",
                "password": "user123"
            }
        }
        
        with open(creds_file, 'w') as f:
            json.dump(credentials, f, indent=2)
        
        print(f"✅ Web credentials created at {creds_file}")
        print("   Admin: admin / admin123")
        print("   User: user / user123")
        return True
    except Exception as e:
        print(f"❌ Web credentials setup failed: {e}")
        return False

def main():
    """Run all initializations."""
    print("=" * 60)
    print("ServerMonitor - Database Initialization")
    print("=" * 60)
    
    # Save current directory
    original_dir = os.getcwd()
    
    try:
        results = []
        
        # Initialize all databases
        results.append(init_metrics_db())
        results.append(init_agents_db())
        results.append(init_admin_portal_db())
        results.append(init_web_credentials())
        
        # Return to original directory
        os.chdir(original_dir)
        
        # Summary
        print("\n" + "=" * 60)
        if all(results):
            print("✅ ALL DATABASES INITIALIZED SUCCESSFULLY")
            print("\n📋 Next Steps:")
            print("   1. Start Admin Portal: python admin_portal/app.py")
            print("   2. Start Web Dashboard: python web/app.py")
            print("   3. Open http://localhost:5001 (Admin Portal)")
            print("   4. Open http://localhost:5000 (Web Dashboard)")
        else:
            print("⚠️  SOME INITIALIZATIONS FAILED - Check errors above")
        print("=" * 60)
        
        return all(results)
        
    except Exception as e:
        os.chdir(original_dir)
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
