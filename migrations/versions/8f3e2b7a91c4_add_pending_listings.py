"""add pending listings

Revision ID: 8f3e2b7a91c4
Revises: 299fd53a3ab6
Create Date: 2026-05-10 10:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '8f3e2b7a91c4'
down_revision = '299fd53a3ab6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pending_listings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('transfer_tx_hash', sa.String(length=64), nullable=False),
        sa.Column('transfer_output_idx', sa.Integer(), nullable=True),
        sa.Column('lock_script_addr', sa.String(length=100), nullable=True),
        sa.Column('listing_mode', sa.String(length=40), nullable=False),
        sa.Column('expected_price', sa.BigInteger(), nullable=True),
        sa.Column('seller_note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'network', name='uq_pending_listings_name_network'),
        sa.UniqueConstraint('transfer_tx_hash'),
    )
    with op.batch_alter_table('pending_listings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pending_listings_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_pending_listings_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_pending_listings_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pending_listings_transfer_tx_hash'), ['transfer_tx_hash'], unique=True)


def downgrade():
    with op.batch_alter_table('pending_listings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pending_listings_transfer_tx_hash'))
        batch_op.drop_index(batch_op.f('ix_pending_listings_status'))
        batch_op.drop_index(batch_op.f('ix_pending_listings_network'))
        batch_op.drop_index(batch_op.f('ix_pending_listings_name'))
    op.drop_table('pending_listings')
