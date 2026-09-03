"""add_missing_columns

Revision ID: 0002_add_missing_columns
Revises: 0001_initial_models
Create Date: 2026-05-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import uuid

# revision identifiers, used by Alembic.
revision = '0002_add_missing_columns'
down_revision = '0001_initial_models'
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
    # op.get_bind() returns a Connection in Alembic's runtime; use it directly
    conn = bind

    # Tenant additions
    if not _col_exists(conn, 'tenant', 'uuid'):
        op.add_column('tenant', sa.Column('uuid', sa.String(length=36), nullable=True))
        # backfill UUIDs
        rows = conn.execute(text("SELECT id FROM tenant")).fetchall()
        for r in rows:
            conn.execute(text("UPDATE tenant SET uuid = :u WHERE id = :id"), {'u': str(uuid.uuid4()), 'id': r[0]})

    if not _col_exists(conn, 'tenant', 'sharepoint_site_url'):
        op.add_column('tenant', sa.Column('sharepoint_site_url', sa.String(length=500), nullable=True))
    if not _col_exists(conn, 'tenant', 'sharepoint_connected'):
        op.add_column('tenant', sa.Column('sharepoint_connected', sa.Integer(), nullable=True, server_default='0'))
    if not _col_exists(conn, 'tenant', 'sharepoint_auto_sync'):
        op.add_column('tenant', sa.Column('sharepoint_auto_sync', sa.Integer(), nullable=True, server_default='0'))
    if not _col_exists(conn, 'tenant', 'sharepoint_sync_interval_minutes'):
        op.add_column('tenant', sa.Column('sharepoint_sync_interval_minutes', sa.Integer(), nullable=True, server_default='60'))
    if not _col_exists(conn, 'tenant', 'last_sharepoint_sync_timestamp'):
        op.add_column('tenant', sa.Column('last_sharepoint_sync_timestamp', sa.DateTime(), nullable=True))

    # User additions
    if not _col_exists(conn, 'user', 'uuid'):
        op.add_column('user', sa.Column('uuid', sa.String(length=36), nullable=True))
        rows = conn.execute(text("SELECT id FROM user")).fetchall()
        for r in rows:
            conn.execute(text("UPDATE user SET uuid = :u WHERE id = :id"), {'u': str(uuid.uuid4()), 'id': r[0]})

    if not _col_exists(conn, 'user', 'role'):
        op.add_column('user', sa.Column('role', sa.String(length=50), nullable=False, server_default='user'))
        try:
            conn.execute(text("UPDATE user SET role = 'super_admin' WHERE is_superadmin = 1"))
            conn.execute(text("UPDATE user SET role = 'tenant_admin' WHERE is_superadmin = 0 AND (role IS NULL OR role = '')"))
        except Exception:
            pass

    # Azure user
    if not _col_exists(conn, 'azure_user', 'employee_id'):
        op.add_column('azure_user', sa.Column('employee_id', sa.String(length=255), nullable=True))

    # Server additions (many backward-compat fields)
    server_cols = {
        'is_hyperv_host': sa.Column('is_hyperv_host', sa.Integer(), nullable=True, server_default='0'),
        'server_type': sa.Column('server_type', sa.String(length=50), nullable=True, server_default='Endpoint'),
        'agent_installed': sa.Column('agent_installed', sa.Integer(), nullable=True, server_default='0'),
        'agent_version': sa.Column('agent_version', sa.String(length=50), nullable=True),
        'monitoring_mode': sa.Column('monitoring_mode', sa.String(length=20), nullable=True, server_default='full'),
        'azure_device_id': sa.Column('azure_device_id', sa.String(length=255), nullable=True),
        'serial_number': sa.Column('serial_number', sa.String(length=100), nullable=True),
        'address': sa.Column('address', sa.String(length=255), nullable=True),
        'screenshot_enabled': sa.Column('screenshot_enabled', sa.Integer(), nullable=True, server_default='0'),
        'screenshot_interval_minutes': sa.Column('screenshot_interval_minutes', sa.Integer(), nullable=True, server_default='10')
    }
    for name, col in server_cols.items():
        if not _col_exists(conn, 'server', name):
            op.add_column('server', col)

    # Metric additions
    metric_cols = {
        'cpu': sa.Column('cpu', sa.Float(), nullable=True),
        'ram': sa.Column('ram', sa.Float(), nullable=True),
        'disk': sa.Column('disk', sa.Float(), nullable=True),
        'cpu_util_percent': sa.Column('cpu_util_percent', sa.Float(), nullable=True),
        'ram_util_percent': sa.Column('ram_util_percent', sa.Float(), nullable=True),
        'ssd_util_percent': sa.Column('ssd_util_percent', sa.Float(), nullable=True),
    }
    for name, col in metric_cols.items():
        if not _col_exists(conn, 'metric', name):
            op.add_column('metric', col)

    # VM additions
    vm_cols = {
        'name': sa.Column('name', sa.String(length=100), nullable=True),
        'state': sa.Column('state', sa.String(length=50), nullable=True),
        'cpu': sa.Column('cpu', sa.Float(), nullable=True),
        'ram': sa.Column('ram', sa.Float(), nullable=True),
    }
    for name, col in vm_cols.items():
        if not _col_exists(conn, 'vm', name):
            op.add_column('vm', col)

    # Screenshot additions
    if not _col_exists(conn, 'screenshot', 'local_file_path'):
        op.add_column('screenshot', sa.Column('local_file_path', sa.String(length=500), nullable=True))

    # RemoteCommand additions
    rc_cols = {
        'completed_at': sa.Column('completed_at', sa.DateTime(), nullable=True),
        'output': sa.Column('output', sa.Text(), nullable=True),
        'error_output': sa.Column('error_output', sa.Text(), nullable=True),
        'exit_code': sa.Column('exit_code', sa.Integer(), nullable=True),
        'timeout_seconds': sa.Column('timeout_seconds', sa.Integer(), nullable=True, server_default='120'),
        'created_by': sa.Column('created_by', sa.String(length=150), nullable=True),
    }
    for name, col in rc_cols.items():
        if not _col_exists(conn, 'remote_command', name):
            op.add_column('remote_command', col)


def downgrade():
    # Downgrade is intentionally left minimal because dropping columns in SQLite
    # can be destructive and requires table recreation. For safety, raise.
    raise NotImplementedError('Downgrade not implemented for 0002_add_missing_columns')
