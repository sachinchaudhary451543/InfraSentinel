import sqlite3
import sys

db_path = "central.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Checking if audit_log table exists...")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
table_exists = cursor.fetchone()
print(f"Table exists: {bool(table_exists)}")

print("\nCurrent audit_log columns:")
try:
    cursor.execute("PRAGMA table_info(audit_log)")
    cols = cursor.fetchall()
    if cols:
        for col in cols:
            print(f"  {col[1]} ({col[2]})")
    else:
        print("  (no columns found)")
except Exception as e:
    print(f"Error: {e}")

print("\nAll tables in database:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for t in tables:
    print(f"  {t[0]}")

conn.close()
