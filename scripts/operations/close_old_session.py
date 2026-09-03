#!/usr/bin/env python
import sqlite3
import os

# Direct database connection
db_path = 'data/central.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# First check what tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f'Tables in database: {[t[0] for t in tables[:10]]}')

# Find and close old unclosed sessions from 2026-05-16
try:
    cursor.execute('''
        UPDATE activity_session 
        SET end_time = '2026-05-16 23:59:59'
        WHERE start_time >= '2026-05-16 00:00:00'
        AND start_time < '2026-05-17 00:00:00'
        AND end_time IS NULL
    ''')
    
    closed_count = cursor.rowcount
    print(f'Closed {closed_count} old sessions from 2026-05-16')
    
    conn.commit()
    print('✓ Database updated successfully')
except Exception as e:
    print(f'Error: {e}')
finally:
    conn.close()
