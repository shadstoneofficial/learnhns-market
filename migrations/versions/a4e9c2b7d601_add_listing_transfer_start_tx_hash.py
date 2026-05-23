"""add listing transfer start tx hash

Revision ID: a4e9c2b7d601
Revises: b6a1d8e3f4c2
Create Date: 2026-05-23 08:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a4e9c2b7d601'
down_revision = 'b6a1d8e3f4c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('transfer_start_tx_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_listings_transfer_start_tx_hash'), ['transfer_start_tx_hash'], unique=False)


def downgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_transfer_start_tx_hash'))
        batch_op.drop_column('transfer_start_tx_hash')
