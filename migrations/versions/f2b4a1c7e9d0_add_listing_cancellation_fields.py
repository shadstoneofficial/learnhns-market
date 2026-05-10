"""add listing cancellation fields

Revision ID: f2b4a1c7e9d0
Revises: d8a63f0d45b2
Create Date: 2026-05-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f2b4a1c7e9d0'
down_revision = 'd8a63f0d45b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cancelled_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('cancel_tx_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_listings_cancel_tx_hash'), ['cancel_tx_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_listings_cancelled_at'), ['cancelled_at'], unique=False)


def downgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_cancelled_at'))
        batch_op.drop_index(batch_op.f('ix_listings_cancel_tx_hash'))
        batch_op.drop_column('cancel_tx_hash')
        batch_op.drop_column('cancelled_at')
