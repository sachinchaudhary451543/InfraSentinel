"""
Migration: Add License and Device-User Mapping Models
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import app, db
from sqlalchemy import text

def add_license_tables():
    """Add license and mapping tables"""
    with app.app_context():
        conn = db.engine.connect()
        try:
            print("[MIGRATION] Adding license and mapping tables...\n")
            
            # 1. Azure License Table
            print("[1] Creating azure_license table...")
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS azure_license (
                        id INTEGER PRIMARY KEY,
                        tenant_id INTEGER NOT NULL,
                        sku_id VARCHAR(255) NOT NULL,
                        sku_name VARCHAR(255),
                        product_name VARCHAR(255),
                        total_licenses INTEGER DEFAULT 0,
                        assigned_licenses INTEGER DEFAULT 0,
                        available_licenses INTEGER DEFAULT 0,
                        service_plans_json TEXT,
                        last_synced DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(tenant_id) REFERENCES tenant(id),
                        UNIQUE(tenant_id, sku_id)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_azure_license_tenant ON azure_license(tenant_id)"))
                print("    ✓ Created azure_license table")
            except Exception as e:
                print(f"    ! {e}")
            
            # 2. Azure License Assignment Table
            print("[2] Creating azure_license_assignment table...")
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS azure_license_assignment (
                        id INTEGER PRIMARY KEY,
                        tenant_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        license_id INTEGER NOT NULL,
                        assigned_at DATETIME,
                        disabled_plans_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(tenant_id) REFERENCES tenant(id),
                        FOREIGN KEY(user_id) REFERENCES azure_user(id),
                        FOREIGN KEY(license_id) REFERENCES azure_license(id)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_license_assignment_user ON azure_license_assignment(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_license_assignment_license ON azure_license_assignment(license_id)"))
                print("    ✓ Created azure_license_assignment table")
            except Exception as e:
                print(f"    ! {e}")
            
            # 3. Verify AzureDeviceOwner table
            print("[3] Verifying azure_device_owner table...")
            try:
                res = conn.execute(text("PRAGMA table_info('azure_device_owner')"))
                cols = {r[1] for r in res.fetchall()}
                
                if len(cols) == 0:
                    # Table doesn't exist, create it
                    conn.execute(text("""
                        CREATE TABLE azure_device_owner (
                            id INTEGER PRIMARY KEY,
                            tenant_id INTEGER NOT NULL,
                            device_id INTEGER NOT NULL,
                            user_id INTEGER NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(tenant_id) REFERENCES tenant(id),
                            FOREIGN KEY(device_id) REFERENCES azure_device(id),
                            FOREIGN KEY(user_id) REFERENCES azure_user(id)
                        )
                    """))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_owner_device ON azure_device_owner(device_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_device_owner_user ON azure_device_owner(user_id)"))
                    print("    ✓ Created azure_device_owner table")
                else:
                    print("    ✓ Table already exists")
            except Exception as e:
                print(f"    ! {e}")
            
            # 4. Add sync columns to tracking tables
            print("[4] Adding sync tracking columns...")
            try:
                res = conn.execute(text("PRAGMA table_info('azure_device')"))
                cols = {r[1] for r in res.fetchall()}
                
                if 'last_activity' not in cols:
                    conn.execute(text("ALTER TABLE azure_device ADD COLUMN last_activity DATETIME"))
                    print("    ✓ Added last_activity to azure_device")
                
                if 'device_status' not in cols:
                    conn.execute(text("ALTER TABLE azure_device ADD COLUMN device_status VARCHAR(50) DEFAULT 'active'"))
                    print("    ✓ Added device_status to azure_device")
                
            except Exception as e:
                print(f"    ! {e}")
            
            conn.commit()
            print("\n✓ Migration completed successfully!")
            
        except Exception as e:
            print(f"\n✗ Migration failed: {e}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == '__main__':
    add_license_tables()
