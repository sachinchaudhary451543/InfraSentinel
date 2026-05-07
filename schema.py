import sqlite3
conn = sqlite3.connect('data/central.db')
print(conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='metric'").fetchone()[0])
