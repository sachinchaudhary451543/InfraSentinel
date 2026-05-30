"""
Migration: Add Status Tracking for Azure Devices and Employees
This adds columns to track active/inactive status with timestamps
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import app, db
from sqlalchemy import text, inspect

def add_status_columns():
    """Add status tracking columns to models"""
    with app.app_context():
        print("[MIGRATION] Adding status tracking columns...\n")
        
        inspector = inspect(db.engine)
        
        try:
            # We use transaction block to commit changes
            with db.engine.begin() as conn:
                
                # 1. Azure Device Status Tracking
                print("[1] Verifying columns for azure_device...")
                cols = {col['name'] for col in inspector.get_columns('azure_device')}
                
                if 'is_active' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN is_active INTEGER DEFAULT 1"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_device_is_active ON azure_device(is_active)"
                    ))
                    print("    -> Added is_active column")
                
                if 'last_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN last_activity TIMESTAMP"
                    ))
                    print("    -> Added last_activity column")
                
                if 'disabled_at' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN disabled_at TIMESTAMP"
                    ))
                    print("    -> Added disabled_at column")
                
                if 'device_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_device ADD COLUMN device_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_device_status ON azure_device(device_status)"
                    ))
                    print("    -> Added device_status column (active/inactive/retired)")
                
                # 2. Azure User Status Tracking
                print("\n[2] Verifying columns for azure_user...")
                cols = {col['name'] for col in inspector.get_columns('azure_user')}
                
                if 'is_active' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN is_active INTEGER DEFAULT 1"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_user_is_active ON azure_user(is_active)"
                    ))
                    print("    -> Added is_active column")
                
                if 'employment_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN employment_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_azure_user_employment_status ON azure_user(employment_status)"
                    ))
                    print("    -> Added employment_status column (active/onleave/terminated)")
                
                if 'left_date' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN left_date TIMESTAMP"
                    ))
                    print("    -> Added left_date column")
                
                if 'last_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE azure_user ADD COLUMN last_activity TIMESTAMP"
                    ))
                    print("    -> Added last_activity column")
                
                # 3. Employee Status Tracking (if not already there)
                print("\n[3] Verifying employee table status columns...")
                cols = {col['name'] for col in inspector.get_columns('employee')}
                
                if 'employment_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE employee ADD COLUMN employment_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    print("    -> Added employment_status column")
                
                if 'left_date' not in cols:
                    conn.execute(text(
                        "ALTER TABLE employee ADD COLUMN left_date TIMESTAMP"
                    ))
                    print("    -> Added left_date column")
                
                # 4. Device/Server Last Activity
                print("\n[4] Adding last_activity tracking to server...")
                cols = {col['name'] for col in inspector.get_columns('server')}
                
                if 'device_active_status' not in cols:
                    conn.execute(text(
                        "ALTER TABLE server ADD COLUMN device_active_status VARCHAR(50) DEFAULT 'active'"
                    ))
                    conn.execute(text(
                        "CREATE INDEX idx_server_active_status ON server(device_active_status)"
                    ))
                    print("    -> Added device_active_status column (active/inactive/retired)")
                
                if 'last_user_activity' not in cols:
                    conn.execute(text(
                        "ALTER TABLE server ADD COLUMN last_user_activity TIMESTAMP"
                    ))
                    print("    -> Added last_user_activity column")
                
            print("\nMigration completed successfully!")
            
        except Exception as e:
            print(f"\nMigration failed: {e}")
            raise e

if __name__ == '__main__':
    add_status_columns()
