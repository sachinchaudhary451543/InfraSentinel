#!/usr/bin/env python3
"""
Initialize/migrate database tables from Flask-SQLAlchemy models
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from web.app import app
from web.models import db

def init_db():
    """Create all missing tables from models"""
    with app.app_context():
        print("Creating all tables from SQLAlchemy models...")
        db.create_all()
        print("✅ Database initialized successfully!")
        
        # Verify tables
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\nCreated/verified {len(tables)} tables:")
        for table_name in sorted(tables):
            print(f"  ✓ {table_name}")

if __name__ == '__main__':
    try:
        init_db()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
