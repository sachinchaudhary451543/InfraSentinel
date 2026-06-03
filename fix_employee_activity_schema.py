#!/usr/bin/env python
"""Fix EmployeeActivity table schema to add tenant_id and employee_id"""
import os
import sqlite3

# Get database path
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, 'data', 'central.db')

print(f"Database path: {db_path}")
if not os.path.exists(db_path):
    print(f"ERROR: Database not found at {db_path}")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current schema
    cursor.execute("PRAGMA table_info(employee_activity)")
    columns = {row[1] for row in cursor.fetchall()}
    print(f"Current columns: {sorted(columns)}")
    
    # Add tenant_id if missing
    if 'tenant_id' not in columns:
        print("Adding tenant_id column...")
        cursor.execute("ALTER TABLE employee_activity ADD COLUMN tenant_id INTEGER")
        cursor.execute("""
            UPDATE employee_activity 
            SET tenant_id = (SELECT tenant_id FROM server WHERE server.id = employee_activity.server_id LIMIT 1)
            WHERE tenant_id IS NULL
        """)
        print("✓ tenant_id added")
    else:
        print("✓ tenant_id already exists")
    
    # Add employee_id if missing
    if 'employee_id' not in columns:
        print("Adding employee_id column...")
        cursor.execute("ALTER TABLE employee_activity ADD COLUMN employee_id INTEGER")
        print("✓ employee_id added")
    else:
        print("✓ employee_id already exists")
    
    # Create indexes
    index_commands = [
        ("idx_employee_activity_tenant_server_user", 
         "CREATE INDEX IF NOT EXISTS idx_employee_activity_tenant_server_user ON employee_activity(tenant_id, server_id, user)"),
        ("idx_employee_activity_tenant_timestamp",
         "CREATE INDEX IF NOT EXISTS idx_employee_activity_tenant_timestamp ON employee_activity(tenant_id, timestamp)"),
        ("idx_employee_activity_employee_timestamp",
         "CREATE INDEX IF NOT EXISTS idx_employee_activity_employee_timestamp ON employee_activity(employee_id, timestamp)")
    ]
    
    for idx_name, cmd in index_commands:
        try:
            cursor.execute(cmd)
            print(f"✓ Index {idx_name} created")
        except Exception as e:
            print(f"  (Note: {e})")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Schema migration completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
