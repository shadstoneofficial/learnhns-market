"""add global name index tables

Revision ID: a7d4c2e8b931
Revises: 5cc2a8f6d9b1
Create Date: 2026-05-11 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7d4c2e8b931'
down_revision = '5cc2a8f6d9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'global_name_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('state', sa.String(length=40), nullable=True),
        sa.Column('renewal_height', sa.Integer(), nullable=True),
        sa.Column('expiration_height', sa.Integer(), nullable=True),
        sa.Column('blocks_until_expire', sa.Integer(), nullable=True),
        sa.Column('days_until_expire', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('hours_until_expire', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('expired', sa.Boolean(), nullable=False),
        sa.Column('source_height', sa.Integer(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'network', name='uq_global_name_states_name_network'),
    )
    with op.batch_alter_table('global_name_states', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_global_name_states_blocks_until_expire'), ['blocks_until_expire'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_expiration_height'), ['expiration_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_expired'), ['expired'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_last_checked_at'), ['last_checked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_source_height'), ['source_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_global_name_states_state'), ['state'], unique=False)

    op.create_table(
        'name_indexer_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('last_indexed_height', sa.Integer(), nullable=True),
        sa.Column('target_height', sa.Integer(), nullable=True),
        sa.Column('names_indexed', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('network'),
    )
    with op.batch_alter_table('name_indexer_progress', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_name_indexer_progress_last_indexed_height'), ['last_indexed_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_name_indexer_progress_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_name_indexer_progress_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_name_indexer_progress_target_height'), ['target_height'], unique=False)


def downgrade():
    with op.batch_alter_table('name_indexer_progress', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_name_indexer_progress_target_height'))
        batch_op.drop_index(batch_op.f('ix_name_indexer_progress_status'))
        batch_op.drop_index(batch_op.f('ix_name_indexer_progress_network'))
        batch_op.drop_index(batch_op.f('ix_name_indexer_progress_last_indexed_height'))
    op.drop_table('name_indexer_progress')

    with op.batch_alter_table('global_name_states', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_global_name_states_state'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_source_height'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_network'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_name'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_last_checked_at'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_expired'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_expiration_height'))
        batch_op.drop_index(batch_op.f('ix_global_name_states_blocks_until_expire'))
    op.drop_table('global_name_states')
