# db_handler.py
# (Not heavily used - main uses sqlite3 directly. Provided for extension.)
import sqlite3
def connect(db_path):
    conn = sqlite3.connect(db_path)
    return conn
