from __future__ import with_statement
import os
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add project path so imports like `from web.models import db` work
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import your metadata object from the models module
try:
    from web.models import db
    target_metadata = db.metadata
except Exception:
    target_metadata = None


# Obtain DB URL: prefer env var DATABASE_URL
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    # fallback to sqlalchemy.url in ini if present
    db_url = config.get_main_option('sqlalchemy.url')

# If the ini contains the placeholder 'driver://user:pass@localhost/dbname' or
# the env var is not set, try to import the Flask app and read its SQLALCHEMY
# setting so local developers can run alembic without setting env vars.
if not db_url or db_url.startswith('driver://'):
    # Try a sensible default local SQLite database used by the app so developers
    # can run alembic without exporting DATABASE_URL. This mirrors the
    # app's fallback to data/central.db.
    try:
        default_path = os.path.join(ROOT, 'data', 'central.db')
        db_url = f"sqlite:///{default_path}"
    except Exception:
        pass

if db_url:
    # Note: don't use config.set_main_option() as it breaks with URLs containing '%'
    # (ConfigParser treats % as special). We'll pass url directly to context.configure()
    pass


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    # Get URL from env or config, handling URLs with % characters properly
    url = db_url or config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    # Get URL from env or config, handling URLs with % characters properly
    url = db_url or config.get_main_option('sqlalchemy.url')
    
    if not url:
        raise ValueError('No database URL configured. Set DATABASE_URL env var or sqlalchemy.url in alembic.ini')
    
    from sqlalchemy import create_engine
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
