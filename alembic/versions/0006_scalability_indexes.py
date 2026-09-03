"""add high-volume query indexes

Revision ID: 0006_scalability_indexes
Revises: 0005_identity_license_correlation_fields
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_scalability_indexes'
down_revision = '0005_identity_license_correlation_fields'
branch_labels = None
depends_on = None


def _existing(conn, table, name):
    return any(index.get('name') == name for index in sa.inspect(conn).get_indexes(table))


def _add(conn, name, table, columns):
    if not _existing(conn, table, name):
        op.create_index(name, table, columns)


def upgrade():
    conn = op.get_bind()
    _add(conn, 'idx_metric_server_timestamp', 'metric', ['server_id', 'timestamp'])
    _add(conn, 'idx_employee_activity_server_timestamp', 'employee_activity', ['server_id', 'timestamp'])
    _add(conn, 'idx_employee_activity_user_timestamp', 'employee_activity', ['user', 'timestamp'])
    _add(conn, 'idx_screenshot_tenant_captured', 'screenshot', ['tenant_id', 'captured_at'])
    _add(conn, 'idx_screenshot_server_captured', 'screenshot', ['server_id', 'captured_at'])
    _add(conn, 'idx_activity_session_employee_start', 'activity_session', ['employee_id', 'start_time'])
    _add(conn, 'idx_remote_command_server_status_created', 'remote_command', ['server_id', 'status', 'created_at'])
    _add(conn, 'idx_server_tenant_hostname', 'server', ['tenant_id', 'hostname'])


def downgrade():
    for name, table in (
        ('idx_server_tenant_hostname', 'server'),
        ('idx_remote_command_server_status_created', 'remote_command'),
        ('idx_activity_session_employee_start', 'activity_session'),
        ('idx_screenshot_server_captured', 'screenshot'),
        ('idx_screenshot_tenant_captured', 'screenshot'),
        ('idx_employee_activity_user_timestamp', 'employee_activity'),
        ('idx_employee_activity_server_timestamp', 'employee_activity'),
        ('idx_metric_server_timestamp', 'metric'),
    ):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass