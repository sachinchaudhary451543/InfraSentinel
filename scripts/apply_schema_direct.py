"""
Apply SQLAlchemy metadata.create_all() directly to the destination DB.
This is a fallback when Alembic isn't available in the runtime.

Usage:
  Set DATABASE_URL env var to the Postgres destination, then run:
    python scripts/apply_schema_direct.py
"""
import os
import sys
from sqlalchemy import create_engine


def main():
    dst = os.environ.get('DATABASE_URL')
    if not dst:
        print('Please set DATABASE_URL to the target Postgres database and retry.')
        sys.exit(1)

    print('Applying SQLAlchemy metadata to', dst)
    engine = create_engine(dst)

    try:
        # Ensure project root is on path so `web` package is importable
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if here not in sys.path:
            sys.path.insert(0, here)

        # Import metadata from models
        from web.models import db
        bind = engine
        db.metadata.create_all(bind=bind)
        print('Schema applied using SQLAlchemy metadata.create_all()')
    except Exception as e:
        print('Error applying schema:', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
