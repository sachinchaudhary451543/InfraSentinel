import sqlite3
from datetime import date

db_path = 'data/central.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check for 2026-05-19 (the date in the system)
target_date = '2026-05-19'
print(f'Checking for productivity data for date: {target_date}')

# Check AppUsage
cursor.execute("SELECT COUNT(*) FROM app_usage WHERE DATE(start_time)=?", (target_date,))
count = cursor.fetchone()[0]
print(f'✓ AppUsage records for {target_date}: {count}')

# Check ActivitySession
cursor.execute("SELECT COUNT(*) FROM activity_session WHERE DATE(start_time)=?", (target_date,))
count = cursor.fetchone()[0]
print(f'✓ ActivitySession records for {target_date}: {count}')

# Check EmployeeActivity
cursor.execute("SELECT COUNT(*) FROM employee_activity WHERE DATE(timestamp)=?", (target_date,))
count = cursor.fetchone()[0]
print(f'✓ EmployeeActivity records for {target_date}: {count}')

# Show sample activity session details
print("\n=== ActivitySession Details ===")
cursor.execute("SELECT id, employee_id, server_id, start_time, end_time FROM activity_session WHERE DATE(start_time)=? LIMIT 5", (target_date,))
for row in cursor.fetchall():
    print(f"Session {row[0]}: employee={row[1]}, server={row[2]}, start={row[3]}, end={row[4]}")

# Show sample app usage
print("\n=== AppUsage Samples ===")
cursor.execute("SELECT COUNT(*), app_name FROM app_usage WHERE DATE(start_time)=? GROUP BY app_name", (target_date,))
for row in cursor.fetchall():
    print(f"{row[1]}: {row[0]} records")

conn.close()
