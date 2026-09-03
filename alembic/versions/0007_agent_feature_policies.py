"""add per-employee agent feature policies

Revision ID: 0007_agent_feature_policies
Revises: 0006_scalability_indexes
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_agent_feature_policies'
down_revision = '0006_scalability_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_feature_policy',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('server_id', sa.Integer(), sa.ForeignKey('server.id'), nullable=False),
        sa.Column('employee_key', sa.String(length=255), nullable=False),
        sa.Column('system_metrics', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('productivity', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('screenshots', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('process_inventory', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('installed_software', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('hyperv_inventory', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('browser_activity', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('updated_by', sa.String(length=255)),
        sa.UniqueConstraint('server_id', 'employee_key', name='uq_agent_feature_policy_server_employee'),
    )
    op.create_index('ix_agent_feature_policy_tenant_id', 'agent_feature_policy', ['tenant_id'])
    op.create_index('ix_agent_feature_policy_server_id', 'agent_feature_policy', ['server_id'])
    op.create_index('ix_agent_feature_policy_employee_key', 'agent_feature_policy', ['employee_key'])


def downgrade():
    op.drop_index('ix_agent_feature_policy_employee_key', table_name='agent_feature_policy')
    op.drop_index('ix_agent_feature_policy_server_id', table_name='agent_feature_policy')
    op.drop_index('ix_agent_feature_policy_tenant_id', table_name='agent_feature_policy')
    op.drop_table('agent_feature_policy')
