"""add_server_vm_uuid

Revision ID: 0003_add_server_vm_uuid
Revises: 0002_add_missing_columns
Create Date: 2026-05-11 15:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import uuid

# revision identifiers, used by Alembic.
revision = '0003_add_server_vm_uuid'
down_revision = '0002_add_missing_columns'
branch_labels = None
depends_on = None


def _col_exists(conn, table, col):
    try:
        res = conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
        return any(r[1] == col for r in res)
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    conn = bind

    # Add uuid to server
    if not _col_exists(conn, 'server', 'uuid'):
        op.add_column('server', sa.Column('uuid', sa.String(length=36), nullable=True))
        rows = conn.execute(text("SELECT id FROM server")).fetchall()
        for r in rows:
            conn.execute(text("UPDATE server SET uuid = :u WHERE id = :id"), {'u': str(uuid.uuid4()), 'id': r[0]})

    # Add uuid to vm
    if not _col_exists(conn, 'vm', 'uuid'):
        op.add_column('vm', sa.Column('uuid', sa.String(length=36), nullable=True))
        rows = conn.execute(text("SELECT id FROM vm")).fetchall()
        for r in rows:
            conn.execute(text("UPDATE vm SET uuid = :u WHERE id = :id"), {'u': str(uuid.uuid4()), 'id': r[0]})


def downgrade():
    raise NotImplementedError('Downgrade not implemented for 0003_add_server_vm_uuid')
