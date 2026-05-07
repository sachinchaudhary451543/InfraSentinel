import sqlite3
import pprint

try:
    conn = sqlite3.connect('data/central.db')
    cursor = conn.cursor()
    print("Tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    pprint.pprint(cursor.fetchall())
    
    print("\nRecent commands:")
    try:
        cursor.execute("SELECT id, command, status, parameters FROM remote_command ORDER BY id DESC LIMIT 5")
        pprint.pprint(cursor.fetchall())
    except Exception as e:
        print(f"Error querying remote_command: {e}")
        
except Exception as e:
    print(f"Error: {e}")
