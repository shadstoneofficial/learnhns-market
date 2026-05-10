"""allow listing history

Revision ID: c1f4f87d2b91
Revises: 8f3e2b7a91c4
Create Date: 2026-05-10 14:50:00.000000
"""
from alembic import op


revision = 'c1f4f87d2b91'
down_revision = '8f3e2b7a91c4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_name'))
        batch_op.create_index(batch_op.f('ix_listings_name'), ['name'], unique=False)


def downgrade():
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_listings_name'))
        batch_op.create_index(batch_op.f('ix_listings_name'), ['name'], unique=True)
