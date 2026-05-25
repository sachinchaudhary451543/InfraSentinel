"""
Migration: Add Status Tracking for Azure Devices and Employees
This adds columns to track active/inactive status with timestamps
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import app, db
from sqlalchemy import text

def add_status_columns():
    """Add status tracking columns to models"""
    with app.app_context():
        conn = db.engine.connect()
        try:
            print("[MIGRATION] Adding status tracking columns...\n")
            
            # 1. Azure Device Status Tracking
            print("[1] Adding status columns to azure_device...")
            try:
                res = conn.execute(text("PRAGMA table_info('azure_device')"))
                cols = {r[1] for r in res.fetchall()}
                
                if 'is_active' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN is_active INTEGER DEFAULT 1"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_device_is_active ON azure_device(is_active)"
                    ))
                    print("    ✓ Added is_active column")
                
                if 'last_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN last_activity DATETIME"
                    ))
                    print("    ✓ Added last_activity column")
                
                if 'disabled_at' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN disabled_at DATETIME"
                    ))
                    print("    ✓ Added disabled_at column")
                
                if 'device_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN device_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_device_status ON azure_device(device_status)"
                    ))
                    print("    ✓ Added device_status column (active/inactive/retired)")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # 2. Azure User Status Tracking
            print("\n[2] Adding status columns to azure_user...")
            try:
                res = conn.execute(text("PRAGMA table_info('azure_user')"))
                cols = {r[1] for r in res.fetchall()}
                
                if 'is_active' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN is_active INTEGER DEFAULT 1"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_user_is_active ON azure_user(is_active)"
                    ))
                    print("    ✓ Added is_active column")
                
                if 'employment_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN employment_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_user_employment_status ON azure_user(employment_status)"
                    ))
                    print("    ✓ Added employment_status column (active/onleave/terminated)")
                
                if 'left_date' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN left_date DATETIME"
                    ))
                    print("    ✓ Added left_date column")
                
                if 'last_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN last_activity DATETIME"
                    ))
                    print("    ✓ Added last_activity column")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # 3. Employee Status Tracking (if not already there)
            print("\n[3] Verifying employee table status columns...")
            try:
                res = conn.execute(text("PRAGMA table_info('employee')"))
                cols = {r[1] for r in res.fetchall()}
                
                if 'employment_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE employee ADD COLUMN employment_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    print("    ✓ Added employment_status column")
                
                if 'left_date' not in cols:
                    conn.execute(text(
                        "ALTER TABLE employee ADD COLUMN left_date DATETIME"
                    ))
                    print("    ✓ Added left_date column")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # 4. Device/Server Last Activity
            print("\n[4] Adding last_activity tracking to server...")
            try:
                res = conn.execute(text("PRAGMA table_info('server')"))
                cols = {r[1] for r in res.fetchall()}
                
                if 'device_active_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE server ADD COLUMN device_active_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_server_active_status ON server(device_active_status)"
                    ))
                    print("    ✓ Added device_active_status column (active/inactive/retired)")
                
                if 'last_user_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE server ADD COLUMN last_user_activity DATETIME"
                    ))
                    print("    ✓ Added last_user_activity column")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Commit all changes
            conn.commit()
            print("\n✓ Migration completed successfully!")
            
        except Exception as e:
            print(f"\n✗ Migration failed: {e}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == '__main__':
    add_status_columns()
