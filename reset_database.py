#!/usr/bin/env python
"""
Reset PostgreSQL database and apply migrations from scratch.
"""

import os
import sys
import psycopg2
from psycopg2 import sql

# Configuration
PG_HOST = os.environ.get("PGHOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PGPORT", "5432"))
PG_USER = os.environ.get("PGUSER", "postgres")
PG_PASSWORD = os.environ.get("PGPASSWORD", "")
DB_NAME = os.environ.get("PGDATABASE", "servermonitor")

def reset_database():
    """Drop and recreate the servermonitor database."""
    
    print("=" * 60)
    print("ServerMonitor Database Reset")
    print("=" * 60)
    print()
    
    try:
        # Connect to default postgres database
        print("[1/3] Connecting to PostgreSQL...")
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        print("OK - Connected")
        print()
        
        # Terminate active connections to the database
        print("[2/3] Dropping database (if exists)...")
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = %s
              AND pid <> pg_backend_pid();
        """, (DB_NAME,))
        
        # Drop database if exists (PostgreSQL doesn't support CASCADE for DROP DATABASE)
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
            sql.Identifier(DB_NAME)
        ))
        print("OK - Database dropped")
        print()
        
        # Create fresh database
        print("[3/3] Creating fresh database...")
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(DB_NAME)
        ))
        print("OK - Database created")
        print()
        
        cursor.close()
        conn.close()
        
        print("=" * 60)
        print("Database reset complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run: alembic upgrade head")
        print("  2. Run: .\\START_SERVERMONITOR.ps1")
        print()
        
        return 0
        
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(reset_database())
