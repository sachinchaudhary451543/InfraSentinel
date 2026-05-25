"""Clean up old failed commands from database"""
import sqlite3
from datetime import datetime

# Connect to main database
conn = sqlite3.connect('data/central.db')
cursor = conn.cursor()

print("📋 Checking remote_command table...")
cursor.execute('SELECT COUNT(*) FROM remote_command WHERE status IN ("failed", "pending")')
count = cursor.fetchone()[0]
print(f"Found {count} failed/pending commands")

# Show before state
print("\nBefore cleanup:")
cursor.execute('SELECT status, COUNT(*) FROM remote_command GROUP BY status')
for status, cnt in cursor.fetchall():
    print(f"  {status}: {cnt}")

# Mark all failed commands as 'archived' and update old pending commands
print("\n🧹 Archiving old failed commands...")
cursor.execute('''
    UPDATE remote_command 
    SET status = 'archived' 
    WHERE status = 'failed' 
    AND created_at < datetime('now', '-1 day')
''')
archived_count = cursor.rowcount
print(f"  Archived {archived_count} old failed commands")

# Delete extremely old pending commands (> 7 days)
print("\n🗑️  Cleaning very old pending commands (> 7 days)...")
cursor.execute('''
    DELETE FROM remote_command 
    WHERE status = 'pending' 
    AND created_at < datetime('now', '-7 days')
''')
deleted_count = cursor.rowcount
print(f"  Deleted {deleted_count} very old pending commands")

conn.commit()

# Show after state
print("\nAfter cleanup:")
cursor.execute('SELECT status, COUNT(*) FROM remote_command GROUP BY status')
for status, cnt in cursor.fetchall():
    print(f"  {status}: {cnt}")

conn.close()
print("\n✅ Cleanup complete!")
