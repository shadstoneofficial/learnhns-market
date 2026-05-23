"""add marketplace covenant index

Revision ID: e6a1d2c3b4f5
Revises: a4e9c2b7d601
Create Date: 2026-05-23 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e6a1d2c3b4f5'
down_revision = 'a4e9c2b7d601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'marketplace_covenant_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('covenant_action', sa.String(length=24), nullable=False),
        sa.Column('tx_hash', sa.String(length=64), nullable=False),
        sa.Column('output_index', sa.Integer(), nullable=False),
        sa.Column('block_height', sa.Integer(), nullable=True),
        sa.Column('block_hash', sa.String(length=64), nullable=True),
        sa.Column('block_time', sa.DateTime(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('network', 'tx_hash', 'output_index', 'covenant_action', 'name', name='uq_market_covenant_event'),
    )
    with op.batch_alter_table('marketplace_covenant_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_block_hash'), ['block_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_block_height'), ['block_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_block_time'), ['block_time'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_covenant_action'), ['covenant_action'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_covenant_events_tx_hash'), ['tx_hash'], unique=False)

    op.create_table(
        'marketplace_indexer_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('last_indexed_height', sa.Integer(), nullable=True),
        sa.Column('target_height', sa.Integer(), nullable=True),
        sa.Column('events_indexed', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('network'),
    )
    with op.batch_alter_table('marketplace_indexer_progress', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_marketplace_indexer_progress_last_indexed_height'), ['last_indexed_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_indexer_progress_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_indexer_progress_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_marketplace_indexer_progress_target_height'), ['target_height'], unique=False)


def downgrade():
    with op.batch_alter_table('marketplace_indexer_progress', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_marketplace_indexer_progress_target_height'))
        batch_op.drop_index(batch_op.f('ix_marketplace_indexer_progress_status'))
        batch_op.drop_index(batch_op.f('ix_marketplace_indexer_progress_network'))
        batch_op.drop_index(batch_op.f('ix_marketplace_indexer_progress_last_indexed_height'))
    op.drop_table('marketplace_indexer_progress')

    with op.batch_alter_table('marketplace_covenant_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_tx_hash'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_source'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_network'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_name'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_covenant_action'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_block_time'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_block_height'))
        batch_op.drop_index(batch_op.f('ix_marketplace_covenant_events_block_hash'))
    op.drop_table('marketplace_covenant_events')
