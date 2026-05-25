"""add identity correlation fields

Revision ID: 0005_identity_license_correlation_fields
Revises: cb4ee9860cce
Create Date: 2026-05-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0005_identity_license_correlation_fields'
down_revision = 'cb4ee9860cce'
branch_labels = None
depends_on = None


def _has_column(conn, table_name, column_name):
    from sqlalchemy import inspect
    columns = inspect(conn).get_columns(table_name)
    return any(col['name'] == column_name for col in columns)


def _has_index(conn, table_name, index_name):
    from sqlalchemy import inspect
    indexes = inspect(conn).get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def _add_column_if_missing(conn, table_name, column):
    if not _has_column(conn, table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(conn, name, table_name, columns, unique=False):
    if not _has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade():
    conn = op.get_bind()

    _add_column_if_missing(conn, 'employee', sa.Column('display_name', sa.String(length=255), nullable=True))
    _add_column_if_missing(conn, 'employee', sa.Column('azure_user_id', sa.String(length=255), nullable=True))
    _add_column_if_missing(conn, 'azure_user', sa.Column('mail_nickname', sa.String(length=255), nullable=True))
    _add_column_if_missing(conn, 'azure_user', sa.Column('sam_account_name', sa.String(length=255), nullable=True))
    _add_column_if_missing(conn, 'azure_device', sa.Column('normalized_hostname', sa.String(length=255), nullable=True))

    _create_index_if_missing(conn, 'ix_employee_display_name', 'employee', ['display_name'])
    _create_index_if_missing(conn, 'ix_employee_azure_user_id', 'employee', ['azure_user_id'])
    _create_index_if_missing(conn, 'idx_employee_tenant_azure_user', 'employee', ['tenant_id', 'azure_user_id'])
    _create_index_if_missing(conn, 'idx_employee_tenant_local_username', 'employee', ['tenant_id', 'local_username'])
    _create_index_if_missing(conn, 'ix_azure_user_mail_nickname', 'azure_user', ['mail_nickname'])
    _create_index_if_missing(conn, 'ix_azure_user_sam_account_name', 'azure_user', ['sam_account_name'])
    _create_index_if_missing(conn, 'idx_azure_user_tenant_employee', 'azure_user', ['tenant_id', 'employee_id'])
    _create_index_if_missing(conn, 'idx_azure_user_tenant_mail_nickname', 'azure_user', ['tenant_id', 'mail_nickname'])
    _create_index_if_missing(conn, 'idx_azure_user_tenant_sam', 'azure_user', ['tenant_id', 'sam_account_name'])
    _create_index_if_missing(conn, 'ix_azure_device_normalized_hostname', 'azure_device', ['normalized_hostname'])
    _create_index_if_missing(conn, 'idx_azure_device_tenant_normalized_hostname', 'azure_device', ['tenant_id', 'normalized_hostname'])


def downgrade():
    for name, table_name in (
        ('idx_azure_device_tenant_normalized_hostname', 'azure_device'),
        ('ix_azure_device_normalized_hostname', 'azure_device'),
        ('idx_azure_user_tenant_sam', 'azure_user'),
        ('idx_azure_user_tenant_mail_nickname', 'azure_user'),
        ('idx_azure_user_tenant_employee', 'azure_user'),
        ('ix_azure_user_sam_account_name', 'azure_user'),
        ('ix_azure_user_mail_nickname', 'azure_user'),
        ('idx_employee_tenant_local_username', 'employee'),
        ('idx_employee_tenant_azure_user', 'employee'),
        ('ix_employee_azure_user_id', 'employee'),
        ('ix_employee_display_name', 'employee'),
    ):
        try:
            op.drop_index(name, table_name=table_name)
        except Exception:
            pass

    for table_name, column_name in (
        ('azure_device', 'normalized_hostname'),
        ('azure_user', 'sam_account_name'),
        ('azure_user', 'mail_nickname'),
        ('employee', 'azure_user_id'),
        ('employee', 'display_name'),
    ):
        try:
            op.drop_column(table_name, column_name)
        except Exception:
            pass
