import sqlite3

conn = sqlite3.connect('central.db')
cursor = conn.cursor()

# Check remote_command table schema
cursor.execute("PRAGMA table_info(remote_command)")
columns = cursor.fetchall()

print("remote_command table columns:")
print("-" * 50)
for col in columns:
    col_id, name, type_, notnull, default, pk = col
    print(f"  {name:20s} {type_:15s} {'NOT NULL' if notnull else ''}")

print("\n✅ The 'completed_at' column exists!" if any(c[1] == 'completed_at' for c in columns) else "\n❌ The 'completed_at' column is missing!")

conn.close()
