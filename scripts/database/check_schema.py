import sqlite3

conn = sqlite3.connect('data/central.db')
cursor = conn.cursor()

print("=== app_usage columns ===")
cursor.execute("PRAGMA table_info(app_usage)")
for row in cursor.fetchall():
    print(row)

print("\n=== activity_session columns ===")
cursor.execute("PRAGMA table_info(activity_session)")
for row in cursor.fetchall():
    print(row)

print("\n=== employee_activity columns ===")
cursor.execute("PRAGMA table_info(employee_activity)")
for row in cursor.fetchall():
    print(row)

conn.close()
