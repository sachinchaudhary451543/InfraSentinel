"""initial_models

Revision ID: 0001_initial_models
Revises: 
Create Date: 2026-05-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_models'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create all tables from SQLAlchemy metadata as a baseline initial migration."""
    # Import the application's metadata and create all tables.
    try:
        from web.models import db
        bind = op.get_bind()
        db.metadata.create_all(bind=bind)
    except Exception as e:
        # If metadata import fails, raise to ensure migration does not silently fail
        raise


def downgrade():
    """Drop all tables created by the metadata. Use with caution in production."""
    try:
        from web.models import db
        bind = op.get_bind()
        db.metadata.drop_all(bind=bind)
    except Exception as e:
        raise
