"""add license sku, license assignment, productivity classification and sync job

Revision ID: 0004_add_license_and_productivity_models
Revises: 0003_add_server_vm_uuid
Create Date: 2026-05-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004_add_license_and_productivity_models'
down_revision = '0003_add_server_vm_uuid'
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    from sqlalchemy import inspect
    insp = inspect(conn)
    return insp.has_table(table_name)

def upgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'
    
    # License SKU
    if not _table_exists(bind, 'license_sku'):
        op.create_table(
            'license_sku',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenant.id'), nullable=False, index=True),
            sa.Column('sku_id', sa.String(100), nullable=False, index=True),
            sa.Column('sku_part_number', sa.String(200)),
            sa.Column('prepaid_units', sa.Integer),
            sa.Column('consumed_units', sa.Integer),
            sa.Column('metadata', postgresql.JSONB() if is_postgres else sa.JSON()),
            sa.Column('fetched_at', sa.DateTime, server_default=sa.func.now()),
        )

    if not _table_exists(bind, 'license_assignment'):
        op.create_table(
            'license_assignment',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenant.id'), nullable=False, index=True),
            sa.Column('user_id', sa.String(100), index=True),
            sa.Column('user_principal_name', sa.String(200), index=True),
            sa.Column('sku_id', sa.String(100), index=True),
            sa.Column('state', sa.String(50)),
            sa.Column('assigned_at', sa.DateTime),
            sa.Column('last_seen', sa.DateTime),
            sa.Column('metadata', postgresql.JSONB() if is_postgres else sa.JSON()),
        )

    if not _table_exists(bind, 'productivity_classification'):
        op.create_table(
            'productivity_classification',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenant.id'), nullable=False, index=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('pattern', sa.String(500), nullable=False),
            sa.Column('category', sa.String(50), nullable=False),
            sa.Column('metadata', postgresql.JSONB() if is_postgres else sa.JSON()),
        )

    if not _table_exists(bind, 'sync_job'):
        op.create_table(
            'sync_job',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenant.id'), nullable=True, index=True),
            sa.Column('job_type', sa.String(100), nullable=False, index=True),
            sa.Column('status', sa.String(50), default='pending', index=True),
            sa.Column('started_at', sa.DateTime),
            sa.Column('completed_at', sa.DateTime),
            sa.Column('log', sa.Text),
            sa.Column('metadata', postgresql.JSONB() if is_postgres else sa.JSON()),
        )


def downgrade():
    op.drop_table('sync_job')
    op.drop_table('productivity_classification')
    op.drop_table('license_assignment')
    op.drop_table('license_sku')
