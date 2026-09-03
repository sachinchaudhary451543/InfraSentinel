#!/usr/bin/env python3
"""
Direct database migration script - adds missing columns without Flask dependencies
"""

import sqlite3
import os
import sys

def migrate_database():
    """Add missing columns to database"""
    db_path = 'central.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Initializing database with required schema...")
        
        # Check if remote_command table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='remote_command'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("Creating remote_command table...")
            cursor.execute('''
            CREATE TABLE remote_command (
                id INTEGER PRIMARY KEY,
                server_id INTEGER NOT NULL,
                command VARCHAR(255) NOT NULL,
                parameters TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                executed_at DATETIME,
                completed_at DATETIME,
                output TEXT,
                error_output TEXT,
                exit_code INTEGER,
                timeout_seconds INTEGER DEFAULT 120,
                created_by VARCHAR(150)
            )
            ''')
            print("✓ remote_command table created")
        else:
            # Check if completed_at column exists
            cursor.execute("PRAGMA table_info(remote_command)")
            columns = {col[1]: col for col in cursor.fetchall()}
            
            if 'completed_at' not in columns:
                print("Adding 'completed_at' column to remote_command table...")
                cursor.execute("ALTER TABLE remote_command ADD COLUMN completed_at DATETIME")
                print("✓ completed_at column added")
            else:
                print("✓ completed_at column already exists")
        
        conn.commit()
        
        # Verify the table
        cursor.execute("PRAGMA table_info(remote_command)")
        columns = cursor.fetchall()
        print(f"\nremote_command table schema:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration Script")
    print("=" * 60 + "\n")
    
    if migrate_database():
        print("\n✅ Database migration completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Database migration failed")
        sys.exit(1)
