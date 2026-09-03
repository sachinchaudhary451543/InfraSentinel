#!/usr/bin/env python
"""
Migration script to add branding column to web app Tenant table
"""
import os
import sys
import json
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Database path
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DATA_DIR, 'central.db')

def get_default_branding():
    """Get default branding JSON"""
    return json.dumps({
        "company_name": "ServerMonitor",
        "logo_url": None,
        "primary_color": "#2563eb",
        "secondary_color": "#1e40af",
        "accent_color": "#dc2626",
        "favicon_url": None
    })

def migrate():
    """Add branding column to tenant table if it doesn't exist"""
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        # Check if branding column exists
        cursor.execute("PRAGMA table_info(tenant)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'branding' in columns:
            print("✓ Branding column already exists in tenant table")
            connection.close()
            return True
        
        # Add branding column
        default_branding = get_default_branding()
        cursor.execute(f"""
            ALTER TABLE tenant 
            ADD COLUMN branding JSON DEFAULT '{default_branding}'
        """)
        
        connection.commit()
        print("✓ Successfully added branding column to tenant table")
        
        # Verify
        cursor.execute("PRAGMA table_info(tenant)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'branding' in columns:
            print("✓ Verification successful: branding column now exists")
        
        connection.close()
        return True
        
    except sqlite3.Error as e:
        print(f"✗ Database migration failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Migration error: {e}")
        return False

if __name__ == '__main__':
    print(f"Migrating database at: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"✗ Database not found at {DB_PATH}")
        print("Please ensure the web app has been initialized with data")
        sys.exit(1)
    
    if migrate():
        print("\n✓ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Migration failed")
        sys.exit(1)
