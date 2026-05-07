#!/usr/bin/env python3
"""
Script to add missing database columns that were defined in models but not yet in the database.
Specifically adds 'completed_at' column to remote_command table.
"""

import sqlite3
import os
from datetime import datetime

def add_missing_columns():
    """Add missing columns to the remote_command table"""
    db_path = os.path.join(os.path.dirname(__file__), 'central.db')
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if completed_at column exists
        cursor.execute("PRAGMA table_info(remote_command)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'completed_at' not in columns:
            print("Adding 'completed_at' column to remote_command table...")
            cursor.execute("ALTER TABLE remote_command ADD COLUMN completed_at DATETIME")
            conn.commit()
            print("✓ 'completed_at' column added successfully")
        else:
            print("✓ 'completed_at' column already exists")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(remote_command)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"\nRemote command table columns: {columns}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"ERROR: Database error: {e}")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Adding Missing Database Columns")
    print("=" * 60)
    
    if add_missing_columns():
        print("\n✓ Database schema update completed successfully")
    else:
        print("\n✗ Failed to update database schema")
