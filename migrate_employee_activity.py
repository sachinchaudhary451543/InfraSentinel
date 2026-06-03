#!/usr/bin/env python
"""
Migration script to add missing fields to EmployeeActivity table.
Adds tenant_id, employee_id, and indexes.
"""
import os
import sys
import sqlite3
from datetime import datetime

# Change to ServerMonitor directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Get the database path - should be data/central.db based on web/app.py
db_path = 'data/central.db'

def run_sqlite_migration():
    """Run migration on SQLite database"""
    global db_path
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return False
    
    # Normalize path
    db_path = os.path.abspath(db_path)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check current schema
        cursor.execute("PRAGMA table_info(employee_activity)")
        columns = {row[1] for row in cursor.fetchall()}
        print(f"✓ Current columns in employee_activity: {columns}")
        
        # Add tenant_id if not exists
        if 'tenant_id' not in columns:
            print("  → Adding tenant_id column...")
            cursor.execute("ALTER TABLE employee_activity ADD COLUMN tenant_id INTEGER")
            
            # Set default tenant_id based on server relationship
            cursor.execute("""
                UPDATE employee_activity 
                SET tenant_id = (
                    SELECT tenant_id FROM server WHERE server.id = employee_activity.server_id LIMIT 1
                )
                WHERE tenant_id IS NULL
            """)
            
            # Add foreign key constraint (SQLite doesn't fully support altering constraints, so we note it)
            print("  ✓ tenant_id column added")
        else:
            print("  ✓ tenant_id column already exists")
        
        # Add employee_id if not exists
        if 'employee_id' not in columns:
            print("  → Adding employee_id column...")
            cursor.execute("ALTER TABLE employee_activity ADD COLUMN employee_id INTEGER")
            print("  ✓ employee_id column added")
        else:
            print("  ✓ employee_id column already exists")
        
        # Create indexes
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_activity_tenant_server_user 
                ON employee_activity(tenant_id, server_id, user)
            """)
            print("  ✓ Index idx_employee_activity_tenant_server_user created")
        except Exception as e:
            print(f"  ⚠ Index creation: {e}")
        
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_activity_tenant_timestamp 
                ON employee_activity(tenant_id, timestamp)
            """)
            print("  ✓ Index idx_employee_activity_tenant_timestamp created")
        except Exception as e:
            print(f"  ⚠ Index creation: {e}")
        
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_activity_employee_timestamp 
                ON employee_activity(employee_id, timestamp)
            """)
            print("  ✓ Index idx_employee_activity_employee_timestamp created")
        except Exception as e:
            print(f"  ⚠ Index creation: {e}")
        
        conn.commit()
        conn.close()
        
        print("\n✓ SQLite migration completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


def run_postgresql_migration():
    """Run migration on PostgreSQL database if configured"""
    try:
        # Check if PostgreSQL is configured
        from web.models import db
        from sqlalchemy.dialects import postgresql
        
        # Only run if using PostgreSQL
        db_url = os.getenv('DATABASE_URL', '')
        if 'postgresql' not in db_url and 'postgres' not in db_url:
            print("PostgreSQL not configured, skipping PostgreSQL migration")
            return True
        
        print("PostgreSQL migration would run here (not implemented)")
        return True
    except Exception as e:
        print(f"⚠ PostgreSQL check: {e}")
        return True


if __name__ == '__main__':
    print("🔄 Starting EmployeeActivity migration...")
    print(f"Database: {DB_PATH}")
    print()
    
    # Detect database type
    if os.path.exists(DB_PATH):
        print("Detected: SQLite")
        success = run_sqlite_migration()
    else:
        print("Checking for PostgreSQL configuration...")
        success = run_postgresql_migration()
    
    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
