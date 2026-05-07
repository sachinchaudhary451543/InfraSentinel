#!/usr/bin/env python3
"""
Minimal Flask app initialization to create all database tables
"""

import sys
import os

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up minimal environment
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('DATABASE_URL', 'sqlite:///central.db')

try:
    print("Initializing Flask application...")
    from web.app import app
    from web.models import db
    
    with app.app_context():
        print("Creating all database tables...")
        db.create_all()
        
        # List created tables
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        print(f"\n✅ Successfully created {len(tables)} database tables:")
        for table in sorted(tables):
            cols = len(inspector.get_columns(table))
            print(f"  ✓ {table:30s} ({cols} columns)")
        
        print("\n✅ Database initialization complete!")
        
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("\nTrying alternative approach with minimal setup...")
    
    # Fallback: create tables directly
    import sqlite3
    db_path = 'central.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get list of all table creation statements from the schema
    print("Creating core tables...")
    
    # Server table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS server (
        id INTEGER PRIMARY KEY,
        hostname VARCHAR(255) NOT NULL,
        ip_address VARCHAR(45),
        os_info VARCHAR(255),
        status VARCHAR(50) DEFAULT 'offline',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # RemoteCommand table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS remote_command (
        id INTEGER PRIMARY KEY,
        server_id INTEGER NOT NULL REFERENCES server(id),
        command VARCHAR(255) NOT NULL,
        parameters TEXT,
        status VARCHAR(50) DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        executed_at DATETIME,
        completed_at DATETIME,
        output TEXT,
        error_output TEXT,
        exit_code INTEGER,
        timeout_seconds INTEGER DEFAULT 120,
        created_by VARCHAR(150)
    )
    ''')
    
    # Metric table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS metric (
        id INTEGER PRIMARY KEY,
        server_id INTEGER NOT NULL REFERENCES server(id),
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        cpu_util_percent REAL,
        ram_util_percent REAL,
        ssd_util_percent REAL
    )
    ''')
    
    conn.commit()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"\n✅ Created {len(tables)} tables: {[t[0] for t in tables]}")
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
