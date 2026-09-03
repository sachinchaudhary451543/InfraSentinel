Alembic migrations

Usage:

1. Install alembic (pip install alembic)
2. Set DATABASE_URL environment variable to your target DB, e.g.:
   export DATABASE_URL=postgresql+psycopg[binary]://user:pass@host:5432/dbname
3. Generate an initial migration:
   alembic revision --autogenerate -m "initial"
4. Apply migrations:
   alembic upgrade head

This env.py reads the SQLALCHEMY URL from the environment and uses the
SQLAlchemy metadata exposed by `web.models.db.metadata` for autogeneration.
