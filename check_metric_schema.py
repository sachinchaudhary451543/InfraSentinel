#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('data/central.db')
cursor = conn.cursor()

print("=== Metric Table Schema ===")
cursor.execute("PRAGMA table_info(metric);")
cols = cursor.fetchall()
for col in cols:
    print(f'{col[1]}: {col[2]}')

conn.close()
