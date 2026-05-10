"""add sale tracking fields

Revision ID: d8a63f0d45b2
Revises: c1f4f87d2b91
Create Date: 2026-05-10 15:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd8a63f0d45b2'
down_revision = 'c1f4f87d2b91'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sold_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('sale_tx_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_listings_sale_tx_hash'), ['sale_tx_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_listings_sold_at'), ['sold_at'], unique=False)


def downgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_sold_at'))
        batch_op.drop_index(batch_op.f('ix_listings_sale_tx_hash'))
        batch_op.drop_column('sale_tx_hash')
        batch_op.drop_column('sold_at')
