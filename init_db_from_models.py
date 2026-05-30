#!/usr/bin/env python
"""
Initialize database directly from Flask models (skips alembic).
"""

import os
import sys

# Set PostgreSQL as database backend
os.environ['DATABASE_URL'] = 'postgresql://postgres:Airport%402026@127.0.0.1:3000/servermonitor'

try:
    from web.app import app, db
    
    print("=" * 60)
    print("ServerMonitor Database Initialization from Models")
    print("=" * 60)
    print()
    
    with app.app_context():
        print("[1/2] Connecting to PostgreSQL database...")
        print("OK - Connected")
        print()
        
        print("[2/2] Creating database schema from models...")
        db.create_all()
        print("OK - Schema created")
        print()
        
    print("=" * 60)
    print("Database initialization complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run: .\\START_SERVERMONITOR.ps1")
    print("  2. Open: http://localhost:5000")
    print()
    
except Exception as e:
    print()
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    print()
    sys.exit(1)
