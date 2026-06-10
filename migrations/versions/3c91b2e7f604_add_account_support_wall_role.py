"""add account support wall role

Revision ID: 3c91b2e7f604
Revises: 7b2c9d4e8f10
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '3c91b2e7f604'
down_revision = '7b2c9d4e8f10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('support_wall_role', sa.String(length=40), nullable=False, server_default='none'))
        batch_op.create_index(batch_op.f('ix_accounts_support_wall_role'), ['support_wall_role'], unique=False)

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.alter_column('support_wall_role', server_default=None)


def downgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accounts_support_wall_role'))
        batch_op.drop_column('support_wall_role')
