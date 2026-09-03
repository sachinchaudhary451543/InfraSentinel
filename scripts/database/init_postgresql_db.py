#!/usr/bin/env python
"""
ServerMonitor PostgreSQL Database Initialization
Creates the 'servermonitor' database if it doesn't exist.
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

def create_database():
    """Create the servermonitor database if it doesn't exist."""
    
    print("=" * 60)
    print("ServerMonitor PostgreSQL Database Initialization")
    print("=" * 60)
    print()
    print(f"PostgreSQL: {PG_HOST}:{PG_PORT}")
    print(f"Database: {DB_NAME}")
    print()
    
    try:
        # Connect to the default 'postgres' database
        print("[1/2] Connecting to PostgreSQL...")
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database="postgres"  # Connect to default database first
        )
        conn.autocommit = True
        cursor = conn.cursor()
        print("OK - Connected to PostgreSQL")
        print()
        
        # Check if database exists
        print("[2/2] Checking if database exists...")
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = %s);",
            (DB_NAME,)
        )
        exists = cursor.fetchone()[0]
        
        if exists:
            print(f"OK - Database '{DB_NAME}' already exists")
        else:
            print(f"Database not found. Creating '{DB_NAME}'...")
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(DB_NAME)
            ))
            print(f"OK - Database '{DB_NAME}' created successfully")
        
        cursor.close()
        conn.close()
        
        print()
        print("=" * 60)
        print("Database initialization complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run: .\\START_SERVERMONITOR.ps1")
        print("  2. Open: http://localhost:5000")
        print()
        
        return 0
        
    except psycopg2.OperationalError as e:
        print()
        print("ERROR: Failed to connect to PostgreSQL")
        print(f"Details: {e}")
        print()
        print("Troubleshooting:")
        print(f"  1. Verify PostgreSQL is running on {PG_HOST}:{PG_PORT}")
        print(f"  2. Check PGUSER and PGPASSWORD environment variables (user: {PG_USER})")
        print("  3. Verify network connectivity to PostgreSQL server")
        print()
        return 1
        
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(create_database())
